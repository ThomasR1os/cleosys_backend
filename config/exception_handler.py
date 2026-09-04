"""
Normaliza errores de la API para el frontend.

Formato (compatible con DRF):
- Campos: { "campo": ["mensaje", ...] }  o anidados
- Globales: { "detail": "mensaje" }  /  { "non_field_errors": ["..."] }

Además convierte ValidationError de Django e IntegrityError en 400 legibles.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _as_list(value):
    if value is None:
        return ["Error de validación."]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def _django_validation_to_data(exc: DjangoValidationError) -> dict:
    if hasattr(exc, "message_dict") and exc.message_dict:
        return {k: _as_list(v) for k, v in exc.message_dict.items()}
    if hasattr(exc, "messages"):
        return {"non_field_errors": _as_list(exc.messages)}
    return {"non_field_errors": _as_list(getattr(exc, "message", str(exc)))}


def _integrity_error_to_data(exc: IntegrityError) -> dict:
    msg = str(exc).lower()
    if "serial_number" in msg or "machines_company" in msg:
        return {
            "serial_number": [
                "Ya existe una máquina con este número de serie en su compañía."
            ]
        }
    if "correlativo" in msg:
        return {
            "correlativo": [
                "No se pudo asignar el correlativo (conflicto). Intente de nuevo."
            ]
        }
    if "unique" in msg or "duplicate" in msg:
        return {
            "non_field_errors": [
                "Ya existe un registro con esos datos únicos. Revise los campos e intente de nuevo."
            ]
        }
    return {
        "non_field_errors": [
            "No se pudo guardar por una restricción de base de datos. Revise los datos."
        ]
    }


def custom_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        return Response(
            _django_validation_to_data(exc),
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, IntegrityError):
        return Response(
            _integrity_error_to_data(exc),
            status=status.HTTP_400_BAD_REQUEST,
        )

    response = drf_exception_handler(exc, context)
    return response
