import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.models import Company
from core.models import Client, PaymentMethods


class ClientContact(models.Model):
    id = models.AutoField(primary_key=True)
    contact_first_name = models.CharField(max_length=100, db_column="contact_first_name")
    contact_last_name = models.CharField(max_length=100, db_column="contact_last_name")
    email = models.EmailField(max_length=200, null=True, blank=True)
    phone = models.CharField(max_length=30, null=True, blank=True)
    client = models.ForeignKey(Client, db_column="client_id", on_delete=models.PROTECT, related_name="contacts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, db_column="user_id", on_delete=models.PROTECT, related_name="client_contacts")
    company = models.ForeignKey(
        Company,
        db_column="company_id",
        on_delete=models.PROTECT,
        related_name="client_contacts",
        null=True,
        blank=True,
    )

    class Meta:
        managed = True
        db_table = "client_contact"
        verbose_name = _("Client Contact")
        verbose_name_plural = _("Client Contacts")
        constraints = [
            models.UniqueConstraint(
                fields=["company", "client", "contact_first_name", "contact_last_name"],
                name="uq_client_contact_per_company",
            ),
            models.UniqueConstraint(
                fields=["company", "client", "email"],
                name="uq_client_contact_email_per_company",
            )
        ]

    def __str__(self) -> str:
        return f"{self.contact_first_name} {self.contact_last_name}"


class QuotationSequence(models.Model):
    """Contador por prefijo (iniciales) para correlativos únicos tipo GER-001052."""

    prefix = models.CharField(max_length=10, primary_key=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        managed = True
        db_table = "quotation_sequence"

    def __str__(self) -> str:
        return f"{self.prefix}:{self.last_number}"


class Quotation(models.Model):
    class QuotationType(models.TextChoices):
        VENTA = "VENTA", _("Venta")
        ALQUILER = "ALQUILER", _("Alquiler")
        SERVICIO = "SERVICIO", _("Servicio")

    class QuotationMoney(models.TextChoices):
        USD = "USD", _("USD")
        PEN = "PEN", _("PEN")

    class QuotationStatus(models.TextChoices):
        APROBADA = "APROBADA", _("Aprobada")
        PENDIENTE = "PENDIENTE", _("Pendiente")
        RECHAZADA = "RECHAZADA", _("Rechazada")

    id = models.AutoField(primary_key=True)
    quotation_type = models.CharField(max_length=20, choices=QuotationType.choices, db_column="type")
    money = models.CharField(max_length=5, choices=QuotationMoney.choices, db_column="money")
    exchange_rate = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        db_column="exchange_rate",
    )
    status = models.CharField(max_length=20, choices=QuotationStatus.choices)
    client = models.ForeignKey(Client, db_column="client_id", on_delete=models.PROTECT, related_name="quotations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, db_column="user_id", on_delete=models.PROTECT, related_name="quotations")
    correlativo = models.CharField(
        _("Correlativo"),
        max_length=32,
        unique=True,
        db_column="correlativo",
    )

    discount = models.DecimalField(max_digits=10, decimal_places=2)
    final_price = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_time = models.IntegerField(db_column="delivery_time")
    conditions = models.TextField(null=True, blank=True)
    payment_methods = models.ForeignKey(
        PaymentMethods,
        db_column="payment_methods_id",
        on_delete=models.PROTECT,
        related_name="quotations",
    )
    works = models.TextField(null=True, blank=True)
    see_sku = models.BooleanField(db_column="see_sku")

    creation_date = models.DateTimeField(default=timezone.now, db_column="creation_date")
    update_date = models.DateTimeField(default=timezone.now, db_column="update_date")

    class Meta:
        managed = True
        db_table = "quotation"
        verbose_name = _("Quotation")
        verbose_name_plural = _("Quotations")

    def _generate_correlativo(self) -> str:
        from accounts.models import UserProfile

        profile = UserProfile.objects.filter(user_id=self.user_id).first()
        prefix = (profile.quotation_prefix or "").strip().upper() if profile else ""
        if not prefix:
            raise ValidationError(
                "El usuario debe tener configurado el prefijo de cotizaciones (iniciales) en su perfil."
            )
        if not prefix.isalpha():
            raise ValidationError(
                "El prefijo de cotizaciones solo debe contener letras (sin números ni espacios)."
            )
        if not (2 <= len(prefix) <= 10):
            raise ValidationError("El prefijo debe tener entre 2 y 10 letras.")

        with transaction.atomic():
            seq, _ = QuotationSequence.objects.select_for_update().get_or_create(
                prefix=prefix,
                defaults={"last_number": 0},
            )
            max_existing = _max_suffix_for_prefix(prefix)
            if seq.last_number < max_existing:
                seq.last_number = max_existing
                seq.save(update_fields=["last_number"])
            seq.last_number += 1
            seq.save(update_fields=["last_number"])
            return f"{prefix}-{seq.last_number:06d}"

    def save(self, *args, **kwargs):
        if self._state.adding and not (self.correlativo or "").strip():
            self.correlativo = self._generate_correlativo()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.correlativo or f"Quotation #{self.id}"


def _max_suffix_for_prefix(prefix: str) -> int:
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    m = 0
    for val in Quotation.objects.filter(correlativo__startswith=f"{prefix}-").values_list(
        "correlativo", flat=True
    ):
        if not val:
            continue
        match = pattern.match(val.strip().upper())
        if match:
            m = max(m, int(match.group(1)))
    return m


class QuotationProduct(models.Model):
    id = models.AutoField(primary_key=True)
    quotation = models.ForeignKey(
        Quotation,
        db_column="quotation_id",
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "almacen.Product",
        db_column="product_id",
        on_delete=models.PROTECT,
        related_name="quotation_items",
    )
    cant = models.IntegerField()
    product_price = models.DecimalField(max_digits=10, decimal_places=2, db_column="product_price")

    # Snapshot por línea: edición en cotización no modifica almacen.Product
    line_sku = models.CharField(max_length=100, blank=True, default="")
    line_description = models.CharField(max_length=250, blank=True, default="")
    line_datasheet = models.TextField(blank=True, default="")

    class Meta:
        managed = True
        db_table = "quotation_product"
        verbose_name = _("Quotation Item")
        verbose_name_plural = _("Quotation Items")

    def save(self, *args, **kwargs):
        if self._state.adding and self.product_id:
            p = self.product
            if not (self.line_sku or "").strip():
                self.line_sku = p.sku
            if not (self.line_description or "").strip():
                self.line_description = p.description
            if not (self.line_datasheet or "").strip():
                self.line_datasheet = p.datasheet
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Quotation #{self.quotation_id} - product:{self.product_id}"
