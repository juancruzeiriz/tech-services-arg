"""Catálogo de hallazgos: cada defecto detectable, con su línea de venta.

Existe por la misma regla que ya hace cumplir `outreach.py`: el pipeline no
inventa hechos sobre el prospecto. Un hallazgo lleva SIEMPRE la evidencia que lo
respalda (el número, la fecha, la etiqueta encontrada), porque la línea que
termina en el guion de la llamada la cita textual — y el dueño del negocio puede
verificarla en el momento.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from gtm.factory.archive import format_month_year
from gtm.factory.types import Language

# Códigos cuya evidencia se guarda en un formato neutral (ISO) y se traduce a
# prosa recién al renderizar, porque `Finding.evidence` es un solo string y no
# puede ser dos idiomas a la vez. `score.py` guarda la fecha con
# `date.isoformat()`; acá se reformatea a "marzo de 2016" / "March 2016" según
# el idioma que pida `sales_line`.
_DATE_EVIDENCE_CODES = frozenset({"stale_since"})


class Severity(StrEnum):
    CRITICAL = "critical"
    """Pierde plata hoy: no se puede llamar, no carga, no es seguro."""

    HIGH = "high"
    """Pierde tráfico o conversión de forma medible."""

    MEDIUM = "medium"
    """Deuda visible, pero no un bloqueador directo de la venta."""

    LOW = "low"
    """Higiene: suma al cuadro general, no mueve la aguja solo."""


class Dimension(StrEnum):
    SPEED = "speed"
    MOBILE = "mobile"
    SEO = "seo"
    MODERNITY = "modernity"
    CONVERSION = "conversion"


@dataclass(frozen=True, slots=True)
class FindingSpec:
    dimension: Dimension
    severity: Severity
    weight: float
    sales_line_en: str
    """Con `{evidence}` para interpolar — ver `Finding.sales_line`."""
    sales_line_es: str


@dataclass(frozen=True, slots=True)
class Finding:
    """Un hallazgo concreto sobre UN prospecto, con su evidencia observada."""

    code: str
    evidence: str
    weight: float = 1.0
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def spec(self) -> FindingSpec:
        return FINDINGS[self.code]

    def sales_line(self, language: Language) -> str:
        spec = self.spec
        template = spec.sales_line_es if language is Language.ES else spec.sales_line_en
        return template.format(evidence=self._formatted_evidence(language))

    def _formatted_evidence(self, language: Language) -> str:
        if self.code not in _DATE_EVIDENCE_CODES:
            return self.evidence
        try:
            parsed = date.fromisoformat(self.evidence)
        except ValueError:
            return self.evidence  # evidencia ya no-ISO (o corrupta): mostrar tal cual
        return format_month_year(parsed, language.value)


FINDINGS: dict[str, FindingSpec] = {
    "no_tel_link": FindingSpec(
        Dimension.CONVERSION,
        Severity.CRITICAL,
        3.0,
        "Your phone number is not tappable on a phone ({evidence}) — a customer has to memorise it to call you.",
        "Tu teléfono no se puede tocar desde un celular ({evidence}): el cliente tiene que memorizarlo para llamarte.",
    ),
    "no_contact_method": FindingSpec(
        Dimension.CONVERSION,
        Severity.CRITICAL,
        3.0,
        "There is no way to contact you from the site ({evidence}).",
        "No hay forma de contactarte desde el sitio ({evidence}).",
    ),
    "stale_since": FindingSpec(
        Dimension.MODERNITY,
        Severity.HIGH,
        2.5,
        "Your site has not changed since {evidence}, according to the public Internet Archive record.",
        "Tu sitio no cambia desde {evidence}, según el registro público del Internet Archive.",
    ),
    "crux_lcp_poor": FindingSpec(
        Dimension.SPEED,
        Severity.CRITICAL,
        3.0,
        "Real visitors on phones wait {evidence} for your page to show its main content.",
        "Los visitantes reales desde el celular esperan {evidence} a que aparezca el contenido principal.",
    ),
    "crux_inp_poor": FindingSpec(
        Dimension.SPEED,
        Severity.HIGH,
        2.0,
        "When someone taps a button on your site it takes {evidence} to respond.",
        "Cuando alguien toca un botón en tu sitio, tarda {evidence} en responder.",
    ),
    "no_viewport": FindingSpec(
        Dimension.MOBILE,
        Severity.CRITICAL,
        3.0,
        "Your site was never built for phones ({evidence}) — visitors have to pinch and zoom.",
        "Tu sitio nunca se hizo para celulares ({evidence}): hay que hacer zoom con dos dedos.",
    ),
    "table_layout": FindingSpec(
        Dimension.MODERNITY,
        Severity.HIGH,
        2.0,
        "The page is laid out with HTML tables ({evidence}), a technique abandoned around 2010.",
        "La página está maquetada con tablas HTML ({evidence}), una técnica abandonada cerca de 2010.",
    ),
    "dead_analytics": FindingSpec(
        Dimension.MODERNITY,
        Severity.MEDIUM,
        1.5,
        "Your site still loads Universal Analytics ({evidence}), which Google shut off in July 2023 — you have had no data since.",
        "Tu sitio todavía carga Universal Analytics ({evidence}), que Google apagó en julio de 2023: no tenés datos desde entonces.",
    ),
    "stale_copyright": FindingSpec(
        Dimension.MODERNITY,
        Severity.MEDIUM,
        1.5,
        "The footer of your own site says {evidence}.",
        "El pie de tu propio sitio dice {evidence}.",
    ),
    "legacy_jquery": FindingSpec(
        Dimension.MODERNITY,
        Severity.MEDIUM,
        1.0,
        "The site runs jQuery {evidence}, a version with known security advisories.",
        "El sitio corre jQuery {evidence}, una versión con avisos de seguridad conocidos.",
    ),
    "dated_palette": FindingSpec(
        Dimension.MODERNITY,
        Severity.LOW,
        1.0,
        "The colour palette ({evidence}) is typical of sites built more than a decade ago.",
        "La paleta de colores ({evidence}) es típica de sitios de hace más de una década.",
    ),
    "no_https": FindingSpec(
        Dimension.SEO,
        Severity.CRITICAL,
        3.0,
        "Chrome marks your site as 'Not secure' ({evidence}).",
        "Chrome marca tu sitio como 'No seguro' ({evidence}).",
    ),
    "no_local_schema": FindingSpec(
        Dimension.SEO,
        Severity.MEDIUM,
        1.5,
        "Your site does not tell Google it is a local business ({evidence}).",
        "Tu sitio no le dice a Google que sos un negocio local ({evidence}).",
    ),
    "tap_targets": FindingSpec(
        Dimension.MOBILE,
        Severity.HIGH,
        2.0,
        "Buttons and links are too small to tap reliably ({evidence}).",
        "Los botones y enlaces son demasiado chicos para tocarlos bien ({evidence}).",
    ),
    "tiny_font": FindingSpec(
        Dimension.MOBILE,
        Severity.HIGH,
        2.0,
        "Most of the text is too small to read on a phone ({evidence}).",
        "La mayor parte del texto es demasiado chico para leer en un celular ({evidence}).",
    ),
}
