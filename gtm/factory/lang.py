"""Detección de idioma por prospecto.

`RunContext.language` es un parámetro de la corrida entera, pero el par
elegido (`tree_service × Albuquerque, NM`, ver `docs/PLAN_DIARIO.md` Día 3)
tiene una población de negocios genuinamente mixta -- imponer un solo idioma
a todos es una moneda al aire por negocio. Esta función deriva una señal por
prospecto a partir de datos que ya existen (el nombre del negocio y,
opcionalmente, el HTML de su sitio si el llamador ya lo tiene a mano) sin
agregar ningún request nuevo -- mismo principio que ya siguen
`score.score_prospect` (reusa el HTML que descarga para forensics) y
`contact.find_contact_form` (reusa el HTML que descarga para buscar el
formulario).

No es magia: es una heurística barata que sirve de default razonable, no una
clasificación certera. Se equivoca hacia `default` (inglés salvo que se pida
otra cosa) ante cualquier ambigüedad -- forzar español sobre un negocio
angloparlante es peor que el error inverso, porque deja el pitch entero en
un idioma que el dueño no lee.
"""

from __future__ import annotations

import re
import unicodedata

from gtm.factory.types import Language, Prospect

# Palabras que en la razón social de un negocio de home services en USA son
# indicio de que el dueño (y probablemente sus clientes) hablan español:
# términos de oficio y de familia comunes en nombres hispanos ("Hermanos",
# "e Hijos"). Sin acentos a propósito -- se comparan contra el nombre ya
# normalizado (ver `_strip_accents`).
_SPANISH_NAME_TOKENS = frozenset(
    {
        "jardineria", "jardin", "arboles", "arbol", "poda", "tala",
        "servicios", "hermanos", "hijos", "hijo", "familia",
        "el", "la", "los", "las", "de", "y",
    }
)  # fmt: skip

# Un solo token común ("la", "el", "y") también aparece en nombres en inglés
# ("La Casa Bar"); exigir más de una coincidencia evita el falso positivo.
_MIN_NAME_TOKEN_MATCHES = 2

_ACCENTED_CHAR_RE = re.compile(r"[áéíóúñÁÉÍÓÚÑ]")

_SPANISH_HTML_LANG_RE = re.compile(r'<html[^>]*\blang=["\']es\b', re.IGNORECASE)

_SPANISH_HTML_STOPWORDS = frozenset(
    {"nosotros", "servicios", "contacto", "presupuesto", "gratis", "llamenos", "llámenos"}
)
_MIN_HTML_STOPWORD_MATCHES = 3


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _name_signals_spanish(name: str) -> bool:
    # Un apellido hispano con tilde ("Núñez", "López") es señal fuerte por sí
    # solo, incluso si no aparece en `_SPANISH_NAME_TOKENS`.
    if _ACCENTED_CHAR_RE.search(name):
        return True

    tokens = re.findall(r"[a-z]+", _strip_accents(name).lower())
    matches = sum(1 for token in tokens if token in _SPANISH_NAME_TOKENS)
    return matches >= _MIN_NAME_TOKEN_MATCHES


def _html_signals_spanish(html: str) -> bool:
    if _SPANISH_HTML_LANG_RE.search(html):
        return True

    lowered = _strip_accents(html).lower()
    matches = sum(1 for word in _SPANISH_HTML_STOPWORDS if _strip_accents(word) in lowered)
    return matches >= _MIN_HTML_STOPWORD_MATCHES


def detect_language(
    prospect: Prospect, *, html: str | None = None, default: Language = Language.EN
) -> Language:
    """Idioma más probable del prospecto -- `default` salvo evidencia razonable
    de español.

    Señales, de la más barata a la más cara: primero el nombre del negocio
    (siempre disponible, sin red); si no hay señal ahí y se tiene el HTML del
    sitio a mano, su atributo `lang` o la densidad de stopwords en español.
    Nunca descarga nada por su cuenta -- `html` es responsabilidad de quien
    llama, igual que en `score.score_prospect`.
    """
    if _name_signals_spanish(prospect.name):
        return Language.ES
    if html is not None and _html_signals_spanish(html):
        return Language.ES
    return default
