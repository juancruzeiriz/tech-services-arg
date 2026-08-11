"""Detector forense de obsolescencia sobre el HTML crudo del prospecto.

Responde, con evidencia citable y sin que un humano tenga que mirar el sitio,
la pregunta "¿esta web es vieja?": maquetación con tablas, jQuery sin
actualizar desde hace una década, Universal Analytics (apagado por Google en
julio de 2023), un copyright congelado en el pie de página, ausencia de
`<meta viewport>`, HTTP sin cifrar, sin JSON-LD de negocio local, sin enlace a
Facebook/Instagram, y una paleta de colores estadísticamente típica de sitios
de hace más de diez años.

Cada detector opera sobre el HTML que `contact.py` ya descarga para buscar el
formulario de contacto — cero requests HTTP adicionales.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from gtm.factory.findings import Finding

_HEX_COLOR_RE = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
_JQUERY_RE = re.compile(r"jquery[.-](\d+)\.(\d+)(?:\.(\d+))?", re.IGNORECASE)
_COPYRIGHT_RE = re.compile(r"(?:©|copyright)\s*(?:\d{4}\s*[-–]\s*)?(\d{4})", re.IGNORECASE)
_PHONE_RE = re.compile(r"\b(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]\d{4}\b")

_PRESENTATIONAL_TABLE_ATTRS = ("width", "bgcolor", "align", "cellpadding", "cellspacing")

_DATED_PALETTE_THRESHOLD = 0.4
_STALE_COPYRIGHT_YEARS = 3

# Solo las dos redes que de verdad importan en este nicho -- no Twitter/X ni
# LinkedIn, que son mucho menos comunes entre home services hispanos en USA.
_SOCIAL_DOMAINS = ("facebook.com", "instagram.com")


def analyse_html(html: str, url: str) -> list[Finding]:
    """Corre todos los detectores sobre `html`.

    Un solo try/except alrededor de toda la secuencia: un HTML roto es
    exactamente el tipo de sitio que se quiere detectar, así que el parser
    explotando no puede costar el prospecto entero. Cada detector agrega a
    `findings` antes de que el siguiente corra, así que si alguno falla a
    mitad de camino, los hallazgos ya encontrados se conservan igual.
    """
    findings: list[Finding] = []
    try:
        soup = BeautifulSoup(html, "html.parser")

        _check_https(url, findings)
        _check_viewport(soup, findings)
        _check_tables(soup, findings)
        _check_analytics(soup, findings)
        _check_copyright(soup, findings)
        _check_jquery(soup, findings)
        _check_tel_link(soup, findings)
        _check_local_schema(soup, findings)
        _check_social_links(soup, findings)
        _check_palette(html, findings)
    except Exception:  # noqa: BLE001 - ver docstring del módulo
        pass

    return findings


def _check_https(url: str, findings: list[Finding]) -> None:
    scheme = urlparse(url).scheme
    if scheme == "http":
        findings.append(Finding(code="no_https", evidence=url))


def _check_viewport(soup: BeautifulSoup, findings: list[Finding]) -> None:
    if soup.find("meta", attrs={"name": "viewport"}) is None:
        # Evidencia sin "sin"/"missing": esas palabras viven en el template de
        # findings.py, que ya está en el idioma correcto -- acá solo va el
        # dato neutral (el nombre de la etiqueta), igual en cualquier idioma.
        findings.append(Finding(code="no_viewport", evidence='<meta name="viewport">'))


def _is_presentational_table(table: object) -> bool:
    if table.find("th") is not None:  # type: ignore[attr-defined]
        return False
    role = (table.get("role") or "").lower()  # type: ignore[attr-defined]
    if role in ("table", "grid", "treegrid"):
        return False
    has_presentational_attr = any(
        table.has_attr(attr) for attr in _PRESENTATIONAL_TABLE_ATTRS  # type: ignore[attr-defined]
    )
    is_nested = table.find_parent("table") is not None  # type: ignore[attr-defined]
    return has_presentational_attr or is_nested


def _check_tables(soup: BeautifulSoup, findings: list[Finding]) -> None:
    tables = soup.find_all("table")
    presentational = [t for t in tables if _is_presentational_table(t)]
    if not presentational:
        return
    nested = sum(1 for t in presentational if t.find_parent("table") is not None)
    # "count|nested" crudo, sin prosa: findings.py arma la frase en el idioma
    # correcto recién al renderizar (mismo mecanismo que ya usa stale_since
    # para la fecha) -- acá no se sabe en qué idioma va a salir el mensaje.
    findings.append(Finding(code="table_layout", evidence=f"{len(presentational)}|{nested}"))


def _check_analytics(soup: BeautifulSoup, findings: list[Finding]) -> None:
    srcs = [str(tag.get("src", "")) for tag in soup.find_all("script") if tag.get("src")]
    has_modern = any("gtag/js" in src or "gtagjs" in src for src in srcs)
    if has_modern:
        return
    dead = next((src for src in srcs if "google-analytics.com/ga.js" in src or "/analytics.js" in src), None)
    if dead:
        findings.append(Finding(code="dead_analytics", evidence=dead))


def _check_copyright(soup: BeautifulSoup, findings: list[Finding]) -> None:
    text = soup.get_text()
    years = [int(m.group(1)) for m in _COPYRIGHT_RE.finditer(text)]
    if not years:
        return
    latest = max(years)
    current_year = datetime.now(UTC).year
    if current_year - latest >= _STALE_COPYRIGHT_YEARS:
        findings.append(Finding(code="stale_copyright", evidence=f"© {latest}"))


def _check_jquery(soup: BeautifulSoup, findings: list[Finding]) -> None:
    for tag in soup.find_all("script"):
        src = str(tag.get("src", ""))
        match = _JQUERY_RE.search(src)
        if not match:
            continue
        major = int(match.group(1))
        if major < 3:
            version = ".".join(g for g in match.groups() if g is not None)
            findings.append(Finding(code="legacy_jquery", evidence=version))
            return


def _check_tel_link(soup: BeautifulSoup, findings: list[Finding]) -> None:
    has_tel_link = any(
        str(a.get("href", "")).lower().startswith("tel:") for a in soup.find_all("a")
    )
    if has_tel_link:
        return
    text = soup.get_text()
    match = _PHONE_RE.search(text)
    if match:
        # El número encontrado, no una descripción de la situación: es un dato
        # citable de verdad (y, de paso, no necesita traducción -- un número
        # de teléfono se lee igual en cualquier idioma).
        findings.append(Finding(code="no_tel_link", evidence=match.group(0)))


def _check_local_schema(soup: BeautifulSoup, findings: list[Finding]) -> None:
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    for tag in scripts:
        if "LocalBusiness" in (tag.string or ""):
            return
    # "sin"/"missing" vive en el template de findings.py; acá solo el nombre
    # del tipo de schema, neutral en cualquier idioma.
    findings.append(Finding(code="no_local_schema", evidence="LocalBusiness"))


def _check_social_links(soup: BeautifulSoup, findings: list[Finding]) -> None:
    """Ausencia de link ≠ ausencia de página: por eso este hallazgo es LOW, no
    CRITICAL como `no_tel_link`. Solo mide si el sitio *enlaza* a su red
    social, no si el negocio tiene una.
    """
    has_social = any(
        any(domain in str(a.get("href", "")).lower() for domain in _SOCIAL_DOMAINS)
        for a in soup.find_all("a")
    )
    if has_social:
        return
    # Los dominios que se buscaron, no una frase armada: ya lo dice el
    # template de findings.py que no hay link, y "facebook.com"/"instagram.com"
    # no cambian de idioma.
    findings.append(
        Finding(code="no_social_presence", evidence=", ".join(_SOCIAL_DOMAINS))
    )


def _check_palette(html: str, findings: list[Finding]) -> None:
    colors = _HEX_COLOR_RE.findall(html)
    normalised = [_normalise_hex(c) for c in colors]
    if len(normalised) < 3:
        return
    signal = palette_age_signal(normalised)
    if signal > _DATED_PALETTE_THRESHOLD:
        # Solo el número, crudo: findings.py arma "N colores saturados"/"N
        # saturated colours" en el idioma correcto al renderizar (mismo
        # mecanismo que table_layout, ver _formatted_color_count).
        findings.append(
            Finding(code="dated_palette", evidence=str(len(set(normalised))))
        )


def _normalise_hex(value: str) -> str:
    value = value.removeprefix("#")
    if len(value) == 3:
        return "".join(ch * 2 for ch in value)
    return value


def _hsl_saturation(hex6: str) -> float:
    r = int(hex6[0:2], 16) / 255
    g = int(hex6[2:4], 16) / 255
    b = int(hex6[4:6], 16) / 255
    hi, lo = max(r, g, b), min(r, g, b)
    if hi == lo:
        return 0.0
    lightness = (hi + lo) / 2
    delta = hi - lo
    return delta / (2 - hi - lo) if lightness > 0.5 else delta / (hi + lo)


_WEB_SAFE_COMPONENTS = frozenset({"00", "33", "66", "99", "cc", "ff"})


def _is_web_safe(hex6: str) -> bool:
    return all(hex6[i : i + 2].lower() in _WEB_SAFE_COMPONENTS for i in (0, 2, 4))


def palette_age_signal(colors: list[str]) -> float:
    """Estima, en [0,1], qué tan típica es la paleta de un sitio de hace más
    de una década. Combina tres señales con pesos iguales:

    - Fracción de colores muy saturados (>0.85): las paletas de hace 15 años
      usan colores puros (rojo, azul, verde); las de hoy son mayormente
      desaturadas con un único acento.
    - Fracción de colores "web-safe" (componentes en {00,33,66,99,CC,FF}):
      un resabio directo de la paleta de 216 colores de los 90.
    - Cantidad de colores distintos, normalizada a 30: una paleta moderna
      tiene 4-8 colores; una de hace 15-20 años, 15-40.
    """
    if not colors:
        return 0.0

    normalised = [_normalise_hex(c) for c in colors]
    n = len(normalised)

    saturated = sum(1 for c in normalised if _hsl_saturation(c) > 0.85)
    web_safe = sum(1 for c in normalised if _is_web_safe(c))
    distinct = len(set(normalised))

    saturated_frac = saturated / n
    web_safe_frac = web_safe / n
    distinct_frac = min(1.0, distinct / 30)

    return (saturated_frac + web_safe_frac + distinct_frac) / 3
