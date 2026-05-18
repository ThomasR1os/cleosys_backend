import logging
from collections import Counter

from django.db.models import Exists, OuterRef
from rest_framework import permissions, status, viewsets, views
from rest_framework.response import Response

from accounts.models import UserProfile
from accounts.permissions import AlmacenWritePermission, company_id_for_user, is_admin_access
from ventas.models import ClientContact
from ventas.serializers import ClientContactSerializer, UserPublicSummarySerializer

from .client_lookup import (
    contacts_exist_scope_company,
    contacts_exist_scope_mine,
    find_client_by_ruc_query,
    normalize_ruc_digits,
    validate_pe_ruc_digits,
)

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


def _contact_display_name(cc: ClientContact) -> str:
    fn = (cc.contact_first_name or "").strip()
    ln = (cc.contact_last_name or "").strip()
    if fn or ln:
        return f"{fn} {ln}".strip()
    return ""


def _user_eligible_sales_highlight(user) -> bool:
    """Asesores VENTAS destacados en el resumen (no admin app, staff ni superusuario)."""
    if not user or user.is_superuser or user.is_staff:
        return False
    p = getattr(user, "profile", None) or UserProfile.objects.filter(user_id=user.pk).first()
    if not p:
        return False
    if p.role == UserProfile.Role.ADMIN:
        return False
    return p.role == UserProfile.Role.VENTAS


def _pick_primary_and_others(counter: Counter[int], uids: list[int]) -> tuple[int | None, list[int]]:
    """
    Asesor principal solo si tiene estrictamente más contactos que el siguiente.
    Si hay empate (ej. 2 contactos, 2 asesores con 1 c/u), no hay principal.
    """
    if not uids:
        return None, []
    ordered = sorted(uids, key=lambda uid: (-counter[uid], uid))
    if len(ordered) == 1:
        return ordered[0], []
    if counter[ordered[0]] > counter[ordered[1]]:
        return ordered[0], ordered[1:]
    return None, ordered


def _build_sales_summary(
    counter: Counter[int],
    user_by_id: dict,
    contacts_count: int,
) -> dict:
    eligible_uids = [uid for uid in counter if _user_eligible_sales_highlight(user_by_id[uid])]
    use_uids = eligible_uids if eligible_uids else list(counter.keys())

    primary_uid, peer_uids = _pick_primary_and_others(counter, use_uids)

    sales_users = []
    for uid in sorted(use_uids, key=lambda u: (-counter[u], u)):
        summary = UserPublicSummarySerializer(user_by_id[uid]).data
        sales_users.append({**summary, "contacts_count": counter[uid]})

    primary_summary = None
    others_summaries = []
    if primary_uid is not None:
        primary_summary = UserPublicSummarySerializer(user_by_id[primary_uid]).data
        others_summaries = [
            UserPublicSummarySerializer(user_by_id[uid]).data for uid in peer_uids
        ]
    elif peer_uids:
        others_summaries = [
            UserPublicSummarySerializer(user_by_id[uid]).data for uid in peer_uids
        ]

    n_advisors = len(use_uids)
    names = [
        (UserPublicSummarySerializer(user_by_id[uid]).data.get("nombre") or user_by_id[uid].username)
        for uid in sorted(use_uids, key=lambda u: (-counter[u], u))
    ]

    if not eligible_uids and counter:
        msg = (
            "El cliente está registrado, pero los contactos están asignados a perfiles "
            "no comerciales o administrativos. Consulte con su supervisor."
        )
    elif contacts_count == 1 and n_advisors == 1:
        msg = (
            f"El cliente está registrado en su empresa; el contacto está a cargo de {names[0]}."
        )
    elif n_advisors == 1:
        msg = (
            f"El cliente está registrado; {names[0]} tiene {contacts_count} contacto(s) "
            f"registrado(s) en su empresa."
        )
    elif n_advisors == contacts_count and all(counter[uid] == 1 for uid in use_uids):
        if n_advisors == 2:
            msg = (
                f"El cliente está registrado con {contacts_count} contactos; cada uno está "
                f"asignado a un asesor distinto ({names[0]} y {names[1]})."
            )
        else:
            listed = ", ".join(names[:-1]) + f" y {names[-1]}"
            msg = (
                f"El cliente está registrado con {contacts_count} contactos; cada uno tiene "
                f"su asesor asignado ({listed})."
            )
    elif primary_uid is not None:
        nombre_pri = names[0]
        msg = (
            f"El cliente está registrado; la cartera comercial la trabaja principalmente "
            f"{nombre_pri} ({counter[primary_uid]} contacto(s))."
        )
        if peer_uids:
            otros = ", ".join(
                UserPublicSummarySerializer(user_by_id[uid]).data.get("nombre")
                or user_by_id[uid].username
                for uid in peer_uids
            )
            msg += f" También hay contactos con {otros}."
    else:
        listed = ", ".join(names)
        msg = (
            f"El cliente está registrado con {contacts_count} contacto(s) repartidos entre "
            f"{n_advisors} asesores: {listed}."
        )

    return {
        "message_for_ui": msg,
        "contacts_count": contacts_count,
        "sales_users": sales_users,
        "primary_sales_user": primary_summary,
        "other_sales_users": others_summaries,
    }


class ClientLookupByRucView(views.APIView):
    """
    GET /api/clients/lookup-by-ruc/?ruc=...&scope=company|mine

    Indica si el cliente existe para la empresa según scope y devuelve resumen comercial
    más todos los contactos de ese cliente en la empresa.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        ruc_raw = (request.query_params.get("ruc") or "").strip()
        if not ruc_raw:
            return Response(
                {"detail": "Indique el parámetro ruc."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        digits = normalize_ruc_digits(ruc_raw)
        if not validate_pe_ruc_digits(digits):
            return Response(
                {"detail": "RUC inválido: se esperan 11 dígitos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        scope = (request.query_params.get("scope") or "company").strip().lower()
        if scope not in ("company", "mine"):
            return Response(
                {"detail": "scope debe ser company o mine."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        company_id = company_id_for_user(request.user)
        if company_id is None:
            return Response(
                {"detail": "Su usuario no tiene empresa asignada; no puede consultar por RUC."},
                status=status.HTTP_403_FORBIDDEN,
            )

        client_obj = find_client_by_ruc_query(digits)
        empty = {
            "exists": False,
            "client": None,
            "sales_summary": None,
            "contacts": [],
        }
        if client_obj is None:
            return Response(empty)

        if scope == "company":
            in_scope = contacts_exist_scope_company(client_obj.pk, company_id)
        else:
            in_scope = contacts_exist_scope_mine(client_obj.pk, company_id, request.user.pk)

        if not in_scope:
            return Response(empty)

        contacts_qs = (
            ClientContact.objects.filter(client_id=client_obj.pk, company_id=company_id)
            .select_related("user", "user__profile")
            .order_by("id")
        )
        contacts_count = contacts_qs.count()
        counter: Counter[int] = Counter()
        user_by_id = {}

        contacts_out = []
        for cc in contacts_qs:
            counter[cc.user_id] += 1
            user_by_id[cc.user_id] = cc.user
            can_see = ClientContactSerializer._can_see_email_and_phone(request.user, cc)
            encargado_data = UserPublicSummarySerializer(cc.user).data
            contacts_out.append(
                {
                    "id": cc.pk,
                    "contact_first_name": cc.contact_first_name,
                    "contact_last_name": cc.contact_last_name,
                    "nombre": _contact_display_name(cc),
                    "email": cc.email if can_see else None,
                    "phone": cc.phone if can_see else None,
                    "user": cc.user_id,
                    "encargado": encargado_data,
                }
            )

        eligible_uids = [uid for uid in counter if _user_eligible_sales_highlight(user_by_id[uid])]
        use_uids = eligible_uids if eligible_uids else list(counter.keys())
        primary_uid, _peer_uids = _pick_primary_and_others(counter, use_uids)

        for row, cc in zip(contacts_out, contacts_qs):
            row["is_primary_advisor"] = (
                primary_uid is not None and cc.user_id == primary_uid
            )

        sales_summary = _build_sales_summary(counter, user_by_id, contacts_count)

        return Response(
            {
                "exists": True,
                "client": {"id": client_obj.pk, "ruc": client_obj.ruc, "name": client_obj.name},
                "sales_summary": sales_summary,
                "contacts": contacts_out,
            }
        )


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
