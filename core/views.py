import logging

from django.db.models import Exists, OuterRef
from rest_framework import permissions, viewsets, views
from rest_framework.response import Response

from accounts.permissions import AlmacenWritePermission, company_id_for_user, is_admin_access
from ventas.models import ClientContact

from .models import (
    Brand,
    CategoryProduct,
    Client,
    PaymentMethods,
    SubcategoryProduct,
    Supplier,
    TypeProduct,
    UnitMeasurement,
)
from .sunat_ruc import SunatConsultaError, fetch_ruc_with_playwright
from .serializers import (
    BrandSerializer,
    CategoryProductSerializer,
    ClientSerializer,
    PaymentMethodsSerializer,
    SubcategoryProductSerializer,
    SupplierSerializer,
    TypeProductSerializer,
    UnitMeasurementSerializer,
)

logger = logging.getLogger(__name__)


def sunat_ruc_query_from_request(request) -> str:
    """Obtiene el RUC a consultar (query, JSON o form) en los endpoints SUNAT."""
    q = (request.query_params.get("ruc") or "").strip()
    if q:
        return q
    if request.method == "POST" and hasattr(request, "data"):
        body = request.data
        if hasattr(body, "get"):
            v = body.get("ruc")
            if v is not None and str(v).strip():
                return str(v).strip()
    return ""


class BaseCoreViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]


class MaestroCatalogViewSet(viewsets.ModelViewSet):
    """Maestros de catálogo: lectura para todos; alta/edición solo almacén o admin."""

    permission_classes = [permissions.IsAuthenticated, AlmacenWritePermission]


class SupplierViewSet(MaestroCatalogViewSet):
    queryset = Supplier.objects.all().order_by("id")
    serializer_class = SupplierSerializer


class BrandViewSet(MaestroCatalogViewSet):
    queryset = Brand.objects.all().order_by("id")
    serializer_class = BrandSerializer


class CategoryProductViewSet(MaestroCatalogViewSet):
    queryset = CategoryProduct.objects.all().order_by("id")
    serializer_class = CategoryProductSerializer


class SubcategoryProductViewSet(MaestroCatalogViewSet):
    queryset = SubcategoryProduct.objects.all().order_by("id")
    serializer_class = SubcategoryProductSerializer


class TypeProductViewSet(MaestroCatalogViewSet):
    queryset = TypeProduct.objects.all().order_by("id")
    serializer_class = TypeProductSerializer


class UnitMeasurementViewSet(MaestroCatalogViewSet):
    queryset = UnitMeasurement.objects.all().order_by("id")
    serializer_class = UnitMeasurementSerializer


class ClientViewSet(BaseCoreViewSet):
    queryset = Client.objects.all().order_by("id")
    serializer_class = ClientSerializer

    def _annotate_is_mine(self, qs):
        """
        Marca cada cliente con `is_mine_anno=True` si el usuario tiene al menos un
        ClientContact asignado en ese cliente. Evita N+1 en el serializer.
        """
        user = self.request.user
        if not user or not user.is_authenticated:
            return qs
        return qs.annotate(
            is_mine_anno=Exists(
                ClientContact.objects.filter(client=OuterRef("pk"), user=user)
            )
        )

    def get_queryset(self):
        qs = Client.objects.all().order_by("id")
        user = self.request.user
        if user.is_superuser:
            return self._annotate_is_mine(qs)
        company_id = company_id_for_user(user)
        if company_id is None:
            return qs.none()
        # Siempre acotado a la empresa del usuario; el parámetro `scope` no puede escapar de eso.
        company_qs = qs.filter(contacts__company_id=company_id).distinct()
        # Admin de aplicación: ve todos los clientes de su empresa, en cualquier acción.
        if is_admin_access(user):
            return self._annotate_is_mine(company_qs)
        # `scope=company` solo amplía el LISTADO; retrieve/update/destroy siguen siendo "míos".
        if (
            self.action == "list"
            and self.request.query_params.get("scope") == "company"
        ):
            return self._annotate_is_mine(company_qs)
        # Comportamiento por defecto: solo clientes con al menos un contacto asignado al usuario.
        mine_qs = qs.filter(
            contacts__company_id=company_id, contacts__user=user
        ).distinct()
        return self._annotate_is_mine(mine_qs)

    def perform_create(self, serializer):
        serializer.save()


class PaymentMethodsViewSet(MaestroCatalogViewSet):
    queryset = PaymentMethods.objects.all().order_by("id")
    serializer_class = PaymentMethodsSerializer


class SunatRucConsultaView(views.APIView):
    """
    GET o POST /api/sunat/ruc/
    - GET: ?ruc=20123456789
    - POST: mismo query, o cuerpo JSON {"ruc": "20123456789"}, o form campo ruc.

    Requiere Playwright y Chromium instalados en el servidor.
    """

    permission_classes = [permissions.IsAuthenticated]

    def _response_consulta(self, request, *args, **kwargs):
        ruc = sunat_ruc_query_from_request(request)
        if not ruc:
            return Response(
                {
                    "detail": "Indique ruc: en la query (?ruc=), en JSON {\"ruc\": \"...\"} o en el formulario.",
                },
                status=400,
            )
        try:
            data = fetch_ruc_with_playwright(ruc)
        except SunatConsultaError as e:
            return Response({"detail": str(e)}, status=400)
        except Exception:
            logger.exception("Error al consultar SUNAT por RUC")
            return Response(
                {"detail": "No se pudo completar la consulta en SUNAT. Intente más tarde."},
                status=502,
            )
        return Response(data)

    def get(self, request, *args, **kwargs):
        return self._response_consulta(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self._response_consulta(request, *args, **kwargs)


class SunatRucIdentificacionView(views.APIView):
    """
    GET o POST /api/sunat/ruc/identificacion/
    Misma forma de enviar el RUC que /api/sunat/ruc/; respuesta: {"ruc", "razon_social"}.
    """

    permission_classes = [permissions.IsAuthenticated]

    def _response(self, request, *args, **kwargs):
        ruc = sunat_ruc_query_from_request(request)
        if not ruc:
            return Response(
                {
                    "detail": "Indique ruc: en la query (?ruc=), en JSON {\"ruc\": \"...\"} o en el formulario.",
                },
                status=400,
            )
        try:
            data = fetch_ruc_with_playwright(ruc)
        except SunatConsultaError as e:
            return Response({"detail": str(e)}, status=400)
        except Exception:
            logger.exception("Error al consultar SUNAT por RUC (identificación)")
            return Response(
                {"detail": "No se pudo completar la consulta en SUNAT. Intente más tarde."},
                status=502,
            )
        out_ruc = data.get("ruc")
        razon = data.get("razon_social")
        if not out_ruc or not razon:
            return Response(
                {
                    "detail": "No se pudo extraer RUC o razón social del resultado de SUNAT.",
                },
                status=502,
            )
        return Response({"ruc": out_ruc, "razon_social": razon})

    def get(self, request, *args, **kwargs):
        return self._response(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        return self._response(request, *args, **kwargs)
