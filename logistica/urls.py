from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import LogisticTaskViewSet

router = DefaultRouter()
router.register(r"logistic-tasks", LogisticTaskViewSet, basename="logistica-task")

urlpatterns = [
    path("", include(router.urls)),
]
