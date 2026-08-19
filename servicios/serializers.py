from rest_framework import serializers

from accounts.permissions import company_id_for_user
from core.models import Client
from ventas.models import ClientContact

from .models import Machine


class MachineSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    # Write-only for superusers without a company profile.
    company_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Machine
        fields = [
            "id",
            "company",
            "company_id",
            "client",
            "client_name",
            "brand",
            "brand_name",
            "model",
            "serial_number",
            "plate_image_url",
            "daily_working_hours",
            "current_hour_meter",
            "location",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "company", "created_at", "updated_at"]

    def _resolve_company_id(self, attrs) -> int | None:
        if self.instance is not None:
            return self.instance.company_id

        ctx_cid = self.context.get("company_id")
        if ctx_cid is not None:
            return ctx_cid

        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            cid = company_id_for_user(request.user)
            if cid is not None:
                return cid
            if request.user.is_superuser:
                return attrs.get("company_id")

        return attrs.get("company_id")

    def _validate_client_belongs_to_company(self, client_obj: Client, company_id: int) -> None:
        if not ClientContact.objects.filter(company_id=company_id, client_id=client_obj.pk).exists():
            raise serializers.ValidationError(
                {
                    "client": (
                        "El cliente no está vinculado a su compañía "
                        "(agregue un contacto para ese cliente)."
                    )
                }
            )

    def validate(self, attrs):
        company_id = self._resolve_company_id(attrs)
        if company_id is None:
            raise serializers.ValidationError(
                {
                    "company": (
                        "Su usuario no tiene empresa asignada; "
                        "indique company_id (superusuario) o asigne un perfil."
                    )
                }
            )

        client_obj = attrs.get("client")
        if client_obj is None and self.instance is not None:
            client_obj = self.instance.client
        if client_obj is not None:
            self._validate_client_belongs_to_company(client_obj, company_id)

        serial = attrs.get("serial_number")
        if serial is None and self.instance is not None:
            serial = self.instance.serial_number
        if serial is not None:
            qs = Machine.objects.filter(company_id=company_id, serial_number=serial)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {
                        "serial_number": (
                            "Ya existe una máquina con este número de serie en su compañía."
                        )
                    }
                )

        attrs["_resolved_company_id"] = company_id
        return attrs

    def create(self, validated_data):
        company_id = validated_data.pop("_resolved_company_id")
        validated_data.pop("company_id", None)
        validated_data["company_id"] = company_id
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("_resolved_company_id", None)
        validated_data.pop("company_id", None)
        return super().update(instance, validated_data)
