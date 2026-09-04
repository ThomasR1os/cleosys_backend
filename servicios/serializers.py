from rest_framework import serializers

from accounts.permissions import company_id_for_user
from core.models import Client, SubcategoryRecommendedPart
from ventas.models import ClientContact

from .models import (
    Machine,
    MachineElectricalEvaluation,
    MachineReport,
    MachineReportPartCheck,
    MachineReportPhoto,
    ReportElectricalEvaluation,
)


class MachineElectricalEvaluationSerializer(serializers.ModelSerializer):
    actual_voltage = serializers.SerializerMethodField()
    main_motor_current = serializers.SerializerMethodField()
    fan_motor_current = serializers.SerializerMethodField()

    class Meta:
        model = MachineElectricalEvaluation
        fields = [
            "id",
            "machine",
            "nominal_voltage",
            "actual_voltage",
            "main_motor_current",
            "fan_motor_current",
            "starter_type",
            "starter_brand",
            "control_voltage",
            "grounding",
            "created_at",
            "updated_at",
            # write-only flat phase fields (filled from nested objects)
            "actual_voltage_l1_l2",
            "actual_voltage_l2_l3",
            "actual_voltage_l3_l1",
            "main_motor_current_l1",
            "main_motor_current_l2",
            "main_motor_current_l3",
            "fan_motor_current_l1",
            "fan_motor_current_l2",
            "fan_motor_current_l3",
        ]
        read_only_fields = ["id", "machine", "created_at", "updated_at"]
        extra_kwargs = {
            "actual_voltage_l1_l2": {"write_only": True, "required": False, "allow_null": True},
            "actual_voltage_l2_l3": {"write_only": True, "required": False, "allow_null": True},
            "actual_voltage_l3_l1": {"write_only": True, "required": False, "allow_null": True},
            "main_motor_current_l1": {"write_only": True, "required": False, "allow_null": True},
            "main_motor_current_l2": {"write_only": True, "required": False, "allow_null": True},
            "main_motor_current_l3": {"write_only": True, "required": False, "allow_null": True},
            "fan_motor_current_l1": {"write_only": True, "required": False, "allow_null": True},
            "fan_motor_current_l2": {"write_only": True, "required": False, "allow_null": True},
            "fan_motor_current_l3": {"write_only": True, "required": False, "allow_null": True},
        }

    def get_attribute(self, instance):
        # Nested under Machine: missing 1:1 row → null instead of DoesNotExist.
        if isinstance(instance, Machine):
            try:
                return instance.electrical_evaluation
            except MachineElectricalEvaluation.DoesNotExist:
                return None
        return instance

    def get_actual_voltage(self, obj):
        return {
            "l1_l2": obj.actual_voltage_l1_l2,
            "l2_l3": obj.actual_voltage_l2_l3,
            "l3_l1": obj.actual_voltage_l3_l1,
        }

    def get_main_motor_current(self, obj):
        return {
            "l1": obj.main_motor_current_l1,
            "l2": obj.main_motor_current_l2,
            "l3": obj.main_motor_current_l3,
        }

    def get_fan_motor_current(self, obj):
        return {
            "l1": obj.fan_motor_current_l1,
            "l2": obj.fan_motor_current_l2,
            "l3": obj.fan_motor_current_l3,
        }

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {
                    "electrical_evaluation": (
                        "Formato inválido: se espera un objeto para electrical_evaluation."
                    )
                }
            )
        mutable = {**data}
        actual = mutable.pop("actual_voltage", None)
        if isinstance(actual, dict):
            if "l1_l2" in actual:
                mutable["actual_voltage_l1_l2"] = actual.get("l1_l2")
            if "l2_l3" in actual:
                mutable["actual_voltage_l2_l3"] = actual.get("l2_l3")
            if "l3_l1" in actual:
                mutable["actual_voltage_l3_l1"] = actual.get("l3_l1")

        main = mutable.pop("main_motor_current", None)
        if isinstance(main, dict):
            if "l1" in main:
                mutable["main_motor_current_l1"] = main.get("l1")
            if "l2" in main:
                mutable["main_motor_current_l2"] = main.get("l2")
            if "l3" in main:
                mutable["main_motor_current_l3"] = main.get("l3")

        fan = mutable.pop("fan_motor_current", None)
        if isinstance(fan, dict):
            if "l1" in fan:
                mutable["fan_motor_current_l1"] = fan.get("l1")
            if "l2" in fan:
                mutable["fan_motor_current_l2"] = fan.get("l2")
            if "l3" in fan:
                mutable["fan_motor_current_l3"] = fan.get("l3")

        return super().to_internal_value(mutable)


class MachineSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    client_name = serializers.CharField(source="client.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    subcategory_name = serializers.CharField(
        source="subcategory.name", read_only=True, allow_null=True
    )
    company_id = serializers.IntegerField(write_only=True, required=False)
    electrical_evaluation = MachineElectricalEvaluationSerializer(
        required=False, allow_null=True
    )

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
            "category",
            "category_name",
            "subcategory",
            "subcategory_name",
            "model",
            "serial_number",
            "plate_image_url",
            "daily_working_hours",
            "current_hour_meter",
            "location",
            "status",
            "electrical_evaluation",
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

        category = attrs.get("category")
        if category is None and self.instance is not None:
            category = self.instance.category
        subcategory = attrs.get("subcategory")
        if subcategory is None and self.instance is not None:
            subcategory = self.instance.subcategory
        if subcategory is not None and category is not None:
            if subcategory.category_id != category.pk:
                raise serializers.ValidationError(
                    {
                        "subcategory": (
                            "La subcategoría no pertenece a la categoría indicada."
                        )
                    }
                )
        elif subcategory is not None and category is None:
            raise serializers.ValidationError(
                {"category": "Debe indicar la categoría junto con la subcategoría."}
            )

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

    def _upsert_electrical(self, machine: Machine, electrical_data: dict | None) -> None:
        if electrical_data is None:
            return
        MachineElectricalEvaluation.objects.update_or_create(
            machine=machine,
            defaults=electrical_data,
        )

    def create(self, validated_data):
        company_id = validated_data.pop("_resolved_company_id")
        validated_data.pop("company_id", None)
        electrical_data = validated_data.pop("electrical_evaluation", None)
        validated_data["company_id"] = company_id
        machine = super().create(validated_data)
        self._upsert_electrical(machine, electrical_data)
        return machine

    def update(self, instance, validated_data):
        validated_data.pop("_resolved_company_id", None)
        validated_data.pop("company_id", None)
        electrical_data = validated_data.pop("electrical_evaluation", None)
        machine = super().update(instance, validated_data)
        self._upsert_electrical(machine, electrical_data)
        return machine


class MachineReportPartCheckSerializer(serializers.ModelSerializer):
    recommended_part_name = serializers.CharField(
        source="recommended_part.name", read_only=True
    )

    class Meta:
        model = MachineReportPartCheck
        fields = [
            "id",
            "recommended_part",
            "recommended_part_name",
            "condition",
            "part_number",
            "notes",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {
            # Front suele enviar null; en DB se guarda "".
            "notes": {"required": False, "allow_blank": True, "allow_null": True},
            "part_number": {"required": False, "allow_blank": True, "allow_null": True},
        }

    def validate(self, attrs):
        condition = attrs.get("condition")
        if condition is None and self.instance is not None:
            condition = self.instance.condition
        part_number = attrs.get("part_number", serializers.empty)
        if part_number is serializers.empty:
            part_number = self.instance.part_number if self.instance is not None else ""
        part_number = (part_number or "").strip()

        if condition == MachineReportPartCheck.Condition.REPLACE and not part_number:
            raise serializers.ValidationError(
                {"part_number": "El número de parte es obligatorio cuando la condición es REPLACE."}
            )
        attrs["part_number"] = part_number

        if "notes" in attrs:
            attrs["notes"] = attrs["notes"] or ""
        return attrs


class MachineReportPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MachineReportPhoto
        fields = [
            "id",
            "photo_url",
            "label",
            "note",
            "sort_order",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {
            "note": {"required": False, "allow_blank": True, "allow_null": True},
        }

    def validate_note(self, value):
        return value or ""


class ReportElectricalEvaluationSerializer(serializers.ModelSerializer):
    actual_voltage = serializers.SerializerMethodField()
    main_motor_current = serializers.SerializerMethodField()
    fan_motor_current = serializers.SerializerMethodField()

    class Meta:
        model = ReportElectricalEvaluation
        fields = [
            "id",
            "nominal_voltage",
            "actual_voltage",
            "main_motor_current",
            "fan_motor_current",
            "starter_type",
            "starter_brand",
            "control_voltage",
            "grounding",
            "created_at",
            "updated_at",
            "actual_voltage_l1_l2",
            "actual_voltage_l2_l3",
            "actual_voltage_l3_l1",
            "main_motor_current_l1",
            "main_motor_current_l2",
            "main_motor_current_l3",
            "fan_motor_current_l1",
            "fan_motor_current_l2",
            "fan_motor_current_l3",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "actual_voltage_l1_l2": {"write_only": True, "required": False, "allow_null": True},
            "actual_voltage_l2_l3": {"write_only": True, "required": False, "allow_null": True},
            "actual_voltage_l3_l1": {"write_only": True, "required": False, "allow_null": True},
            "main_motor_current_l1": {"write_only": True, "required": False, "allow_null": True},
            "main_motor_current_l2": {"write_only": True, "required": False, "allow_null": True},
            "main_motor_current_l3": {"write_only": True, "required": False, "allow_null": True},
            "fan_motor_current_l1": {"write_only": True, "required": False, "allow_null": True},
            "fan_motor_current_l2": {"write_only": True, "required": False, "allow_null": True},
            "fan_motor_current_l3": {"write_only": True, "required": False, "allow_null": True},
        }

    def get_attribute(self, instance):
        if isinstance(instance, MachineReport):
            try:
                return instance.electrical_evaluation
            except ReportElectricalEvaluation.DoesNotExist:
                return None
        return instance

    def get_actual_voltage(self, obj):
        return {
            "l1_l2": obj.actual_voltage_l1_l2,
            "l2_l3": obj.actual_voltage_l2_l3,
            "l3_l1": obj.actual_voltage_l3_l1,
        }

    def get_main_motor_current(self, obj):
        return {
            "l1": obj.main_motor_current_l1,
            "l2": obj.main_motor_current_l2,
            "l3": obj.main_motor_current_l3,
        }

    def get_fan_motor_current(self, obj):
        return {
            "l1": obj.fan_motor_current_l1,
            "l2": obj.fan_motor_current_l2,
            "l3": obj.fan_motor_current_l3,
        }

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {
                    "electrical_evaluation": (
                        "Formato inválido: se espera un objeto para electrical_evaluation."
                    )
                }
            )
        mutable = {**data}
        actual = mutable.pop("actual_voltage", None)
        if isinstance(actual, dict):
            if "l1_l2" in actual:
                mutable["actual_voltage_l1_l2"] = actual.get("l1_l2")
            if "l2_l3" in actual:
                mutable["actual_voltage_l2_l3"] = actual.get("l2_l3")
            if "l3_l1" in actual:
                mutable["actual_voltage_l3_l1"] = actual.get("l3_l1")
        main = mutable.pop("main_motor_current", None)
        if isinstance(main, dict):
            if "l1" in main:
                mutable["main_motor_current_l1"] = main.get("l1")
            if "l2" in main:
                mutable["main_motor_current_l2"] = main.get("l2")
            if "l3" in main:
                mutable["main_motor_current_l3"] = main.get("l3")
        fan = mutable.pop("fan_motor_current", None)
        if isinstance(fan, dict):
            if "l1" in fan:
                mutable["fan_motor_current_l1"] = fan.get("l1")
            if "l2" in fan:
                mutable["fan_motor_current_l2"] = fan.get("l2")
            if "l3" in fan:
                mutable["fan_motor_current_l3"] = fan.get("l3")
        return super().to_internal_value(mutable)


class MachineReportSerializer(serializers.ModelSerializer):
    machine_serial_number = serializers.CharField(source="machine.serial_number", read_only=True)
    machine_model = serializers.CharField(source="machine.model", read_only=True)
    origin_report_type = serializers.CharField(
        source="origin_report.type", read_only=True, allow_null=True
    )
    created_by_name = serializers.SerializerMethodField()
    part_checks = MachineReportPartCheckSerializer(many=True, required=False)
    photos = MachineReportPhotoSerializer(many=True, required=False)
    electrical_evaluation = ReportElectricalEvaluationSerializer(
        required=False, allow_null=True
    )

    class Meta:
        model = MachineReport
        fields = [
            "id",
            "correlativo",
            "type",
            "machine",
            "machine_serial_number",
            "machine_model",
            "origin_report",
            "origin_report_type",
            "intervention_date",
            "hour_meter",
            "current_condition",
            "work_performed",
            "background",
            "conclusions",
            "recommendations",
            "part_checks",
            "photos",
            "electrical_evaluation",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "correlativo", "created_by", "created_at", "updated_at"]

    def get_created_by_name(self, obj) -> str:
        user = obj.created_by
        full = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
        return full or user.username

    def _company_id_for_request(self) -> int | None:
        ctx_cid = self.context.get("company_id")
        if ctx_cid is not None:
            return ctx_cid
        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.is_authenticated:
            return company_id_for_user(request.user)
        return None

    def validate_machine(self, machine: Machine) -> Machine:
        request = self.context.get("request")
        if request and getattr(request, "user", None) and request.user.is_superuser:
            return machine
        company_id = self._company_id_for_request()
        if company_id is None or machine.company_id != company_id:
            raise serializers.ValidationError(
                "La máquina no pertenece a su compañía o no tiene empresa asignada."
            )
        return machine

    def validate(self, attrs):
        report_type = attrs.get("type")
        if report_type is None and self.instance is not None:
            report_type = self.instance.type

        machine = attrs.get("machine")
        if machine is None and self.instance is not None:
            machine = self.instance.machine

        origin = attrs.get("origin_report", serializers.empty)
        if origin is serializers.empty:
            origin = self.instance.origin_report if self.instance is not None else None

        if "origin_report" in attrs or self.instance is None:
            if report_type == MachineReport.ReportType.EVALUATION and origin is not None:
                raise serializers.ValidationError(
                    {
                        "origin_report": (
                            "Un informe de evaluación no puede tener informe de origen."
                        )
                    }
                )

            if report_type == MachineReport.ReportType.SERVICE and origin is not None:
                if origin.type != MachineReport.ReportType.EVALUATION:
                    raise serializers.ValidationError(
                        {
                            "origin_report": (
                                "El informe de origen debe ser de tipo EVALUATION."
                            )
                        }
                    )
                if machine is not None and origin.machine_id != machine.pk:
                    raise serializers.ValidationError(
                        {
                            "origin_report": (
                                "El informe de origen debe pertenecer a la misma máquina."
                            )
                        }
                    )

        hour_meter = attrs.get("hour_meter", serializers.empty)
        if hour_meter is serializers.empty:
            hour_meter = self.instance.hour_meter if self.instance is not None else None
        if (
            hour_meter is not None
            and machine is not None
            and machine.current_hour_meter is not None
            and hour_meter < machine.current_hour_meter
        ):
            raise serializers.ValidationError(
                {
                    "hour_meter": (
                        f"El horómetro no puede ser menor que el actual de la máquina "
                        f"({machine.current_hour_meter})."
                    )
                }
            )

        part_checks = attrs.get("part_checks")
        if part_checks is not None:
            if report_type != MachineReport.ReportType.EVALUATION:
                raise serializers.ValidationError(
                    {"part_checks": "Solo los informes de evaluación admiten checklist de partes."}
                )
            if machine is not None and machine.subcategory_id is None:
                raise serializers.ValidationError(
                    {
                        "part_checks": (
                            "La máquina no tiene subcategoría; no se pueden validar partes recomendadas."
                        )
                    }
                )
            seen_parts: set[int] = set()
            for item in part_checks:
                part = item.get("recommended_part")
                if part is None:
                    continue
                part_id = part.pk if isinstance(part, SubcategoryRecommendedPart) else int(part)
                if part_id in seen_parts:
                    raise serializers.ValidationError(
                        {"part_checks": "Hay partes recomendadas duplicadas en el checklist."}
                    )
                seen_parts.add(part_id)
                if not isinstance(part, SubcategoryRecommendedPart):
                    part = SubcategoryRecommendedPart.objects.filter(pk=part_id).first()
                if part is None:
                    raise serializers.ValidationError(
                        {"part_checks": f"Parte recomendada {part_id} no existe."}
                    )
                if machine is not None and part.subcategory_id != machine.subcategory_id:
                    raise serializers.ValidationError(
                        {
                            "part_checks": (
                                f"La parte '{part.name}' no pertenece a la subcategoría de la máquina."
                            )
                        }
                    )

        return attrs

    def _sync_machine_hour_meter(self, machine: Machine, hour_meter) -> None:
        if hour_meter is None:
            return
        Machine.objects.filter(pk=machine.pk).update(current_hour_meter=hour_meter)
        machine.current_hour_meter = hour_meter

    def _replace_part_checks(self, report: MachineReport, part_checks_data: list | None) -> None:
        if part_checks_data is None:
            return
        report.part_checks.all().delete()
        for item in part_checks_data:
            MachineReportPartCheck.objects.create(report=report, **item)

    def _replace_photos(self, report: MachineReport, photos_data: list | None) -> None:
        if photos_data is None:
            return
        report.photos.all().delete()
        for item in photos_data:
            MachineReportPhoto.objects.create(report=report, **item)

    def _upsert_report_electrical(
        self, report: MachineReport, electrical_data: dict | None
    ) -> None:
        if electrical_data is None:
            return
        ReportElectricalEvaluation.objects.update_or_create(
            report=report,
            defaults=electrical_data,
        )
        # Sync a la ficha eléctrica actual de la máquina (como el horómetro).
        MachineElectricalEvaluation.objects.update_or_create(
            machine=report.machine,
            defaults=electrical_data,
        )

    def create(self, validated_data):
        request = self.context.get("request")
        if not request or not getattr(request, "user", None):
            raise serializers.ValidationError(
                {"created_by": "Se requiere un usuario autenticado."}
            )
        part_checks_data = validated_data.pop("part_checks", None)
        photos_data = validated_data.pop("photos", None)
        electrical_data = validated_data.pop("electrical_evaluation", None)
        validated_data["created_by"] = request.user
        report = super().create(validated_data)
        self._sync_machine_hour_meter(report.machine, report.hour_meter)
        self._replace_part_checks(report, part_checks_data)
        self._replace_photos(report, photos_data)
        self._upsert_report_electrical(report, electrical_data)
        return report

    def update(self, instance, validated_data):
        part_checks_data = validated_data.pop("part_checks", None)
        photos_data = validated_data.pop("photos", None)
        electrical_data = validated_data.pop("electrical_evaluation", serializers.empty)
        hour_meter = validated_data.get("hour_meter", serializers.empty)
        report = super().update(instance, validated_data)
        if hour_meter is not serializers.empty and hour_meter is not None:
            self._sync_machine_hour_meter(report.machine, report.hour_meter)
        if part_checks_data is not None:
            self._replace_part_checks(report, part_checks_data)
        if photos_data is not None:
            self._replace_photos(report, photos_data)
        if electrical_data is not serializers.empty and electrical_data is not None:
            self._upsert_report_electrical(report, electrical_data)
        return report
