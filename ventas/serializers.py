from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.models import UserProfile
from accounts.permissions import company_id_for_user, is_admin_access
from .models import ClientContact, Quotation, QuotationProduct

User = get_user_model()


class UserPublicSummarySerializer(serializers.ModelSerializer):
    """
    Solo lectura: id, username, nombre y apellidos (mismo criterio que encargado en contactos).
    No incluye email ni otros campos sensibles del modelo User.
    """

    nombre = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name", "nombre")

    def get_nombre(self, obj: User) -> str:
        fn = (obj.first_name or "").strip()
        ln = (obj.last_name or "").strip()
        if fn or ln:
            return f"{fn} {ln}".strip()
        un = (obj.username or "").strip()
        if un:
            return un
        return str(obj.pk)


class ClientContactEncargadoSerializer(UserPublicSummarySerializer):
    """Vendedor asignado al contacto (visible para toda la empresa)."""


class ClientContactSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(read_only=True)
    encargado = ClientContactEncargadoSerializer(source="user", read_only=True)
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)

    class Meta:
        model = ClientContact
        fields = (
            "id",
            "contact_first_name",
            "contact_last_name",
            "email",
            "phone",
            "client",
            "user",
            "company",
            "encargado",
        )

    def _get_company_id_from_user(self, user_id: int):
        profile = UserProfile.objects.filter(user_id=user_id).first()
        if not profile:
            raise serializers.ValidationError(
                {"user": "El usuario no tiene company asignada en UserProfile."}
            )
        return profile.company_id

    def validate(self, attrs):
        request = self.context.get("request")
        instance = getattr(self, "instance", None)
        if request and not is_admin_access(request.user):
            if instance is None:
                attrs["user"] = request.user
            else:
                attrs.pop("user", None)
        u = attrs.get("user")
        if u is not None and hasattr(u, "pk"):
            user_id = u.pk
        else:
            user_id = instance.user_id if instance else None
        c = attrs.get("client")
        if c is not None and hasattr(c, "pk"):
            client_id = c.pk
        else:
            client_id = instance.client_id if instance else None
        first_name = attrs.get("contact_first_name") or (instance.contact_first_name if instance else None)
        last_name = attrs.get("contact_last_name") or (instance.contact_last_name if instance else None)
        email = attrs.get("email") or (instance.email if instance else None)

        if user_id and client_id and first_name and last_name:
            company_id = self._get_company_id_from_user(user_id)
            qs_name = ClientContact.objects.filter(
                company_id=company_id,
                client_id=client_id,
                contact_first_name=first_name,
                contact_last_name=last_name,
            )
            qs_email = ClientContact.objects.filter(
                company_id=company_id,
                client_id=client_id,
                email=email,
            )
            if instance is not None:
                qs_name = qs_name.exclude(pk=instance.pk)
                qs_email = qs_email.exclude(pk=instance.pk)
            if qs_name.exists():
                raise serializers.ValidationError(
                    "Este contacto ya existe para ese cliente dentro de la misma compania."
                )
            if email and qs_email.exists():
                raise serializers.ValidationError(
                    "Este correo ya existe para ese cliente dentro de la misma compania."
                )
        return attrs

    @staticmethod
    def _can_see_email_and_phone(request_user, instance: ClientContact) -> bool:
        if not request_user or not request_user.is_authenticated:
            return False
        if request_user.is_superuser:
            return True
        if is_admin_access(request_user):
            return True
        return instance.user_id == request_user.id

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if user and not self._can_see_email_and_phone(user, instance):
            data["email"] = None
            data["phone"] = None
        return data

    def create(self, validated_data):
        uid = None
        u = validated_data.get("user")
        if u is not None:
            uid = u.pk if hasattr(u, "pk") else u
        elif validated_data.get("user_id") is not None:
            uid = validated_data["user_id"]
        if uid is None:
            raise serializers.ValidationError({"user": "Este campo es requerido."})
        validated_data["company_id"] = self._get_company_id_from_user(uid)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        user_obj = validated_data.get("user", instance.user)
        validated_data["company_id"] = self._get_company_id_from_user(user_obj.pk)
        return super().update(instance, validated_data)


class QuotationSerializer(serializers.ModelSerializer):
    """`user` sigue siendo el id del FK; `user_detail` es aditivo y de solo lectura."""

    user_detail = UserPublicSummarySerializer(source="user", read_only=True)

    class Meta:
        model = Quotation
        fields = (
            "id",
            "quotation_type",
            "money",
            "exchange_rate",
            "status",
            "client",
            "user",
            "user_detail",
            "correlativo",
            "discount",
            "final_price",
            "delivery_time",
            "conditions",
            "payment_methods",
            "works",
            "see_sku",
            "creation_date",
            "update_date",
        )
        read_only_fields = ("correlativo",)

    def validate(self, attrs):
        request = self.context.get("request")
        if self.instance is None and request and not is_admin_access(request.user):
            attrs["user_id"] = request.user.pk
        if self.instance is None:
            uid = attrs.get("user_id")
            if uid is not None:
                profile = UserProfile.objects.filter(user_id=uid).first()
                if not profile or not (profile.quotation_prefix or "").strip():
                    raise serializers.ValidationError(
                        {
                            "user": "Configure el prefijo de cotizaciones (iniciales) en el perfil del usuario antes de crear cotizaciones."
                        }
                    )
        return attrs

    def update(self, instance, validated_data):
        request = self.context.get("request")
        if request and not is_admin_access(request.user):
            validated_data.pop("user_id", None)
        return super().update(instance, validated_data)


class QuotationProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuotationProduct
        fields = "__all__"

    def validate_quotation(self, value):
        request = self.context.get("request")
        if not request or is_admin_access(request.user):
            return value
        if value.user_id == request.user.id:
            return value
        viewer_company = company_id_for_user(request.user)
        if viewer_company is None:
            raise serializers.ValidationError(
                "No puede asociar lineas a cotizaciones de otro usuario."
            )
        owner = UserProfile.objects.filter(user_id=value.user_id).first()
        if not owner or owner.company_id != viewer_company:
            raise serializers.ValidationError(
                "No puede asociar lineas a cotizaciones fuera de su compania."
            )
        return value
