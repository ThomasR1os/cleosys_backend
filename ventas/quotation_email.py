"""Envío de cotizaciones por correo (SMTP de la compañía + PDF del front)."""

from __future__ import annotations

import base64
import binascii
from typing import Any

from rest_framework.exceptions import ValidationError

from accounts.email_inline import iter_named_cids, prepare_html_inline_images
from accounts.email_sending import send_with_company_smtp
from accounts.models import CompanyEmailSettings, UserProfile
from accounts.permissions import company_id_for_user

from .models import Quotation, QuotationEmailLog

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB


class SmtpSendError(Exception):
    """Fallo al hablar con el servidor SMTP (después de validar el request)."""

    def __init__(self, message: str, log_id: int | None = None):
        super().__init__(message)
        self.log_id = log_id


def _join_emails(emails: list[str]) -> str:
    return ", ".join(emails)


def _decode_pdf_base64(raw: str) -> bytes:
    value = (raw or "").strip()
    if "," in value and value.lower().startswith("data:"):
        value = value.split(",", 1)[1]
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError({"pdf_base64": "PDF base64 inválido."}) from exc
    if not data:
        raise ValidationError({"pdf_base64": "PDF vacío."})
    if len(data) > MAX_PDF_BYTES:
        raise ValidationError({"pdf_base64": "El PDF supera el límite de 10 MB."})
    return data


def _resolve_company_id(quotation: Quotation, sender) -> int:
    cid = company_id_for_user(sender)
    if cid is not None:
        return cid
    profile = UserProfile.objects.filter(user_id=quotation.user_id).first()
    if profile:
        return profile.company_id
    raise ValidationError({"detail": "No se pudo determinar la empresa de la cotización."})


def _get_active_smtp(company_id: int) -> CompanyEmailSettings:
    try:
        settings_obj = CompanyEmailSettings.objects.get(company_id=company_id)
    except CompanyEmailSettings.DoesNotExist as exc:
        raise ValidationError(
            {"detail": "La empresa no tiene SMTP configurado."}
        ) from exc
    if not settings_obj.is_active:
        raise ValidationError({"detail": "El SMTP de la empresa está inactivo."})
    if not settings_obj.host or not settings_obj.from_email:
        raise ValidationError({"detail": "SMTP incompleto: host y from_email son obligatorios."})
    if not settings_obj.password_configured:
        raise ValidationError({"detail": "SMTP incompleto: falta la contraseña."})
    return settings_obj


def _email_domain(email: str) -> str:
    parts = (email or "").strip().lower().rsplit("@", 1)
    return parts[1] if len(parts) == 2 else ""


def _sender_identity(sender, settings_obj: CompanyEmailSettings) -> tuple[str | None, str, list[str]]:
    """
    Remitente visible del asesor si tiene email del mismo dominio que from_email de la empresa.
    Retorna (from_email_override | None, from_name, reply_to_list).
    """
    profile = UserProfile.objects.filter(user=sender).select_related("user").first()
    if profile:
        user_email = profile.resolve_reply_to_email()
        display_name = profile.resolve_email_display_name()
    else:
        user_email = (getattr(sender, "email", None) or "").strip()
        full = f"{(getattr(sender, 'first_name', '') or '').strip()} {(getattr(sender, 'last_name', '') or '').strip()}".strip()
        display_name = full or (getattr(sender, "username", "") or "")

    reply_to = [user_email] if user_email else []
    company_domain = _email_domain(settings_obj.from_email)
    user_domain = _email_domain(user_email)

    if user_email and company_domain and user_domain == company_domain:
        return user_email, display_name, reply_to
    return None, display_name, reply_to


def _escape_html(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _resolve_signature_named_urls(sender, signature_url: str | None) -> dict[str, str]:
    """CIDs de la firma del asesor → URL remota. El HTML usa src=\"cid:…\"."""
    sig = (signature_url or "").strip()
    if not sig:
        profile = UserProfile.objects.filter(user=sender).first()
        sig = ((profile.signature_url or "").strip() if profile else "")
    return iter_named_cids(
        [
            ("firma_logo", sig),
            ("firma_vendedor", sig),
        ]
    )


def _build_html_body(
    *,
    message: str,
    html_message: str | None,
    named_urls: dict[str, str],
) -> str | None:
    """
    Prioridad: html_message del front (se reescribe a CID después).
    Si no hay HTML, arma firma en tablas + cid: (Outlook).
    """
    html = (html_message or "").strip()
    if html:
        return html

    has_sig = bool(named_urls.get("firma_vendedor") or named_urls.get("firma_logo"))
    if not has_sig:
        return None

    safe_text = _escape_html(message or "").replace("\n", "<br/>")
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
        'style="border-collapse:collapse;">'
        '<tr><td style="font-family:Arial,sans-serif;font-size:14px;line-height:1.5;color:#222222;">'
        f"{safe_text}</td></tr>"
        '<tr><td style="padding-top:16px;">'
        '<img src="cid:firma_vendedor" alt="Firma" width="420" border="0" '
        'style="display:block;border:0;outline:none;text-decoration:none;width:420px;max-width:100%;height:auto;" />'
        "</td></tr></table>"
    )


def send_quotation_email(
    *,
    quotation: Quotation,
    sender,
    to: list[str] | None,
    cc: list[str] | None,
    subject: str | None,
    message: str,
    pdf_base64: str,
    pdf_filename: str | None,
    html_message: str | None = None,
    signature_url: str | None = None,
) -> dict[str, Any]:
    recipients = [e.strip() for e in (to or []) if e and str(e).strip()]
    if not recipients:
        contact = quotation.client_contact
        contact_email = (contact.email or "").strip() if contact else ""
        if not contact_email:
            raise ValidationError(
                {
                    "to": (
                        "Indique destinatarios o asigne un contacto con email a la cotización."
                    )
                }
            )
        recipients = [contact_email]

    cc_list = [e.strip() for e in (cc or []) if e and str(e).strip()]
    subj = (subject or "").strip() or f"Cotización {quotation.correlativo}"
    filename = (pdf_filename or "").strip() or f"cotizacion-{quotation.correlativo}.pdf"
    pdf_bytes = _decode_pdf_base64(pdf_base64)
    plain = message or ""

    company_id = _resolve_company_id(quotation, sender)
    named_urls = _resolve_signature_named_urls(sender, signature_url)
    html_body = _build_html_body(
        message=plain,
        html_message=html_message,
        named_urls=named_urls,
    )
    inline_images = []
    if html_body:
        html_body, inline_images = prepare_html_inline_images(html_body, named_urls=named_urls)

    settings_obj = _get_active_smtp(company_id)
    from_override, from_name, reply_to = _sender_identity(sender, settings_obj)

    # CC de la petición + CC por defecto de la empresa (sin duplicados)
    merged_cc: list[str] = []
    seen_cc: set[str] = set()
    for email in settings_obj.resolved_default_cc() + cc_list:
        key = email.lower()
        if key not in seen_cc:
            seen_cc.add(key)
            merged_cc.append(email)
    cc_list = merged_cc

    # Copia oculta (BCC) al correo del asesor que envía
    bcc_list: list[str] = []
    sender_copy = (reply_to[0] if reply_to else "").strip()
    if not sender_copy:
        profile = UserProfile.objects.filter(user=sender).select_related("user").first()
        if profile:
            sender_copy = profile.resolve_reply_to_email()
        else:
            sender_copy = (getattr(sender, "email", None) or "").strip()
    if sender_copy:
        already = {e.lower() for e in recipients + cc_list}
        if sender_copy.lower() not in already:
            bcc_list.append(sender_copy)

    log = QuotationEmailLog(
        quotation=quotation,
        sent_by=sender if getattr(sender, "is_authenticated", False) else None,
        to_emails=_join_emails(recipients),
        cc_emails=_join_emails(cc_list),
        subject=subj,
        status=QuotationEmailLog.Status.FAILED,
        error_message="",
    )

    try:
        send_with_company_smtp(
            settings_obj,
            to=recipients,
            cc=cc_list,
            bcc=bcc_list,
            subject=subj,
            body=plain,
            html_body=html_body,
            reply_to=reply_to,
            from_email=from_override,
            from_name=from_name if from_override else None,
            attachments=[(filename, pdf_bytes, "application/pdf")],
            inline_images=inline_images,
        )
    except Exception as exc:
        log.error_message = str(exc)[:2000]
        log.save()
        raise SmtpSendError(str(exc), log_id=log.pk) from exc

    log.status = QuotationEmailLog.Status.SENT
    log.error_message = ""
    log.save()
    return {
        "status": "sent",
        "to": recipients,
        "cc": cc_list,
        "bcc": bcc_list,
        "log_id": log.pk,
        "from_email": from_override or settings_obj.from_email,
        "html": bool(html_body),
    }
