"""
Consulta de datos de contribuyente en la web pública de SUNAT (Consulta RUC).

La página usa reCAPTCHA v3 en el cliente; un POST directo sin token es rechazado.
Se automatiza el flujo con Playwright (Chromium) para reproducir el navegador.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

SUNAT_CONSULTA_URL = (
    "https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/FrameCriterioBusquedaWeb.jsp"
)


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


def fetch_ruc_with_playwright(ruc: str, *, timeout_ms: int = 90_000) -> dict[str, Any]:
    """
    Abre la consulta SUNAT en Chromium, envía el RUC y devuelve el dict parseado.
    Requiere: pip install playwright && playwright install chromium
    """
    from playwright.sync_api import sync_playwright

    if not validate_ruc_checksum(ruc):
        raise SunatConsultaError("El número de RUC no es válido (formato o dígito verificador).")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="es-PE",
                viewport={"width": 1280, "height": 720},
            )
            page = ctx.new_page()
            page.goto(SUNAT_CONSULTA_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            page.fill("#txtRuc", ruc.strip())
            page.click("#btnAceptar")
            page.wait_for_load_state("networkidle", timeout=timeout_ms)
            html = page.content()
            ctx.close()
        finally:
            browser.close()

    return parse_sunat_result_html(html)
