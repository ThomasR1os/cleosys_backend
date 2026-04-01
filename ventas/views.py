from rest_framework import permissions, viewsets

from accounts.permissions import is_admin_access

from .models import ClientContact, Quotation, QuotationProduct
from .serializers import ClientContactSerializer, QuotationProductSerializer, QuotationSerializer


class BaseVentasViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]


class ClientContactViewSet(BaseVentasViewSet):
    queryset = ClientContact.objects.all().order_by("id")
    serializer_class = ClientContactSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if is_admin_access(user):
            return qs
        return qs.filter(user=user)

    def perform_create(self, serializer):
        if is_admin_access(self.request.user):
            serializer.save()
        else:
            serializer.save(user_id=self.request.user.pk)


class QuotationViewSet(BaseVentasViewSet):
    queryset = Quotation.objects.all().order_by("id")
    serializer_class = QuotationSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if is_admin_access(self.request.user):
            return qs
        return qs.filter(user=self.request.user)

    def perform_create(self, serializer):
        if is_admin_access(self.request.user):
            serializer.save()
        else:
            serializer.save(user_id=self.request.user.pk)


class QuotationProductViewSet(BaseVentasViewSet):
    queryset = QuotationProduct.objects.select_related("product", "quotation").order_by("id")
    serializer_class = QuotationProductSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if is_admin_access(self.request.user):
            return qs
        return qs.filter(quotation__user=self.request.user)
