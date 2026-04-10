from django.db.models import QuerySet
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied

from accounts.permissions import company_id_for_user, is_admin_access

from .models import ClientContact, Quotation, QuotationProduct
from .serializers import ClientContactSerializer, QuotationProductSerializer, QuotationSerializer


def filter_quotation_queryset_for_user(qs: QuerySet[Quotation], user) -> QuerySet[Quotation]:
    """
    Lectura (listado y detalle): todos los usuarios con empresa ven las cotizaciones de su compañía.
    Superusuario: todas. Sin empresa en perfil: ninguna.

    La edición no se gobierna aquí: ver `can_edit_quotation` + check_object_permissions en los viewsets.
    """
    if user.is_superuser:
        return qs
    company_id = company_id_for_user(user)
    if company_id is None:
        return qs.none()
    return qs.filter(user__profile__company_id=company_id)


def can_edit_quotation(request, quotation: Quotation) -> bool:
    """Modificar o eliminar cotización / sus líneas: dueño o administrador de app (o superusuario)."""
    u = request.user
    if not u.is_authenticated:
        return False
    if u.is_superuser or is_admin_access(u):
        return True
    return quotation.user_id == u.id


class BaseVentasViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]


class ClientContactViewSet(BaseVentasViewSet):
    queryset = ClientContact.objects.all().order_by("id")
    serializer_class = ClientContactSerializer

    def get_queryset(self):
        qs = (
            ClientContact.objects.select_related("user", "client", "company")
            .all()
            .order_by("id")
        )
        user = self.request.user
        if user.is_superuser:
            return qs
        company_id = company_id_for_user(user)
        if company_id is None:
            return qs.none()
        return qs.filter(company_id=company_id)

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in permissions.SAFE_METHODS:
            if request.user.is_superuser or is_admin_access(request.user):
                return
            if obj.user_id != request.user.id:
                raise PermissionDenied(
                    detail="Solo el vendedor asignado o un administrador pueden modificar o eliminar este contacto."
                )

    def perform_create(self, serializer):
        if is_admin_access(self.request.user):
            serializer.save()
        else:
            serializer.save(user_id=self.request.user.pk)


class QuotationViewSet(BaseVentasViewSet):
    queryset = Quotation.objects.all().order_by("id")
    serializer_class = QuotationSerializer

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("client", "client_contact", "user", "user__profile", "payment_methods")
        )
        return filter_quotation_queryset_for_user(qs, self.request.user)

    def perform_create(self, serializer):
        if is_admin_access(self.request.user):
            serializer.save()
        else:
            serializer.save(user_id=self.request.user.pk)

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in permissions.SAFE_METHODS:
            if not can_edit_quotation(request, obj):
                raise PermissionDenied(
                    detail="Solo el vendedor que creó la cotización o un administrador pueden modificarla o eliminarla."
                )


class QuotationProductViewSet(BaseVentasViewSet):
    queryset = QuotationProduct.objects.select_related("product", "quotation").order_by("id")
    serializer_class = QuotationProductSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "product",
            "quotation__user",
            "quotation__user__profile",
        )
        visible = filter_quotation_queryset_for_user(Quotation.objects.all(), self.request.user)
        return qs.filter(quotation__in=visible)

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in permissions.SAFE_METHODS:
            if not can_edit_quotation(request, obj.quotation):
                raise PermissionDenied(
                    detail="Solo el vendedor de la cotización o un administrador pueden modificar sus líneas."
                )
