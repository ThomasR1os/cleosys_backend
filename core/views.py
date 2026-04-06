from rest_framework import permissions, viewsets

from accounts.permissions import AlmacenWritePermission, company_id_for_user

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
        if user.is_superuser:
            return qs
        company_id = company_id_for_user(user)
        if company_id is None:
            return qs.none()
        # Solo clientes con al menos un contacto registrado en la empresa del usuario.
        return qs.filter(contacts__company_id=company_id).distinct()

    def perform_create(self, serializer):
        serializer.save()


class PaymentMethodsViewSet(MaestroCatalogViewSet):
    queryset = PaymentMethods.objects.all().order_by("id")
    serializer_class = PaymentMethodsSerializer
