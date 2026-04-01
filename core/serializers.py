from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework import serializers

from accounts.models import UserProfile
from accounts.permissions import is_admin_access
from ventas.models import ClientContact

from .models import (
    Brand,
    CategoryProduct,
    Client,
    PaymentMethods,
    SubcategoryProduct,
    Supplier,
    TypeProduct,
    UnitMeasurement,
)

User = get_user_model()


class ClientContactWriteSerializer(serializers.ModelSerializer):
    """Datos del contacto; opcionalmente `user` (vendedor) solo para administradores."""

    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = ClientContact
        fields = ("contact_first_name", "contact_last_name", "email", "phone", "user")


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = "__all__"


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = "__all__"


class CategoryProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategoryProduct
        fields = "__all__"


class SubcategoryProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubcategoryProduct
        fields = "__all__"


class TypeProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeProduct
        fields = "__all__"


class UnitMeasurementSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitMeasurement
        fields = "__all__"


class ClientSerializer(serializers.ModelSerializer):
    """
    - POST: acepta `contact` obligatorio (cliente + primer contacto / vendedor en una operación).
    - El vendedor es el usuario del contacto (`contact.user`); por defecto quien crea el registro.
    """

    contact = ClientContactWriteSerializer(write_only=True, required=False)

    class Meta:
        model = Client
        fields = (
            "id",
            "ruc",
            "name",
            "contact",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is None:
            self.fields["contact"].required = True

    def validate_ruc(self, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("El RUC no puede estar vacío.")
        return v

    def validate(self, attrs):
        if self.instance is None:
            if not attrs.get("contact"):
                raise serializers.ValidationError(
                    {"contact": "Debe registrar el contacto junto con el cliente."}
                )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get("request")
        contact_data = validated_data.pop("contact")
        ruc = validated_data["ruc"].strip()
        name = validated_data["name"].strip()

        existing = Client.objects.filter(ruc=ruc).first()
        if existing is not None:
            if (existing.name or "").strip() != name:
                raise serializers.ValidationError(
                    {
                        "ruc": "Ya existe un cliente con este RUC; el nombre no coincide con el registrado."
                    }
                )
            client = existing
        else:
            client = Client.objects.create(ruc=ruc, name=name)

        serializer_cc = ClientContactWriteSerializer(data=contact_data)
        serializer_cc.is_valid(raise_exception=True)
        vd = dict(serializer_cc.validated_data)
        contact_user = vd.pop("user", None)
        if contact_user is None:
            contact_user = request.user if request else None
        elif request and not is_admin_access(request.user):
            contact_user = request.user
        if contact_user is None:
            raise serializers.ValidationError(
                {"contact": "No se pudo determinar el vendedor del contacto."}
            )
        if not UserProfile.objects.filter(user=contact_user).exists():
            raise serializers.ValidationError(
                {
                    "contact": {
                        "user": "El vendedor debe tener perfil (empresa) asignado."
                    }
                }
            )

        company_id = (
            UserProfile.objects.filter(user_id=contact_user.pk)
            .values_list("company_id", flat=True)
            .first()
        )
        if not company_id:
            raise serializers.ValidationError(
                {"contact": "El usuario del contacto no tiene empresa asignada en su perfil."}
            )

        try:
            ClientContact.objects.create(
                client=client,
                user_id=contact_user.pk,
                company_id=company_id,
                **vd,
            )
        except IntegrityError:
            raise serializers.ValidationError(
                {
                    "contact": "Ya existe ese contacto para este cliente en su empresa (nombre o correo duplicado)."
                }
            ) from None
        return client

    @transaction.atomic
    def update(self, instance, validated_data):
        validated_data.pop("contact", None)
        return super().update(instance, validated_data)


class PaymentMethodsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethods
        fields = "__all__"
