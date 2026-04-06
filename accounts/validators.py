from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from rest_framework import serializers as drf_serializers

_HEX_RE = re.compile(r"^#?[0-9A-Fa-f]{6}$")


def normalize_hex_color(value: str) -> str:
    """Acepta # opcional; devuelve #RRGGBB en mayúsculas."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        raise ValidationError("El color no puede estar vacío.")
    s = str(value).strip()
    if not _HEX_RE.match(s):
        raise ValidationError("Use formato hexadecimal #RRGGBB (el # es opcional).")
    if not s.startswith("#"):
        s = "#" + s
    return s.upper()


def normalize_hex_color_drf(value: str) -> str:
    try:
        return normalize_hex_color(value)
    except ValidationError as e:
        raise drf_serializers.ValidationError(e.messages) from e
