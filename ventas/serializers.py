from rest_framework import serializers

from accounts.models import UserProfile
from accounts.permissions import is_admin_access
from .models import ClientContact, Quotation, QuotationProduct


class ClientContactSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ClientContact
        fields = "__all__"

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
                attrs["user_id"] = request.user.pk
            else:
                attrs.pop("user_id", None)
        user_id = attrs.get("user_id") or (instance.user_id if instance else None)
        client_id = attrs.get("client_id") or (instance.client_id if instance else None)
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

    def create(self, validated_data):
        company_id = self._get_company_id_from_user(validated_data["user_id"])
        validated_data["company_id"] = company_id
        return super().create(validated_data)

    def update(self, instance, validated_data):
        target_user_id = validated_data.get("user_id", instance.user_id)
        validated_data["company_id"] = self._get_company_id_from_user(target_user_id)
        return super().update(instance, validated_data)


class QuotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quotation
        fields = "__all__"
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
        if request and not is_admin_access(request.user):
            if value.user_id != request.user.id:
                raise serializers.ValidationError(
                    "No puede asociar lineas a cotizaciones de otro usuario."
                )
        return value
