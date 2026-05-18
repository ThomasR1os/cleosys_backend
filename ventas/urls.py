from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ClientContactViewSet,
    ProformaRequestViewSet,
    QuotationProductViewSet,
    QuotationViewSet,
)

router = DefaultRouter()
router.register(r"client-contacts", ClientContactViewSet, basename="ventas-client-contact")
router.register(r"quotations", QuotationViewSet, basename="ventas-quotation")
router.register(r"quotation-products", QuotationProductViewSet, basename="ventas-quotation-product")
router.register(r"proforma-requests", ProformaRequestViewSet, basename="ventas-proforma-request")

urlpatterns = [
    path("", include(router.urls)),
]
