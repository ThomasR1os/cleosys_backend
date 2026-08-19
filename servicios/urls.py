from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import MachineViewSet

router = DefaultRouter()
router.register(r"machines", MachineViewSet, basename="servicios-machine")

urlpatterns = [
    path("", include(router.urls)),
]
