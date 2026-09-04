from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import MachineReportViewSet, MachineViewSet, ReportPhotoUploadView

router = DefaultRouter()
router.register(r"machines", MachineViewSet, basename="servicios-machine")
router.register(r"reports", MachineReportViewSet, basename="servicios-report")

urlpatterns = [
    path("report-photos/upload/", ReportPhotoUploadView.as_view(), name="servicios-report-photo-upload"),
    path("", include(router.urls)),
]
