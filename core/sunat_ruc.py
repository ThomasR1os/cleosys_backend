"""
Consulta de datos de contribuyente en la web pública de SUNAT (Consulta RUC).

La página usa reCAPTCHA v3 en el cliente; un POST directo sin token es rechazado.
Se automatiza el flujo con Playwright (Chromium) para reproducir el navegador.
"""

from __future__ import annotations

import atexit
import os
import re
import threading
import time
from typing import Any

from bs4 import BeautifulSoup

SUNAT_CONSULTA_URL = (
    "https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/FrameCriterioBusquedaWeb.jsp"
)
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# Cache en memoria (por proceso) para acelerar consultas repetidas.
# Nota: en producción con múltiples workers, cada worker tendrá su propio cache.
_CACHE_TTL_S = 12 * 60 * 60  # 12 horas
_cache_lock = threading.Lock()
_ruc_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _playwright_timeout_ms() -> int:
    raw = os.environ.get("SUNAT_PLAYWRIGHT_TIMEOUT_MS", "").strip()
    if raw.isdigit():
        return max(5_000, min(int(raw), 120_000))
    return 60_000


class SunatConsultaError(Exception):
    """Error al consultar o interpretar la respuesta de SUNAT."""


def validate_ruc_checksum(ruc: str) -> bool:
    """Valida RUC de 11 dígitos con dígito verificador (misma lógica que la web SUNAT)."""
    ruc = ruc.strip()
    if len(ruc) != 11 or not ruc.isdigit():
        return False
    suma = 0
    x = 6
    for i in range(10):
        if i == 4:
            x = 8
        digito = int(ruc[i])
        x -= 1
        suma += digito * x
    resto = suma % 11
    resto = 11 - resto
    if resto >= 10:
        resto -= 10
    return resto == int(ruc[10])


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_sunat_result_html(html: str) -> dict[str, Any]:
    """Parsea el HTML de la página de resultado de consulta por RUC."""
    if "Pagina de Error" in html or "Surgieron problemas al procesar" in html:
        raise SunatConsultaError(
            "SUNAT devolvió un error al procesar la consulta. Intente de nuevo más tarde."
        )

    soup = BeautifulSoup(html, "lxml")
    heading = None
    for div in soup.find_all("div", class_=re.compile(r"panel-heading")):
        if "Resultado de la Búsqueda" in div.get_text():
            heading = div
            break
    if not heading:
        raise SunatConsultaError(
            "No se encontró el bloque de resultado. Es posible que el RUC no exista o la página haya cambiado."
        )

    panel = heading.find_parent("div", class_=re.compile(r"panel"))
    if not panel:
        raise SunatConsultaError("Estructura de página inesperada (panel).")

    list_group = panel.find("div", class_="list-group")
    if not list_group:
        raise SunatConsultaError("Estructura de página inesperada (list-group).")

    fields: dict[str, str | list[str]] = {}

    for item in list_group.find_all("div", class_="list-group-item", recursive=False):
        row = item.find("div", class_="row")
        if not row:
            continue
        cols = row.find_all(
            "div",
            class_=lambda c: c and isinstance(c, (list, str)) and "col-" in str(c),
        )
        i = 0
        while i + 1 < len(cols):
            label_cell = cols[i]
            value_cell = cols[i + 1]
            label_el = label_cell.find("h4", class_=re.compile(r"list-group-item-heading"))
            if not label_el:
                i += 1
                continue
            label = _normalize_ws(label_el.get_text()).rstrip(":").strip()
            if not label:
                i += 2
                continue

            table = value_cell.find("table", class_=re.compile(r"tblResultado"))
            if table:
                lines = []
                for td in table.select("tbody tr td"):
                    t = _normalize_ws(td.get_text())
                    if t:
                        lines.append(t)
                fields[label] = lines
            else:
                val_el = value_cell.find(["h4", "p"])
                if val_el:
                    value = _normalize_ws(val_el.get_text())
                else:
                    value = _normalize_ws(value_cell.get_text())
                fields[label] = value

            i += 2

    if not fields:
        raise SunatConsultaError("No se pudieron extraer campos del resultado.")

    ruc_line = fields.get("Número de RUC")
    ruc_num: str | None = None
    razon_social: str | None = None
    if isinstance(ruc_line, str) and ruc_line:
        m = re.match(r"^(\d{11})\s*-\s*(.+)$", ruc_line)
        if m:
            ruc_num, razon_social = m.group(1), m.group(2).strip()

    return {
        "ruc": ruc_num,
        "razon_social": razon_social,
        "fields": fields,
    }


class _PlaywrightBrowser:
    """
    Reusa un navegador Chromium por proceso para evitar el overhead de arrancar
    Playwright/Chromium en cada request.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started = False
        self._playwright = None
        self._browser = None

    def _ensure_started(self) -> None:
        if self._started:
            return
        from playwright.sync_api import sync_playwright

        try:
            self._playwright = sync_playwright().start()
            # En Docker / PaaS hace falta --no-sandbox; --disable-dev-shm-usage evita caídas por /dev/shm pequeño.
            self._browser = self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            self._started = True
        except Exception as e:
            err = str(e).lower()
            if "executable doesn't exist" in err or "browserType.launch" in err:
                raise SunatConsultaError(
                    "Chromium no está disponible en el servidor. Instale los browsers de Playwright "
                    "(p. ej. `playwright install chromium`) y en Linux las dependencias del sistema "
                    "(`playwright install-deps`) o despliegue con la imagen Docker oficial de Playwright."
                ) from e
            raise

    def close(self) -> None:
        with self._lock:
            if not self._started:
                return
            try:
                if self._browser:
                    self._browser.close()
            finally:
                if self._playwright:
                    self._playwright.stop()
                self._browser = None
                self._playwright = None
                self._started = False

    def fetch_html(self, ruc: str, *, timeout_ms: int) -> str:
        # Serializamos por lock: evita pelear por recursos del browser en dev server.
        # En prod puedes escalar con workers/procesos.
        with self._lock:
            self._ensure_started()
            assert self._browser is not None
            ctx = self._browser.new_context(
                user_agent=_DEFAULT_UA,
                locale="es-PE",
                viewport={"width": 1280, "height": 720},
            )
            # Bloquear recursos pesados acelera bastante (CSS, imágenes, fuentes).
            def _route_handler(route):
                rt = route.request.resource_type
                if rt in {"image", "stylesheet", "font", "media"}:
                    return route.abort()
                return route.continue_()

            ctx.route("**/*", _route_handler)
            page = ctx.new_page()
            try:
                page.goto(SUNAT_CONSULTA_URL, wait_until="domcontentloaded", timeout=timeout_ms)
                page.fill("#txtRuc", ruc.strip())
                # A veces un overlay (divCarga) intercepta el click; disparar el handler vía JS es más estable/rápido.
                page.evaluate("document.querySelector('#btnAceptar')?.click()")
                # Mejor que networkidle: esperamos el elemento específico del resultado.
                page.wait_for_selector("div.panel-heading", timeout=timeout_ms)
                # Aseguramos que el heading sea el esperado (evita devolver criterio).
                page.wait_for_function(
                    "document.body && document.body.innerText.includes('Resultado de la Búsqueda')",
                    timeout=timeout_ms,
                )
                return page.content()
            finally:
                ctx.close()


_pw_browser = _PlaywrightBrowser()
atexit.register(_pw_browser.close)


def _cache_get(ruc: str) -> dict[str, Any] | None:
    now = time.time()
    with _cache_lock:
        hit = _ruc_cache.get(ruc)
        if not hit:
            return None
        ts, data = hit
        if now - ts > _CACHE_TTL_S:
            _ruc_cache.pop(ruc, None)
            return None
        return data


def _cache_set(ruc: str, data: dict[str, Any]) -> None:
    with _cache_lock:
        _ruc_cache[ruc] = (time.time(), data)


def fetch_ruc_with_playwright(ruc: str, *, timeout_ms: int | None = None) -> dict[str, Any]:
    """
    Abre la consulta SUNAT en Chromium, envía el RUC y devuelve el dict parseado.
    Requiere: pip install playwright && playwright install chromium (y en Linux, dependencias del sistema).

    ``timeout_ms`` por defecto se toma de SUNAT_PLAYWRIGHT_TIMEOUT_MS (o 60000 ms).
    """
    if timeout_ms is None:
        timeout_ms = _playwright_timeout_ms()

    if not validate_ruc_checksum(ruc):
        raise SunatConsultaError("El número de RUC no es válido (formato o dígito verificador).")

    ruc = ruc.strip()
    cached = _cache_get(ruc)
    if cached is not None:
        return cached

    try:
        html = _pw_browser.fetch_html(ruc, timeout_ms=timeout_ms)
    except SunatConsultaError:
        raise
    except Exception as e:
        if "Timeout" in type(e).__name__ or "timeout" in str(e).lower():
            raise SunatConsultaError(
                "Tiempo de espera agotado al consultar SUNAT. Revise la red del servidor, "
                "aumente SUNAT_PLAYWRIGHT_TIMEOUT_MS o el límite de tiempo del hosting (p. ej. Render)."
            ) from e
        raise

    data = parse_sunat_result_html(html)
    _cache_set(ruc, data)
    return data
