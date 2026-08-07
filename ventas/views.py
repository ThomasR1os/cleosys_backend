from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from accounts.permissions import company_id_for_user, is_admin_access

from .models import ClientContact, ProformaRequest, Quotation, QuotationProduct
from .quotation_email import SmtpSendError, send_quotation_email
from .serializers import (
    ClientContactSerializer,
    ProformaRequestSerializer,
    QuotationProductSerializer,
    QuotationSendEmailSerializer,
    QuotationSerializer,
    UserPublicSummarySerializer,
)


User = get_user_model()


def filter_quotation_queryset_for_user(qs: QuerySet[Quotation], user) -> QuerySet[Quotation]:
    """
    Lectura (listado y detalle): todos los usuarios con empresa ven las cotizaciones de su compañía.
    Superusuario: todas. Sin empresa en perfil: ninguna.

    La edición no se gobierna aquí: ver `can_edit_quotation` + check_object_permissions en los viewsets.
    """
    if user.is_superuser:
        return qs
    company_id = company_id_for_user(user)
    if company_id is None:
        return qs.none()
    return qs.filter(user__profile__company_id=company_id)


def can_edit_quotation(request, quotation: Quotation) -> bool:
    """Modificar o eliminar cotización / sus líneas: dueño o administrador de app (o superusuario)."""
    u = request.user
    if not u.is_authenticated:
        return False
    if u.is_superuser or is_admin_access(u):
        return True
    return quotation.user_id == u.id


class BaseVentasViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]


class ClientContactViewSet(BaseVentasViewSet):
    queryset = ClientContact.objects.all().order_by("id")
    serializer_class = ClientContactSerializer

    def get_queryset(self):
        qs = (
            ClientContact.objects.select_related("user", "client", "company")
            .all()
            .order_by("id")
        )
        user = self.request.user
        if user.is_superuser:
            return qs
        company_id = company_id_for_user(user)
        if company_id is None:
            return qs.none()
        return qs.filter(company_id=company_id)

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in permissions.SAFE_METHODS:
            if request.user.is_superuser or is_admin_access(request.user):
                return
            if obj.user_id != request.user.id:
                raise PermissionDenied(
                    detail="Solo el vendedor asignado o un administrador pueden modificar o eliminar este contacto."
                )

    def perform_create(self, serializer):
        serializer.save()


class QuotationViewSet(BaseVentasViewSet):
    queryset = Quotation.objects.all().order_by("id")
    serializer_class = QuotationSerializer

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("client", "client_contact", "user", "user__profile", "payment_methods")
        )
        return filter_quotation_queryset_for_user(qs, self.request.user)

    def perform_create(self, serializer):
        if is_admin_access(self.request.user):
            serializer.save()
        else:
            serializer.save(user_id=self.request.user.pk)

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in permissions.SAFE_METHODS:
            # send-email: cualquiera de la compañía que pueda ver la cotización
            if getattr(self, "action", None) == "send_email":
                return
            if not can_edit_quotation(request, obj):
                raise PermissionDenied(
                    detail="Solo el vendedor que creó la cotización o un administrador pueden modificarla o eliminarla."
                )

    @action(detail=True, methods=["post"], url_path="send-email")
    def send_email(self, request, pk=None):
        quotation = self.get_object()
        serializer = QuotationSendEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            result = send_quotation_email(
                quotation=quotation,
                sender=request.user,
                to=data.get("to"),
                cc=data.get("cc"),
                subject=data.get("subject"),
                message=data.get("message") or "",
                html_message=data.get("html_message") or None,
                signature_url=data.get("signature_url") or None,
                pdf_base64=data["pdf_base64"],
                pdf_filename=data.get("pdf_filename"),
            )
        except SmtpSendError as exc:
            payload = {"detail": f"Error al enviar el correo: {exc}"}
            if exc.log_id:
                payload["log_id"] = exc.log_id
            return Response(payload, status=status.HTTP_502_BAD_GATEWAY)
        return Response(result, status=status.HTTP_200_OK)


class QuotationProductViewSet(BaseVentasViewSet):
    queryset = QuotationProduct.objects.select_related("product", "quotation").order_by("id")
    serializer_class = QuotationProductSerializer

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "product",
            "quotation__user",
            "quotation__user__profile",
        )
        visible = filter_quotation_queryset_for_user(Quotation.objects.all(), self.request.user)
        return qs.filter(quotation__in=visible)

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in permissions.SAFE_METHODS:
            if not can_edit_quotation(request, obj.quotation):
                raise PermissionDenied(
                    detail="Solo el vendedor de la cotización o un administrador pueden modificar sus líneas."
                )


class ProformaRequestViewSet(BaseVentasViewSet):
    queryset = ProformaRequest.objects.select_related(
        "company", "client", "assigned_user", "quotation"
    ).order_by("-entered_at", "-id")
    serializer_class = ProformaRequestSerializer

    def get_queryset(self):
        qs = (
            ProformaRequest.objects.select_related(
                "company", "client", "assigned_user", "quotation",
            )
            .order_by("-entered_at", "-id")
        )
        user = self.request.user
        if user.is_superuser:
            return qs
        cid = company_id_for_user(user)
        if cid is None:
            return qs.none()
        return qs.filter(company_id=cid)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["company_id"] = company_id_for_user(self.request.user)
        return ctx

    def perform_create(self, serializer):
        cid = company_id_for_user(self.request.user)
        if cid is None:
            raise ValidationError(
                {
                    "company": "Su usuario no tiene empresa asignada; no puede crear solicitudes de proforma."
                }
            )
        serializer.save(company_id=cid)

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in permissions.SAFE_METHODS:
            if request.user.is_superuser or is_admin_access(request.user):
                return
            if obj.assigned_user_id != request.user.id:
                raise PermissionDenied(
                    detail="Solo el asesor asignado o un administrador pueden modificar o eliminar esta solicitud."
                )

    @action(detail=False, methods=["get"], url_path="assignable-users")
    def assignable_users(self, request):
        cid = company_id_for_user(request.user)
        if cid is None:
            return Response([])
        users = (
            User.objects.filter(profile__company_id=cid)
            .select_related("profile")
            .order_by("id")
        )
        return Response(UserPublicSummarySerializer(users, many=True).data)
