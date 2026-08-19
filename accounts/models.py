from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .branding_defaults import DEFAULT_BRANDING_COLORS
from .validators import normalize_hex_color


class Company(models.Model):
    id = models.AutoField(primary_key=True)
    ruc = models.TextField(
        "RUC",
        blank=True,
        default="",
    )
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


class CompanyBranding(models.Model):
    """
    Paleta PDF por compañía (1:1). Si no hay fila, la API devuelve defaults en branding_defaults.
    """

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="branding",
        primary_key=True,
    )
    primary = models.CharField(
        max_length=7,
        default=DEFAULT_BRANDING_COLORS["primary"],
        help_text=_("Marca: títulos, cabecera de tabla, acentos."),
    )
    primary_light = models.CharField(
        max_length=7,
        default=DEFAULT_BRANDING_COLORS["primary_light"],
        help_text=_("Fondos suaves (bloques resumen / totales)."),
    )
    muted = models.CharField(
        max_length=7,
        default=DEFAULT_BRANDING_COLORS["muted"],
        help_text=_("Texto secundario / etiquetas."),
    )
    border = models.CharField(
        max_length=7,
        default=DEFAULT_BRANDING_COLORS["border"],
        help_text=_("Bordes y líneas."),
    )
    table_stripe = models.CharField(
        max_length=7,
        default=DEFAULT_BRANDING_COLORS["table_stripe"],
        help_text=_("Rayado de filas de productos."),
    )
    emphasis_bar = models.CharField(
        max_length=7,
        default=DEFAULT_BRANDING_COLORS["emphasis_bar"],
        help_text=_("Barra oscura de totales; texto principal en varias zonas."),
    )
    text_body = models.CharField(
        max_length=7,
        default=DEFAULT_BRANDING_COLORS["text_body"],
        help_text=_("Párrafos (ej. cuentas bancarias)."),
    )
    text_label = models.CharField(
        max_length=7,
        default=DEFAULT_BRANDING_COLORS["text_label"],
        help_text=_("Etiquetas destacadas (ej. ficha técnica)."),
    )
    text_caption = models.CharField(
        max_length=7,
        default=DEFAULT_BRANDING_COLORS["text_caption"],
        help_text=_("Texto secundario en cursiva (ficha técnica)."),
    )
    extensions = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Extensiones futuras (no sustituye los campos de color explícitos)."),
    )

    class Meta:
        managed = True
        db_table = "company_branding"
        verbose_name = _("Company branding")
        verbose_name_plural = _("Company brandings")

    def clean(self) -> None:
        for name in (
            "primary",
            "primary_light",
            "muted",
            "border",
            "table_stripe",
            "emphasis_bar",
            "text_body",
            "text_label",
            "text_caption",
        ):
            normalized = normalize_hex_color(getattr(self, name))
            setattr(self, name, normalized)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CompanyEmailSettings(models.Model):
    """SMTP saliente por compañía (1:1)."""

    company = models.OneToOneField(
        Company,
        on_delete=models.CASCADE,
        related_name="email_settings",
        primary_key=True,
    )
    host = models.CharField(max_length=255, blank=True, default="")
    port = models.PositiveIntegerField(default=587)
    use_tls = models.BooleanField(default=True)
    use_ssl = models.BooleanField(default=False)
    username = models.CharField(max_length=255, blank=True, default="")
    password_encrypted = models.TextField(blank=True, default="")
    from_email = models.EmailField(blank=True, default="")
    from_name = models.CharField(max_length=150, blank=True, default="")
    default_cc = models.JSONField(
        default=list,
        blank=True,
        help_text=_("Emails en copia por defecto al enviar cotizaciones (lista)."),
    )
    is_active = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = "company_email_settings"
        verbose_name = _("Company email settings")
        verbose_name_plural = _("Company email settings")

    def __str__(self) -> str:
        return f"Email settings for company {self.company_id}"

    @property
    def password_configured(self) -> bool:
        return bool((self.password_encrypted or "").strip())

    def set_password(self, plain: str) -> None:
        from .email_crypto import encrypt_secret

        self.password_encrypted = encrypt_secret(plain) if plain else ""

    def get_password(self) -> str:
        from .email_crypto import decrypt_secret

        return decrypt_secret(self.password_encrypted)

    def resolved_default_cc(self) -> list[str]:
        raw = self.default_cc or []
        if isinstance(raw, str):
            raw = [p.strip() for p in raw.split(",") if p.strip()]
        result: list[str] = []
        seen: set[str] = set()
        for item in raw:
            email = str(item or "").strip()
            key = email.lower()
            if email and key not in seen:
                seen.add(key)
                result.append(email)
        return result


class UserProfile(models.Model):
    class Role(models.TextChoices):
        ALMACEN = "ALMACEN", _("Almacén")
        VENTAS = "VENTAS", _("Ventas")
        LOGISTICA = "LOGISTICA", _("Logística")
        SERVICIOS = "SERVICIOS", _("Servicios")
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
    email_display_name = models.CharField(
        _("Nombre visible en correos"),
        max_length=150,
        blank=True,
        default="",
        help_text=_("Si está vacío se usa el nombre del usuario."),
    )
    reply_to_email = models.EmailField(
        _("Reply-To al enviar cotizaciones"),
        blank=True,
        default="",
        help_text=_("Si está vacío se usa user.email."),
    )
    signature_url = models.URLField(
        _("URL de firma (Cloudinary)"),
        max_length=500,
        blank=True,
        default="",
        help_text=_("Imagen de firma del usuario en Cloudinary."),
    )

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.company_id}"

    def resolve_email_display_name(self) -> str:
        if (self.email_display_name or "").strip():
            return self.email_display_name.strip()
        user = self.user
        full = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
        return full or user.username

    def resolve_reply_to_email(self) -> str:
        if (self.reply_to_email or "").strip():
            return self.reply_to_email.strip()
        return (self.user.email or "").strip()
