from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ClientContactViewSet, QuotationProductViewSet, QuotationViewSet

router = DefaultRouter()
router.register(r"client-contacts", ClientContactViewSet, basename="ventas-client-contact")
router.register(r"quotations", QuotationViewSet, basename="ventas-quotation")
router.register(r"quotation-products", QuotationProductViewSet, basename="ventas-quotation-product")

urlpatterns = [
    path("", include(router.urls)),
]
