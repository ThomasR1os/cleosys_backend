from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ProductImageUploadView,
    ProductImageViewSet,
    ProductSupplierViewSet,
    ProductViewSet,
    WarehouseMovementsViewSet,
    WarehouseProductViewSet,
    WarehouseViewSet,
)

router = DefaultRouter()
router.register(r"products", ProductViewSet, basename="almacen-product")
router.register(r"product-images", ProductImageViewSet, basename="almacen-product-image")
router.register(r"product-suppliers", ProductSupplierViewSet, basename="almacen-product-supplier")
router.register(r"warehouses", WarehouseViewSet, basename="almacen-warehouse")
router.register(r"warehouse-movements", WarehouseMovementsViewSet, basename="almacen-warehouse-movement")
router.register(r"warehouse-products", WarehouseProductViewSet, basename="almacen-warehouse-product")

urlpatterns = [
    path("product-images/upload/", ProductImageUploadView.as_view(), name="almacen-product-image-upload"),
    path("", include(router.urls)),
]
