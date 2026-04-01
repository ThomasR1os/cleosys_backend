from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BrandViewSet,
    CategoryProductViewSet,
    ClientViewSet,
    PaymentMethodsViewSet,
    SubcategoryProductViewSet,
    SupplierViewSet,
    TypeProductViewSet,
    UnitMeasurementViewSet,
)

router = DefaultRouter()
router.register(r"suppliers", SupplierViewSet, basename="supplier")
router.register(r"brands", BrandViewSet, basename="brand")
router.register(r"categories", CategoryProductViewSet, basename="category-product")
router.register(r"subcategories", SubcategoryProductViewSet, basename="subcategory-product")
router.register(r"types", TypeProductViewSet, basename="type-product")
router.register(r"units", UnitMeasurementViewSet, basename="unit-measurement")
router.register(r"clients", ClientViewSet, basename="client")
router.register(r"payment-methods", PaymentMethodsViewSet, basename="payment-methods")

urlpatterns = [
    path("", include(router.urls)),
]

