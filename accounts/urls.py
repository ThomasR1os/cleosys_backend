from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AdminUserViewSet, CompanyViewSet, MeView, MyProfileView, RegisterView, UserProfileViewSet

router = DefaultRouter()
router.register(r"companies", CompanyViewSet, basename="company")
router.register(r"profiles", UserProfileViewSet, basename="userprofile")
router.register(r"accounts/users", AdminUserViewSet, basename="admin-users")

urlpatterns = [
    path("", include(router.urls)),
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("auth/profile/", MyProfileView.as_view(), name="my-profile"),
]

