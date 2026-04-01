from rest_framework import permissions, viewsets

from accounts.permissions import AlmacenWritePermission, is_admin_access

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

    def get_queryset(self):
        qs = Client.objects.all().order_by("id")
        user = self.request.user
        if is_admin_access(user):
            return qs
        return qs.filter(contacts__user=user).distinct()

    def perform_create(self, serializer):
        serializer.save()


class PaymentMethodsViewSet(MaestroCatalogViewSet):
    queryset = PaymentMethods.objects.all().order_by("id")
    serializer_class = PaymentMethodsSerializer
