"""Cifrado de secretos SMTP (password) con Fernet."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    raw = (getattr(settings, "EMAIL_CREDENTIALS_KEY", None) or "").strip()
    if raw:
        # Acepta clave Fernet url-safe base64 (44 chars) o cualquier string → se deriva.
        try:
            return Fernet(raw.encode("ascii") if isinstance(raw, str) else raw)
        except (ValueError, TypeError):
            digest = hashlib.sha256(raw.encode("utf-8")).digest()
            return Fernet(base64.urlsafe_b64encode(digest))
    digest = hashlib.sha256(str(settings.SECRET_KEY).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    if plain is None or plain == "":
        return ""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        raise ValueError("No se pudo descifrar la contraseña SMTP.") from exc
