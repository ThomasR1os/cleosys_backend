# Generated manually for CompanyBranding (1:1 with Company).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0015_rename_celular_to_cellphone_postgresql"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyBranding",
            fields=[
                (
                    "company",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="branding",
                        serialize=False,
                        to="accounts.company",
                    ),
                ),
                (
                    "primary",
                    models.CharField(
                        default="#1E3A5F",
                        help_text="Marca: títulos, cabecera de tabla, acentos.",
                        max_length=7,
                    ),
                ),
                (
                    "primary_light",
                    models.CharField(
                        default="#F1F5F9",
                        help_text="Fondos suaves (bloques resumen / totales).",
                        max_length=7,
                    ),
                ),
                (
                    "muted",
                    models.CharField(
                        default="#64748B",
                        help_text="Texto secundario / etiquetas.",
                        max_length=7,
                    ),
                ),
                (
                    "border",
                    models.CharField(
                        default="#E2E8F0",
                        help_text="Bordes y líneas.",
                        max_length=7,
                    ),
                ),
                (
                    "table_stripe",
                    models.CharField(
                        default="#F8FAFC",
                        help_text="Rayado de filas de productos.",
                        max_length=7,
                    ),
                ),
                (
                    "emphasis_bar",
                    models.CharField(
                        default="#0F172A",
                        help_text="Barra oscura de totales; texto principal en varias zonas.",
                        max_length=7,
                    ),
                ),
                (
                    "text_body",
                    models.CharField(
                        default="#3C3C3C",
                        help_text="Párrafos (ej. cuentas bancarias).",
                        max_length=7,
                    ),
                ),
                (
                    "text_label",
                    models.CharField(
                        default="#374151",
                        help_text="Etiquetas destacadas (ej. ficha técnica).",
                        max_length=7,
                    ),
                ),
                (
                    "text_caption",
                    models.CharField(
                        default="#475569",
                        help_text="Texto secundario en cursiva (ficha técnica).",
                        max_length=7,
                    ),
                ),
                (
                    "extensions",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Extensiones futuras (no sustituye los campos de color explícitos).",
                    ),
                ),
            ],
            options={
                "db_table": "company_branding",
                "verbose_name": "Company branding",
                "verbose_name_plural": "Company brandings",
                "managed": True,
            },
        ),
    ]
