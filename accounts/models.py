from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Company(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    logo_url = models.URLField(
        _("URL del logo (Cloudinary)"),
        max_length=500,
        blank=True,
        default="",
        help_text=_("Enlace público al logo en Cloudinary u otro CDN."),
    )
    bank_accounts = models.TextField(
        "Bank accounts",
        blank=True,
        default="",
        help_text=_("Datos de cuentas bancarias (texto libre)."),
    )

    class Meta:
        # En SQLite (dev) la manejamos con migraciones para poder sembrar data.
        # Cuando conectemos a tu DB real, podemos volver a `managed = False`.
        managed = True
        db_table = "company"
        verbose_name = _("Company")
        verbose_name_plural = _("Companies")

    def __str__(self) -> str:
        return self.name


class UserProfile(models.Model):
    class Role(models.TextChoices):
        ALMACEN = "ALMACEN", _("Almacén")
        VENTAS = "VENTAS", _("Ventas")
        LOGISTICA = "LOGISTICA", _("Logística")
        ADMIN = "ADMIN", _("Administrador")

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="profiles")
    role = models.CharField(
        _("Rol"),
        max_length=20,
        choices=Role.choices,
        default=Role.VENTAS,
        db_column="role",
    )
    # Iniciales / código corto para correlativos de cotización (ej. GER, KC, MP) → GER-001052
    quotation_prefix = models.CharField(
        _("Prefijo cotizaciones (iniciales)"),
        max_length=10,
        blank=True,
        default="",
        db_column="quotation_prefix",
        help_text=_("Letras usadas en el correlativo, ej. GER → GER-001052"),
    )
    cellphone = models.CharField(
        _("Cellphone"),
        max_length=20,
        blank=True,
        default="",
        db_column="cellphone",
    )

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.company_id}"
