from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied

from accounts.permissions import company_id_for_user, is_admin_access

from .models import ClientContact, Quotation, QuotationProduct
from .serializers import ClientContactSerializer, QuotationProductSerializer, QuotationSerializer


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
        # `user` en select_related evita N+1 al serializar `user_detail` en listados.
        qs = super().get_queryset().select_related("client", "user", "payment_methods")
        user = self.request.user
        if user.is_superuser:
            return qs
        company_id = company_id_for_user(user)
        if company_id is None:
            return qs.none()
        return qs.filter(user__profile__company_id=company_id)

    def perform_create(self, serializer):
        if is_admin_access(self.request.user):
            serializer.save()
        else:
            serializer.save(user_id=self.request.user.pk)


class QuotationProductViewSet(BaseVentasViewSet):
    queryset = QuotationProduct.objects.select_related("product", "quotation").order_by("id")
    serializer_class = QuotationProductSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related("quotation__user")
        user = self.request.user
        if user.is_superuser:
            return qs
        company_id = company_id_for_user(user)
        if company_id is None:
            return qs.none()
        return qs.filter(quotation__user__profile__company_id=company_id)
