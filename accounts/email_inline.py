"""Imágenes inline (CID) para correos HTML compatibles con Outlook y Gmail."""

from __future__ import annotations

import base64
import binascii
import hashlib
import html as html_lib
import re
from dataclasses import dataclass
from typing import Iterable
from urllib.error import URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

MAX_INLINE_IMAGE_BYTES = 2 * 1024 * 1024
_FETCH_TIMEOUT_SEC = 15
_CID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_DATA_URI_RE = re.compile(
    r"^data:image/(png|jpe?g|gif);base64,(.+)$",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class InlineImage:
    cid: str
    content: bytes
    mimetype: str
    filename: str


def fetch_remote_image(url: str) -> tuple[bytes, str] | None:
    """Descarga una imagen pública. None si falla o no es png/jpeg/gif."""
    target = (url or "").strip()
    if not target.startswith(("http://", "https://")):
        return None
    req = Request(target, headers={"User-Agent": "CleoSys-Mailer/1.0"})
    try:
        with urlopen(req, timeout=_FETCH_TIMEOUT_SEC) as resp:
            content_type = (resp.headers.get_content_type() or "").lower()
            data = resp.read(MAX_INLINE_IMAGE_BYTES + 1)
    except (URLError, TimeoutError, OSError, ValueError):
        return None
    if not data or len(data) > MAX_INLINE_IMAGE_BYTES:
        return None
    mimetype = _sniff_image_mimetype(data, content_type)
    if not mimetype:
        return None
    return data, mimetype


def decode_data_uri_image(src: str) -> tuple[bytes, str] | None:
    raw = (src or "").strip()
    match = _DATA_URI_RE.match(raw)
    if not match:
        return None
    subtype = match.group(1).lower()
    if subtype == "jpg":
        subtype = "jpeg"
    try:
        data = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError):
        return None
    if not data or len(data) > MAX_INLINE_IMAGE_BYTES:
        return None
    mimetype = _sniff_image_mimetype(data, f"image/{subtype}") or f"image/{subtype}"
    return data, mimetype


def prepare_html_inline_images(
    html: str,
    *,
    named_urls: dict[str, str] | None = None,
) -> tuple[str, list[InlineImage]]:
    """
    Reescribe <img src> a cid:… y devuelve las partes inline.
    named_urls: cid conocido → URL (p. ej. firma_vendedor, logo_empresa).
    """
    html_text = (html or "").strip()
    if not html_text:
        return html_text, []

    names = {
        cid: (url or "").strip()
        for cid, url in (named_urls or {}).items()
        if _CID_RE.match(cid)
    }
    url_to_cid = {url: cid for cid, url in names.items() if url}
    soup = BeautifulSoup(html_text, "html.parser")
    loaded: dict[str, InlineImage] = {}
    unused_imgs: list = []

    for img in soup.find_all("img"):
        src = html_lib.unescape((img.get("src") or "").strip())
        if not src:
            unused_imgs.append(img)
            continue

        cid, payload = _resolve_img_source(src, names, url_to_cid, loaded)
        if cid and payload:
            loaded[cid] = payload
            img["src"] = f"cid:{cid}"
            img["border"] = img.get("border") or "0"
        else:
            unused_imgs.append(img)

    for img in unused_imgs:
        img.decompose()

    return str(soup), list(loaded.values())


def _resolve_img_source(
    src: str,
    names: dict[str, str],
    url_to_cid: dict[str, str],
    loaded: dict[str, InlineImage],
) -> tuple[str | None, InlineImage | None]:
    if src.lower().startswith("cid:"):
        cid = src[4:].strip().strip("<>")
        if not _CID_RE.match(cid):
            return None, None
        if cid in loaded:
            return cid, loaded[cid]
        url = names.get(cid, "")
        payload = _image_from_url(cid, url) if url else None
        return (cid, payload) if payload else (None, None)

    if src.lower().startswith("data:image/"):
        cid = _cid_from_key(
            f"data:{hashlib.sha1(src.encode('utf-8', errors='ignore')).hexdigest()}"
        )
        if cid in loaded:
            return cid, loaded[cid]
        decoded = decode_data_uri_image(src)
        if not decoded:
            return None, None
        data, mimetype = decoded
        return cid, _to_inline(cid, data, mimetype)

    cid = url_to_cid.get(src) or _cid_from_key(src)
    if cid in loaded:
        return cid, loaded[cid]
    payload = _image_from_url(cid, src)
    return (cid, payload) if payload else (None, None)


def _image_from_url(cid: str, url: str) -> InlineImage | None:
    fetched = fetch_remote_image(url)
    if not fetched:
        return None
    data, mimetype = fetched
    return _to_inline(cid, data, mimetype)


def _to_inline(cid: str, data: bytes, mimetype: str) -> InlineImage:
    ext = "jpg" if mimetype == "image/jpeg" else mimetype.split("/", 1)[-1]
    return InlineImage(
        cid=cid,
        content=data,
        mimetype=mimetype,
        filename=f"{cid}.{ext}",
    )


def _cid_from_key(key: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"img_{digest}"


def _sniff_image_mimetype(data: bytes, content_type: str) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    normalized = (content_type or "").split(";")[0].strip().lower()
    if normalized == "image/jpg":
        return "image/jpeg"
    if normalized in {"image/png", "image/jpeg", "image/gif"}:
        return normalized
    return None


def iter_named_cids(pairs: Iterable[tuple[str, str | None]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for cid, url in pairs:
        value = (url or "").strip()
        if value and _CID_RE.match(cid):
            result[cid] = value
    return result
