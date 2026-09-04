from django.conf import settings
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _

from accounts.models import Company
from core.models import Brand, CategoryProduct, Client, SubcategoryProduct


class Machine(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("Activa")
        OUT_OF_SERVICE = "OUT_OF_SERVICE", _("Fuera de servicio")
        DECOMMISSIONED = "DECOMMISSIONED", _("Dada de baja")

    id = models.AutoField(primary_key=True)
    company = models.ForeignKey(
        Company,
        db_column="company_id",
        on_delete=models.PROTECT,
        related_name="machines",
    )
    client = models.ForeignKey(
        Client,
        db_column="client_id",
        on_delete=models.PROTECT,
        related_name="machines",
    )
    brand = models.ForeignKey(
        Brand,
        db_column="brand_id",
        on_delete=models.PROTECT,
        related_name="machines",
    )
    category = models.ForeignKey(
        CategoryProduct,
        db_column="category_id",
        on_delete=models.PROTECT,
        related_name="machines",
        null=True,
        blank=True,
    )
    subcategory = models.ForeignKey(
        SubcategoryProduct,
        db_column="subcategory_id",
        on_delete=models.PROTECT,
        related_name="machines",
        null=True,
        blank=True,
    )
    model = models.CharField(max_length=100)
    serial_number = models.CharField(max_length=100)
    plate_image_url = models.URLField(max_length=500, null=True, blank=True)
    daily_working_hours = models.PositiveIntegerField()
    current_hour_meter = models.PositiveIntegerField(null=True, blank=True)
    location = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = "machines"
        verbose_name = _("Machine")
        verbose_name_plural = _("Machines")
        constraints = [
            models.UniqueConstraint(
                fields=["company", "serial_number"],
                name="uq_machine_serial_per_company",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.brand_id} {self.model} ({self.serial_number})"


class MachineElectricalEvaluation(models.Model):
    class NominalVoltage(models.TextChoices):
        V220 = "220V", "220 V"
        V380 = "380V", "380 V"
        V440 = "440V", "440 V"

    class StarterType(models.TextChoices):
        DIRECT = "DIRECT", _("Directo")
        STAR_DELTA = "STAR_DELTA", _("Estrella-triángulo")
        VSD = "VSD", "VSD"
        SOFT = "SOFT", "SOFT"

    class ControlVoltage(models.TextChoices):
        VAC_110 = "110_VAC", "110 VAC"
        VAC_220 = "220_VAC", "220 VAC"
        VDC_24 = "24_VDC", "24 VDC"

    id = models.AutoField(primary_key=True)
    machine = models.OneToOneField(
        Machine,
        db_column="machine_id",
        on_delete=models.CASCADE,
        related_name="electrical_evaluation",
    )
    nominal_voltage = models.CharField(
        max_length=10,
        choices=NominalVoltage.choices,
        blank=True,
        default="",
    )
    actual_voltage_l1_l2 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    actual_voltage_l2_l3 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    actual_voltage_l3_l1 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    main_motor_current_l1 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    main_motor_current_l2 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    main_motor_current_l3 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    fan_motor_current_l1 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    fan_motor_current_l2 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    fan_motor_current_l3 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    starter_type = models.CharField(
        max_length=20,
        choices=StarterType.choices,
        blank=True,
        default="",
    )
    starter_brand = models.CharField(max_length=100, blank=True, default="")
    control_voltage = models.CharField(
        max_length=20,
        choices=ControlVoltage.choices,
        blank=True,
        default="",
    )
    grounding = models.CharField(max_length=250, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = "machine_electrical_evaluation"
        verbose_name = _("Machine electrical evaluation")
        verbose_name_plural = _("Machine electrical evaluations")

    def __str__(self) -> str:
        return f"Electrical evaluation for machine {self.machine_id}"


class ReportSequence(models.Model):
    """Contador por empresa + prefijo (EVA / SRV) → EVA-000001."""

    id = models.AutoField(primary_key=True)
    company = models.ForeignKey(
        Company,
        db_column="company_id",
        on_delete=models.CASCADE,
        related_name="report_sequences",
    )
    prefix = models.CharField(max_length=10)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        managed = True
        db_table = "report_sequence"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "prefix"],
                name="uq_report_sequence_company_prefix",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.company_id}:{self.prefix}:{self.last_number}"


class MachineReport(models.Model):
    class ReportType(models.TextChoices):
        EVALUATION = "EVALUATION", _("Evaluación")
        SERVICE = "SERVICE", _("Servicio")

    class CurrentCondition(models.TextChoices):
        OPERATIONAL = "OPERATIONAL", _("Operativo")
        INOPERATIVE = "INOPERATIVE", _("Inoperativo")

    PREFIX_BY_TYPE = {
        ReportType.EVALUATION: "EVA",
        ReportType.SERVICE: "SRV",
    }

    id = models.AutoField(primary_key=True)
    correlativo = models.CharField(max_length=30, unique=True, blank=True, default="")
    type = models.CharField(max_length=20, choices=ReportType.choices)
    machine = models.ForeignKey(
        Machine,
        db_column="machine_id",
        on_delete=models.PROTECT,
        related_name="reports",
    )
    origin_report = models.ForeignKey(
        "self",
        db_column="origin_report_id",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="follow_up_reports",
    )
    intervention_date = models.DateField()
    hour_meter = models.PositiveIntegerField(null=True, blank=True)
    current_condition = models.CharField(
        max_length=20,
        choices=CurrentCondition.choices,
    )
    work_performed = models.TextField(blank=True, default="")
    background = models.TextField(blank=True, default="")
    conclusions = models.TextField(blank=True, default="")
    recommendations = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        db_column="created_by_id",
        on_delete=models.PROTECT,
        related_name="machine_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = "machine_reports"
        verbose_name = _("Machine report")
        verbose_name_plural = _("Machine reports")
        ordering = ["-intervention_date", "-id"]

    def _generate_correlativo(self) -> str:
        company_id = self.machine.company_id
        prefix = self.PREFIX_BY_TYPE.get(self.type, "RPT")
        with transaction.atomic():
            seq, _ = ReportSequence.objects.select_for_update().get_or_create(
                company_id=company_id,
                prefix=prefix,
                defaults={"last_number": 0},
            )
            seq.last_number += 1
            seq.save(update_fields=["last_number"])
            # Incluye company_id para unicidad global multi-empresa
            return f"{company_id}-{prefix}-{seq.last_number:06d}"

    def save(self, *args, **kwargs):
        if self._state.adding and not (self.correlativo or "").strip():
            self.correlativo = self._generate_correlativo()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.correlativo or f"{self.type} #{self.pk}"


class ReportElectricalEvaluation(models.Model):
    """Snapshot eléctrico opcional por informe (historial)."""

    class NominalVoltage(models.TextChoices):
        V220 = "220V", "220 V"
        V380 = "380V", "380 V"
        V440 = "440V", "440 V"

    class StarterType(models.TextChoices):
        DIRECT = "DIRECT", _("Directo")
        STAR_DELTA = "STAR_DELTA", _("Estrella-triángulo")
        VSD = "VSD", "VSD"
        SOFT = "SOFT", "SOFT"

    class ControlVoltage(models.TextChoices):
        VAC_110 = "110_VAC", "110 VAC"
        VAC_220 = "220_VAC", "220 VAC"
        VDC_24 = "24_VDC", "24 VDC"

    id = models.AutoField(primary_key=True)
    report = models.OneToOneField(
        MachineReport,
        db_column="report_id",
        on_delete=models.CASCADE,
        related_name="electrical_evaluation",
    )
    nominal_voltage = models.CharField(
        max_length=10,
        choices=NominalVoltage.choices,
        blank=True,
        default="",
    )
    actual_voltage_l1_l2 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    actual_voltage_l2_l3 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    actual_voltage_l3_l1 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    main_motor_current_l1 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    main_motor_current_l2 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    main_motor_current_l3 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    fan_motor_current_l1 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    fan_motor_current_l2 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    fan_motor_current_l3 = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    starter_type = models.CharField(
        max_length=20,
        choices=StarterType.choices,
        blank=True,
        default="",
    )
    starter_brand = models.CharField(max_length=100, blank=True, default="")
    control_voltage = models.CharField(
        max_length=20,
        choices=ControlVoltage.choices,
        blank=True,
        default="",
    )
    grounding = models.CharField(max_length=250, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = "report_electrical_evaluation"
        verbose_name = _("Report electrical evaluation")
        verbose_name_plural = _("Report electrical evaluations")

    def __str__(self) -> str:
        return f"Electrical evaluation for report {self.report_id}"


class MachineReportPartCheck(models.Model):
    class Condition(models.TextChoices):
        OK = "OK", _("Buen estado")
        REPLACE = "REPLACE", _("Reemplazar")
        CLEAN = "CLEAN", _("Solo limpiar")

    id = models.AutoField(primary_key=True)
    report = models.ForeignKey(
        MachineReport,
        db_column="report_id",
        on_delete=models.CASCADE,
        related_name="part_checks",
    )
    recommended_part = models.ForeignKey(
        "core.SubcategoryRecommendedPart",
        db_column="recommended_part_id",
        on_delete=models.PROTECT,
        related_name="report_checks",
    )
    condition = models.CharField(max_length=20, choices=Condition.choices)
    part_number = models.CharField(max_length=250, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    class Meta:
        managed = True
        db_table = "machine_report_part_checks"
        verbose_name = _("Machine report part check")
        verbose_name_plural = _("Machine report part checks")
        constraints = [
            models.UniqueConstraint(
                fields=["report", "recommended_part"],
                name="uq_report_recommended_part",
            ),
        ]

    def __str__(self) -> str:
        return f"Check {self.recommended_part_id} on report {self.report_id}"


class MachineReportPhoto(models.Model):
    class Label(models.TextChoices):
        BEFORE = "BEFORE", _("Before")
        DURING = "DURING", _("During")
        AFTER = "AFTER", _("After")

    id = models.AutoField(primary_key=True)
    report = models.ForeignKey(
        MachineReport,
        db_column="report_id",
        on_delete=models.CASCADE,
        related_name="photos",
    )
    photo_url = models.URLField(max_length=500)
    label = models.CharField(max_length=20, choices=Label.choices)
    note = models.TextField(blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "machine_report_photos"
        verbose_name = _("Machine report photo")
        verbose_name_plural = _("Machine report photos")
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.label} photo on report {self.report_id}"
