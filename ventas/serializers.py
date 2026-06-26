from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.models import UserProfile
from accounts.permissions import company_id_for_user, is_admin_access, resolve_contact_owner_user
from core.models import Client
from .models import ClientContact, ProformaRequest, Quotation, QuotationProduct

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


class QuotationUserDetailSerializer(UserPublicSummarySerializer):
    """Asesor de la cotización: nombre + correo y teléfono (perfil) para listado, detalle y PDF."""

    cellphone = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name", "nombre", "email", "cellphone")

    def get_cellphone(self, obj: User) -> str:
        profile = getattr(obj, "profile", None)
        if profile is None:
            profile = UserProfile.objects.filter(user_id=obj.pk).first()
        return (profile.cellphone or "").strip() if profile else ""


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
        if request is not None:
            if instance is None:
                attrs["user"] = resolve_contact_owner_user(request, attrs.get("user"))
            elif "user" in attrs:
                attrs["user"] = resolve_contact_owner_user(request, attrs.get("user"))
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
            fn_key = (first_name or "").strip()
            ln_key = (last_name or "").strip()
            qs_name = ClientContact.objects.filter(
                company_id=company_id,
                client_id=client_id,
                contact_first_name__iexact=fn_key,
                contact_last_name__iexact=ln_key,
            )
            qs_email = ClientContact.objects.filter(
                company_id=company_id,
                client_id=client_id,
            )
            if email and str(email).strip():
                qs_email = qs_email.filter(email__iexact=str(email).strip())
            else:
                qs_email = qs_email.none()
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


class QuotationClientContactReadSerializer(serializers.ModelSerializer):
    """
    Datos del contacto del cliente en la cotización.
    Nombre siempre visible para quien ve la cotización; email y teléfono solo si el mismo
    criterio que en client-contacts (admin, superusuario o vendedor asignado al contacto).
    """

    nombre = serializers.SerializerMethodField()

    class Meta:
        model = ClientContact
        fields = ("id", "contact_first_name", "contact_last_name", "nombre", "email", "phone")

    def get_nombre(self, obj: ClientContact) -> str:
        fn = (obj.contact_first_name or "").strip()
        ln = (obj.contact_last_name or "").strip()
        if fn or ln:
            return f"{fn} {ln}".strip()
        return ""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if user and not ClientContactSerializer._can_see_email_and_phone(user, instance):
            data["email"] = None
            data["phone"] = None
        return data


class QuotationClientReadSerializer(serializers.ModelSerializer):
    """Resumen del cliente embebido en la cotización (visible para toda la empresa)."""

    class Meta:
        model = Client
        fields = ("id", "ruc", "name")


class QuotationSerializer(serializers.ModelSerializer):
    """`user` sigue siendo el id del FK; `user_detail` incluye email y cellphone del asesor."""

    user_detail = QuotationUserDetailSerializer(source="user", read_only=True)
    client_detail = QuotationClientReadSerializer(source="client", read_only=True)
    client_contact = serializers.PrimaryKeyRelatedField(
        queryset=ClientContact.objects.all(),
        required=False,
        allow_null=True,
    )
    client_contact_detail = QuotationClientContactReadSerializer(
        source="client_contact",
        read_only=True,
    )

    class Meta:
        model = Quotation
        fields = (
            "id",
            "quotation_type",
            "money",
            "exchange_rate",
            "rental_unit",
            "rental_quantity",
            "status",
            "client",
            "client_detail",
            "client_contact",
            "client_contact_detail",
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
        client = attrs.get("client")
        if client is None and self.instance is not None:
            client = self.instance.client
        cc = attrs.get("client_contact")
        if cc is None and self.instance is not None:
            cc = self.instance.client_contact
        if cc is not None and client is not None and cc.client_id != client.pk:
            raise serializers.ValidationError(
                {"client_contact": "El contacto debe pertenecer al mismo cliente de la cotización."}
            )
        if cc is not None and request and not request.user.is_superuser:
            cid = company_id_for_user(request.user)
            if cid is not None and cc.company_id != cid:
                raise serializers.ValidationError(
                    {"client_contact": "El contacto no pertenece a su compañía."}
                )
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

        qtype = attrs.get("quotation_type") or (
            self.instance.quotation_type if self.instance else None
        )
        ru = attrs.get(
            "rental_unit",
            getattr(self.instance, "rental_unit", None) if self.instance else None,
        )
        rq = attrs.get(
            "rental_quantity",
            getattr(self.instance, "rental_quantity", None) if self.instance else None,
        )
        if qtype == Quotation.QuotationType.ALQUILER:
            if ru in (None, ""):
                raise serializers.ValidationError(
                    {"rental_unit": "Requerido cuando quotation_type es ALQUILER."}
                )
            if rq is None:
                raise serializers.ValidationError(
                    {"rental_quantity": "Requerido cuando quotation_type es ALQUILER."}
                )
            if rq < 1:
                raise serializers.ValidationError(
                    {"rental_quantity": "Debe ser >= 1."}
                )
        else:
            attrs["rental_unit"] = None
            attrs["rental_quantity"] = None
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
        raise serializers.ValidationError(
            "Solo puede añadir o editar líneas en cotizaciones propias (o como administrador)."
        )

    def validate(self, attrs):
        quotation = attrs.get("quotation")
        if quotation is None and self.instance is not None:
            quotation = self.instance.quotation
        delivery_time = attrs.get("delivery_time")
        if delivery_time is None and self.instance is not None and "delivery_time" not in attrs:
            delivery_time = self.instance.delivery_time
        if quotation is not None and quotation.quotation_type == Quotation.QuotationType.VENTA:
            if not (delivery_time or "").strip():
                raise serializers.ValidationError(
                    {"delivery_time": "Requerido cuando la cotización es de tipo VENTA."}
                )
        return attrs


class ProformaRequestSerializer(serializers.ModelSerializer):
    company = serializers.PrimaryKeyRelatedField(read_only=True)
    client_detail = QuotationClientReadSerializer(source="client", read_only=True)
    assigned_user_detail = UserPublicSummarySerializer(source="assigned_user", read_only=True)
    quotation_correlativo = serializers.SerializerMethodField()

    class Meta:
        model = ProformaRequest
        fields = (
            "id",
            "company",
            "client",
            "client_detail",
            "assigned_user",
            "assigned_user_detail",
            "entry_channel",
            "proforma_type",
            "description",
            "status",
            "quotation",
            "quotation_correlativo",
            "entered_at",
            "quoted_at",
        )
        extra_kwargs = {
            "quotation": {"allow_null": True, "required": False},
        }
        read_only_fields = ("entered_at", "quoted_at")

    def get_quotation_correlativo(self, obj: ProformaRequest) -> str | None:
        if not obj.quotation_id:
            return None
        return obj.quotation.correlativo if obj.quotation else None

    def _company_id_for_validation(self) -> int | None:
        if self.instance is not None:
            return self.instance.company_id
        cid = self.context.get("company_id")
        if cid is not None:
            return cid
        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            return company_id_for_user(request.user)
        return None

    def _validate_assigned_user_company(self, user_obj, company_id: int) -> None:
        if not UserProfile.objects.filter(user=user_obj, company_id=company_id).exists():
            raise serializers.ValidationError(
                {"assigned_user": "El asesor debe pertenecer a la misma compañía que la solicitud."}
            )

    def _validate_client_belongs_to_company(self, client_obj, company_id: int) -> None:
        if not ClientContact.objects.filter(company_id=company_id, client_id=client_obj.pk).exists():
            raise serializers.ValidationError(
                {
                    "client": "El cliente no está vinculado a su compañía (agregue un contacto para ese cliente)."
                }
            )

    def _validate_quotation_matches(self, quotation_obj, company_id: int, client_obj) -> None:
        prof = UserProfile.objects.filter(user_id=quotation_obj.user_id).first()
        q_company = prof.company_id if prof else None
        if q_company != company_id:
            raise serializers.ValidationError(
                {"quotation": "La cotización no pertenece a la misma compañía que la solicitud."}
            )
        if quotation_obj.client_id != client_obj.pk:
            raise serializers.ValidationError(
                {"quotation": "La cotización debe ser del mismo cliente que la solicitud."}
            )

    def validate(self, attrs):
        company_id = self._company_id_for_validation()
        if company_id is None:
            raise serializers.ValidationError(
                {"company": "Su usuario no tiene empresa asignada; no puede gestionar solicitudes de proforma."}
            )

        assigned = attrs.get("assigned_user")
        if assigned is None and self.instance is not None:
            assigned = self.instance.assigned_user

        client_obj = attrs.get("client")
        if client_obj is None and self.instance is not None:
            client_obj = self.instance.client

        if assigned is not None:
            self._validate_assigned_user_company(assigned, company_id)

        if client_obj is not None:
            self._validate_client_belongs_to_company(client_obj, company_id)

        quotation_obj = None
        if "quotation" in attrs:
            quotation_obj = attrs["quotation"]
            if quotation_obj is None:
                return attrs
        elif self.instance is not None:
            quotation_obj = self.instance.quotation

        if quotation_obj is not None and client_obj is not None:
            self._validate_quotation_matches(quotation_obj, company_id, client_obj)

        return attrs
