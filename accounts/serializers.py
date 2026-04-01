from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.db.utils import OperationalError
from rest_framework import serializers

from .models import Company, UserProfile
from .permissions import can_edit_sensitive_profile_fields
from .utils import get_or_create_profile_for_user

User = get_user_model()


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ["id", "name", "logo_url", "bank_accounts"]


class UserSerializer(serializers.ModelSerializer):
    cellphone = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "cellphone"]

    def get_cellphone(self, obj):
        try:
            return (obj.profile.cellphone or "").strip()
        except UserProfile.DoesNotExist:
            return ""


class UserSelfUpdateSerializer(serializers.ModelSerializer):
    """PATCH del usuario autenticado: sin username ni privilegios."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        extra_kwargs = {
            "first_name": {"required": False, "allow_blank": True},
            "last_name": {"required": False, "allow_blank": True},
            "email": {"required": False, "allow_blank": True},
        }


class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    company = CompanySerializer(read_only=True)
    company_id = serializers.IntegerField(write_only=True, required=False)
    user_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = UserProfile
        fields = [
            "id",
            "user",
            "company",
            "company_id",
            "user_id",
            "quotation_prefix",
            "role",
            "cellphone",
        ]

    def validate_quotation_prefix(self, value: str) -> str:
        if value is None or value == "":
            return ""
        v = value.strip().upper()
        if not (2 <= len(v) <= 10):
            raise serializers.ValidationError("Use entre 2 y 10 letras.")
        if not v.isalpha():
            raise serializers.ValidationError("Solo letras (sin espacios ni números).")
        return v

    def validate(self, attrs):
        if self.instance is None:
            if attrs.get("user_id") is None or attrs.get("company_id") is None:
                raise serializers.ValidationError(
                    "En creación deben enviarse user_id y company_id."
                )
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if "role" in attrs and not can_edit_sensitive_profile_fields(user):
            raise serializers.ValidationError(
                {"role": "Solo administradores pueden asignar o cambiar el rol."}
            )
        if "company_id" in attrs and not can_edit_sensitive_profile_fields(user):
            raise serializers.ValidationError(
                {"company_id": "No puede cambiar la compañía desde este perfil."}
            )
        return attrs

    def create(self, validated_data):
        user_id = validated_data.pop("user_id")
        company_id = validated_data.pop("company_id")
        return UserProfile.objects.create(user_id=user_id, company_id=company_id, **validated_data)

    def update(self, instance: UserProfile, validated_data):
        validated_data.pop("user_id", None)
        return super().update(instance, validated_data)


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    last_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    email = serializers.EmailField(required=False, allow_blank=True)
    company_id = serializers.IntegerField(required=False)
    cellphone = serializers.CharField(max_length=20, allow_blank=True, required=False)

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate_company_id(self, value: int) -> int:
        try:
            if not Company.objects.filter(id=value).exists():
                raise serializers.ValidationError("Company no existe.")
        except OperationalError:
            return value
        return value

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        company_id = validated_data.pop("company_id", None)
        cellphone = validated_data.pop("cellphone", "")

        user = User(**validated_data)
        user.set_password(password)
        user.save()

        if company_id is not None:
            try:
                UserProfile.objects.create(user=user, company_id=company_id, cellphone=cellphone or "")
            except OperationalError:
                # Tabla `company`/DB aún no lista en dev.
                pass
        return user


def _normalize_quotation_prefix(value: str) -> str:
    if value is None or value == "":
        return ""
    v = value.strip().upper()
    if not (2 <= len(v) <= 10):
        raise serializers.ValidationError("Use entre 2 y 10 letras.")
    if not v.isalpha():
        raise serializers.ValidationError("Solo letras (sin espacios ni números).")
    return v


class UserProfileNestedSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)

    class Meta:
        model = UserProfile
        fields = ["id", "company", "quotation_prefix", "role", "cellphone"]


class AdminUserListSerializer(serializers.ModelSerializer):
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_superuser",
            "profile",
        ]

    def get_profile(self, obj):
        try:
            profile = obj.profile
        except UserProfile.DoesNotExist:
            return None
        return UserProfileNestedSerializer(profile, context=self.context).data


class AdminUserSelfPatchSerializer(serializers.Serializer):
    """
    Usuario autenticado editando su propio registro vía PATCH/PUT /accounts/users/<id>/.
    Sin username, contraseña, is_active, empresa ni rol.
    """

    email = serializers.EmailField(required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    quotation_prefix = serializers.CharField(required=False, allow_blank=True)
    cellphone = serializers.CharField(max_length=20, required=False, allow_blank=True)

    def validate_quotation_prefix(self, value: str) -> str:
        if value is None or value == "":
            return ""
        return _normalize_quotation_prefix(value)

    def update(self, instance, validated_data):
        quotation_prefix = validated_data.pop("quotation_prefix", None)
        cellphone = validated_data.pop("cellphone", None)
        if validated_data:
            for field, value in validated_data.items():
                setattr(instance, field, value)
            instance.save()
        if quotation_prefix is not None or cellphone is not None:
            profile = get_or_create_profile_for_user(instance)
            to_save = []
            if quotation_prefix is not None:
                profile.quotation_prefix = quotation_prefix
                to_save.append("quotation_prefix")
            if cellphone is not None:
                profile.cellphone = (cellphone or "").strip()
                to_save.append("cellphone")
            if to_save:
                profile.save(update_fields=to_save)
        return instance

    def to_representation(self, instance):
        return AdminUserListSerializer(instance, context=self.context).data


class AdminUserWriteSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    company_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    role = serializers.ChoiceField(choices=UserProfile.Role.choices, write_only=True, required=False)
    quotation_prefix = serializers.CharField(write_only=True, required=False, allow_blank=True)
    cellphone = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=20)

    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "password",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "company_id",
            "role",
            "quotation_prefix",
            "cellphone",
            "profile",
        ]
        extra_kwargs = {
            "username": {"required": True},
            "email": {"required": False, "allow_blank": True},
            "first_name": {"required": False, "allow_blank": True},
            "last_name": {"required": False, "allow_blank": True},
            "is_active": {"required": False},
        }

    def get_profile(self, obj):
        try:
            profile = obj.profile
        except UserProfile.DoesNotExist:
            return None
        return UserProfileNestedSerializer(profile, context=self.context).data

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate_quotation_prefix(self, value: str) -> str:
        return _normalize_quotation_prefix(value)

    def validate_company_id(self, value: int | None) -> int | None:
        if value is None:
            return None
        try:
            if not Company.objects.filter(id=value).exists():
                raise serializers.ValidationError("Company no existe.")
        except OperationalError:
            return value
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if "role" in attrs and not can_edit_sensitive_profile_fields(user):
            raise serializers.ValidationError(
                {"role": "Solo administradores pueden asignar o cambiar el rol."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        company_id = validated_data.pop("company_id", None)
        role = validated_data.pop("role", None)
        quotation_prefix = validated_data.pop("quotation_prefix", None)
        cellphone = validated_data.pop("cellphone", None)

        user = User(**validated_data)
        user.set_password(password)
        user.save()

        if company_id is not None:
            try:
                profile_kwargs = {}
                if role is not None:
                    profile_kwargs["role"] = role
                if quotation_prefix is not None:
                    profile_kwargs["quotation_prefix"] = _normalize_quotation_prefix(quotation_prefix)
                if cellphone is not None:
                    profile_kwargs["cellphone"] = (cellphone or "").strip()
                UserProfile.objects.create(user=user, company_id=company_id, **profile_kwargs)
            except OperationalError:
                pass

        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        company_id = validated_data.pop("company_id", None)
        role = validated_data.pop("role", None)
        quotation_prefix = validated_data.pop("quotation_prefix", None)
        cellphone = validated_data.pop("cellphone", None)
        password = validated_data.pop("password", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        if password:
            instance.set_password(password)

        instance.save()

        if (
            company_id is not None
            or role is not None
            or quotation_prefix is not None
            or cellphone is not None
        ):
            try:
                profile = UserProfile.objects.filter(user=instance).first()
                if profile is None:
                    if company_id is None:
                        raise serializers.ValidationError(
                            {"company_id": "Para crear perfil debe enviarse company_id."}
                        )
                    profile = UserProfile.objects.create(user=instance, company_id=company_id)
                else:
                    if company_id is not None:
                        profile.company_id = company_id

                if role is not None:
                    profile.role = role
                if quotation_prefix is not None:
                    profile.quotation_prefix = _normalize_quotation_prefix(quotation_prefix)
                if cellphone is not None:
                    profile.cellphone = (cellphone or "").strip()
                profile.save()
            except OperationalError:
                pass

        return instance


class AdminSetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value
