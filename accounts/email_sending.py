"""Envío SMTP usando CompanyEmailSettings (multi-tenant)."""

from __future__ import annotations

from email.utils import formataddr
from typing import Sequence

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.mail.backends.smtp import EmailBackend
from django.utils.encoding import force_str

from .email_inline import InlineImage
from .models import CompanyEmailSettings


class EmailMultiRelated(EmailMultiAlternatives):
    """
    multipart/mixed
      multipart/related
        multipart/alternative (text/plain + text/html)
        image/* (Content-Disposition: inline, Content-ID)
      application/pdf (attachment)
    """

    def __init__(self, *args, **kwargs):
        self.related_images: list[InlineImage] = []
        super().__init__(*args, **kwargs)

    def attach_related_image(self, image: InlineImage) -> None:
        self.related_images.append(image)

    def _add_bodies(self, msg):
        if not self.related_images:
            super()._add_bodies(msg)
            return

        encoding = self.encoding or settings.DEFAULT_CHARSET
        html = None
        for alternative in getattr(self, "alternatives", []):
            if alternative.mimetype == "text/html":
                html = alternative.content
                break

        inner = type(msg)(policy=msg.policy)
        body = force_str(self.body or "", encoding=encoding, errors="surrogateescape")
        inner.set_content(body, subtype="plain", charset=encoding)
        if html is not None:
            if isinstance(html, bytes):
                html = html.decode()
            inner.add_alternative(html, subtype="html", charset=encoding)

        msg.make_related()
        msg.attach(inner)
        for image in self.related_images:
            subtype = image.mimetype.split("/", 1)[-1] if "/" in image.mimetype else "png"
            if subtype == "jpg":
                subtype = "jpeg"
            part = type(msg)(policy=msg.policy)
            part.set_content(
                image.content,
                maintype="image",
                subtype=subtype,
                cid=image.cid,
                filename=image.filename,
                disposition="inline",
            )
            msg.attach(part)


def build_smtp_backend(settings_obj: CompanyEmailSettings) -> EmailBackend:
    return EmailBackend(
        host=settings_obj.host,
        port=settings_obj.port,
        username=settings_obj.username or None,
        password=settings_obj.get_password() or None,
        use_tls=settings_obj.use_tls,
        use_ssl=settings_obj.use_ssl,
        fail_silently=False,
    )


def company_from_header(settings_obj: CompanyEmailSettings) -> str:
    email = (settings_obj.from_email or "").strip()
    name = (settings_obj.from_name or "").strip()
    if name:
        return formataddr((name, email))
    return email


def format_from_header(*, email: str, name: str = "") -> str:
    email = (email or "").strip()
    name = (name or "").strip()
    if name and email:
        return formataddr((name, email))
    return email


def send_with_company_smtp(
    settings_obj: CompanyEmailSettings,
    *,
    to: Sequence[str],
    subject: str,
    body: str,
    html_body: str | None = None,
    cc: Sequence[str] | None = None,
    bcc: Sequence[str] | None = None,
    reply_to: Sequence[str] | None = None,
    from_email: str | None = None,
    from_name: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
    inline_images: list[InlineImage] | None = None,
) -> None:
    """
    attachments: lista de (filename, content_bytes, mimetype) — Disposition: attachment
    inline_images: partes related con Content-ID (no aparecen como adjuntos normales)

    Si se pasan from_email/from_name se usan como remitente visible (mismo dominio).
    Si no, se usa from_email/from_name de la empresa.
    La autenticación SMTP sigue siendo siempre la de la compañía.

    body = text/plain; si html_body viene, se adjunta como text/html (multipart/alternative).
    """
    backend = build_smtp_backend(settings_obj)
    if from_email:
        header_from = format_from_header(email=from_email, name=from_name or "")
    else:
        header_from = company_from_header(settings_obj)
    message = EmailMultiRelated(
        subject=subject,
        body=body or "",
        from_email=header_from,
        to=list(to),
        cc=list(cc or []),
        bcc=list(bcc or []),
        reply_to=list(reply_to or []),
        connection=backend,
    )
    if html_body and str(html_body).strip():
        message.attach_alternative(str(html_body), "text/html")
    for image in inline_images or []:
        message.attach_related_image(image)
    for filename, content, mimetype in attachments or []:
        message.attach(filename, content, mimetype)
    message.send(fail_silently=False)
