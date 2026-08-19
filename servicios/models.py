from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.models import Company
from core.models import Brand, Client


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
