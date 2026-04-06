"""
Valores por defecto de la paleta PDF (cotizaciones) y helper de respuesta API.

Si no existe fila en CompanyBranding, GET /api/companies/{id}/ devuelve este dict
(misma forma que con branding persistido).
"""
from __future__ import annotations

from typing import Any

# Hex normalizado: #RRGGBB (mayúsculas).
DEFAULT_BRANDING_COLORS: dict[str, str] = {
    "primary": "#1E3A5F",
    "primary_light": "#F1F5F9",
    "muted": "#64748B",
    "border": "#E2E8F0",
    "table_stripe": "#F8FAFC",
    "emphasis_bar": "#0F172A",
    "text_body": "#3C3C3C",
    "text_label": "#374151",
    "text_caption": "#475569",
}

COLOR_FIELD_NAMES: tuple[str, ...] = tuple(DEFAULT_BRANDING_COLORS.keys())


def default_extensions() -> dict[str, Any]:
    return {}


def branding_payload_for_company(company) -> dict[str, Any]:
    """Incluye colores + extensions; sin fila DB → colores por defecto y extensions {}."""
    from .models import CompanyBranding

    try:
        b = company.branding
    except CompanyBranding.DoesNotExist:
        return {**DEFAULT_BRANDING_COLORS, "extensions": default_extensions()}
    return {
        **{name: getattr(b, name) for name in COLOR_FIELD_NAMES},
        "extensions": b.extensions if b.extensions is not None else default_extensions(),
    }
