"""Helpers para búsqueda de cliente por RUC (sin depender del formato guardado en BD)."""

from __future__ import annotations

import re

from .models import Client


def normalize_ruc_digits(raw: str) -> str:
    """Deja solo dígitos del RUC (entrada típica SUNAT / usuario)."""
    if raw is None:
        return ""
    s = str(raw).strip().replace("\xa0", "")
    return re.sub(r"\D", "", s)


def validate_pe_ruc_digits(digits: str) -> bool:
    """RUC Perú persona jurídica típicamente 11 dígitos."""
    return len(digits) == 11 and digits.isdigit()


def find_client_by_ruc_query(normalized_digits: str) -> Client | None:
    """
    Busca un cliente cuyo RUC normalizado (solo dígitos) coincida con normalized_digits.
    Prioriza coincidencia exacta en columna `ruc`; si no hay, revisa candidatos por dígitos embebidos.
    """
    if not normalized_digits:
        return None
    exact = Client.objects.filter(ruc=normalized_digits).first()
    if exact:
        return exact

    # Variantes comunes con guiones/espacios
    variants = [
        normalized_digits,
        f"{normalized_digits[:2]}-{normalized_digits[2:10]}-{normalized_digits[10]}",
        f"{normalized_digits[:2]}-{normalized_digits[2:]}",
    ]
    found = Client.objects.filter(ruc__in=[v for v in variants if v]).first()
    if found:
        return found

    # Índice acotado: prefijo numérico (sin scan masivo de tabla client completa)
    prefix = normalized_digits[: min(8, len(normalized_digits))]
    if len(prefix) < 6:
        return None
    for row in Client.objects.filter(ruc__contains=prefix).only("id", "ruc", "name"):
        if normalize_ruc_digits(row.ruc) == normalized_digits:
            return row
    return None


def contacts_exist_scope_company(client_pk: int, company_id: int) -> bool:
    """Hay al menos un contacto del cliente en la empresa."""
    from ventas.models import ClientContact

    return ClientContact.objects.filter(client_id=client_pk, company_id=company_id).exists()


def contacts_exist_scope_mine(client_pk: int, company_id: int, user_id: int) -> bool:
    """El usuario tiene al menos un contacto del cliente en la empresa."""
    from ventas.models import ClientContact

    return ClientContact.objects.filter(
        client_id=client_pk,
        company_id=company_id,
        user_id=user_id,
    ).exists()
