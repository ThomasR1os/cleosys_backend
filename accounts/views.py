from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework.exceptions import PermissionDenied

from almacen.cloudinary_upload import upload_product_image

from .email_sending import send_with_company_smtp
from .models import Company, CompanyBranding, CompanyEmailSettings, UserProfile
from .permissions import AdminAccessPermission, AdminUserOrSelfPermission, company_id_for_user, is_admin_access
from .serializers import (
    AdminSetPasswordSerializer,
    AdminUserListSerializer,
    AdminUserSelfPatchSerializer,
    AdminUserWriteSerializer,
    CompanyBrandingPatchSerializer,
    CompanyEmailSettingsSerializer,
    CompanyEmailTestSerializer,
    CompanySerializer,
    RegisterSerializer,
    UserProfileSerializer,
    UserSelfUpdateSerializer,
    UserSerializer,
)
from .utils import get_or_create_profile_for_user

User = get_user_model()


def get_or_create_my_profile(request):
    """Perfil del usuario autenticado (crea uno mínimo si no existe)."""
    return get_or_create_profile_for_user(request.user)


class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=201)


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = UserProfile.objects.filter(user=request.user).select_related("company").first()
        return Response(
            {
                "user": UserSerializer(request.user).data,
                "profile": UserProfileSerializer(profile).data if profile else None,
            }
        )

    def patch(self, request):
        user = request.user
        data = request.data if isinstance(request.data, dict) else {}
        if "user" in data and isinstance(data.get("user"), dict):
            u_ser = UserSelfUpdateSerializer(user, data=data["user"], partial=True, context={"request": request})
            u_ser.is_valid(raise_exception=True)
            u_ser.save()
        if "profile" in data and isinstance(data.get("profile"), dict):
            profile_payload = dict(data["profile"])
        else:
            profile_payload = {k: v for k, v in data.items()}
            profile_payload.pop("user", None)
        profile = get_or_create_my_profile(request)
        if profile_payload:
            p_ser = UserProfileSerializer(
                profile,
                data=profile_payload,
                partial=True,
                context={"request": request},
            )
            p_ser.is_valid(raise_exception=True)
            p_ser.save()
        user.refresh_from_db()
        profile.refresh_from_db()
        return Response(
            {
                "user": UserSerializer(user).data,
                "profile": UserProfileSerializer(profile).data,
            }
        )

    def put(self, request):
        return self.patch(request)


def _me_payload(user, profile):
    return {
        "user": UserSerializer(user).data,
        "profile": UserProfileSerializer(profile).data if profile else None,
    }


class MeSignatureUploadView(APIView):
    """
    POST multipart/form-data: file (imagen de firma).
    Sube a Cloudinary en cleosys/companies/{company_id}/users/{user_id} y guarda signature_url.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"detail": "Falta el campo file (multipart)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        profile = get_or_create_my_profile(request)
        folder = f"cleosys/companies/{profile.company_id}/users/{request.user.pk}"
        try:
            result = upload_product_image(upload, folder=folder)
        except RuntimeError as e:
            return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            return Response(
                {"detail": f"Error al subir a Cloudinary: {e}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        secure_url = result.get("secure_url") or result.get("url")
        if not secure_url:
            return Response(
                {"detail": "Cloudinary no devolvió URL."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        profile.signature_url = str(secure_url)[:500]
        profile.save(update_fields=["signature_url"])
        profile.refresh_from_db()
        return Response(_me_payload(request.user, profile))

    def delete(self, request):
        profile = get_or_create_my_profile(request)
        profile.signature_url = ""
        profile.save(update_fields=["signature_url"])
        return Response(_me_payload(request.user, profile))


class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.select_related("branding").all().order_by("id")
    serializer_class = CompanySerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(
        detail=True,
        methods=["patch"],
        url_path="branding",
        permission_classes=[permissions.IsAuthenticated, AdminAccessPermission],
    )
    def branding(self, request, pk=None):
        """
        Actualiza solo la paleta PDF. Crea CompanyBranding en el primer PATCH si no existía.
        Respuesta: mismo cuerpo que GET /companies/{id}/ (incluye branding completo).
        """
        company = self.get_object()
        branding, _ = CompanyBranding.objects.get_or_create(company=company)
        serializer = CompanyBrandingPatchSerializer(branding, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        company = Company.objects.select_related("branding").get(pk=company.pk)
        return Response(CompanySerializer(company).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="upload_logo",
        permission_classes=[permissions.IsAuthenticated, AdminAccessPermission],
    )
    def upload_logo(self, request, pk=None):
        """
        POST multipart/form-data: file (imagen). Sube a Cloudinary y guarda la URL en logo_url.
        Mismo criterio que /api/almacen/product-images/upload/.
        """
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"detail": "Falta el campo file (multipart)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        company = self.get_object()
        try:
            result = upload_product_image(upload, folder="cleosys/companies")
        except RuntimeError as e:
            return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            return Response(
                {"detail": f"Error al subir a Cloudinary: {e}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        secure_url = result.get("secure_url") or result.get("url")
        if not secure_url:
            return Response(
                {"detail": "Cloudinary no devolvió URL."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        company.logo_url = str(secure_url)[:500]
        company.save(update_fields=["logo_url"])
        return Response(CompanySerializer(company).data)

    def _ensure_admin_company_access(self, request, company: Company) -> None:
        if request.user.is_superuser:
            return
        cid = company_id_for_user(request.user)
        if cid is None or cid != company.pk:
            raise PermissionDenied(
                detail="Solo puede gestionar el correo saliente de su propia empresa."
            )

    @action(
        detail=True,
        methods=["get", "patch"],
        url_path="email-settings",
        permission_classes=[permissions.IsAuthenticated, AdminAccessPermission],
    )
    def email_settings(self, request, pk=None):
        company = self.get_object()
        self._ensure_admin_company_access(request, company)
        settings_obj, _ = CompanyEmailSettings.objects.get_or_create(company=company)
        if request.method == "GET":
            return Response(CompanyEmailSettingsSerializer(settings_obj).data)
        serializer = CompanyEmailSettingsSerializer(
            settings_obj, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        settings_obj.refresh_from_db()
        return Response(CompanyEmailSettingsSerializer(settings_obj).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="email-settings/test",
        permission_classes=[permissions.IsAuthenticated, AdminAccessPermission],
    )
    def email_settings_test(self, request, pk=None):
        company = self.get_object()
        self._ensure_admin_company_access(request, company)
        body = CompanyEmailTestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            settings_obj = CompanyEmailSettings.objects.get(company=company)
        except CompanyEmailSettings.DoesNotExist:
            return Response(
                {"detail": "Configure primero el SMTP de la empresa."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not settings_obj.host or not settings_obj.from_email:
            return Response(
                {"detail": "host y from_email son obligatorios para probar el envío."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not settings_obj.password_configured:
            return Response(
                {"detail": "Configure la contraseña SMTP antes de probar."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            send_with_company_smtp(
                settings_obj,
                to=[body.validated_data["to"]],
                subject=f"Prueba SMTP — {company.name}",
                body="Este es un correo de prueba de la configuración SMTP de Cleosys.",
            )
        except Exception as exc:
            return Response(
                {"detail": f"Error al enviar: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"status": "sent", "to": [body.validated_data["to"]]})


class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all().select_related("user", "company").order_by("id")
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated, AdminAccessPermission]


class AdminUserViewSet(viewsets.ModelViewSet):
    """
    Gestión unificada (admin): User + UserProfile.
    Ruta recomendada: /api/accounts/users/
    """

    permission_classes = [permissions.IsAuthenticated, AdminUserOrSelfPermission]

    def get_queryset(self):
        return (
            User.objects.all()
            .select_related("profile", "profile__company")
            .order_by("id")
        )

    def get_serializer_class(self):
        if self.action in ("list", "retrieve"):
            return AdminUserListSerializer
        return AdminUserWriteSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if str(request.user.pk) == str(kwargs.get("pk")) and not is_admin_access(request.user):
            serializer = AdminUserSelfPatchSerializer(
                instance, data=request.data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if str(request.user.pk) == str(kwargs.get("pk")) and not is_admin_access(request.user):
            serializer = AdminUserSelfPatchSerializer(
                instance, data=request.data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request, pk=None):
        user = self.get_object()
        serializer = AdminSetPasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])
        return Response(status=204)


class MyProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserProfileSerializer

    def get_object(self):
        return get_or_create_my_profile(self.request)
