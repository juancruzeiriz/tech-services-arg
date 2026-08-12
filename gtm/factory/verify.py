"""Capa 2 de verificación de ausencia digital.

`classify_web_presence` (`gtm.factory.types`) confirma ausencia de sitio contra una
sola fuente: el campo `websiteUri` que el negocio cargó en su ficha de Google Maps.
Un negocio puede tener dominio propio y sencillamente no haberlo vinculado ahí --
y `score.py` le asignaría el dolor máximo (100) y afirmaría, en la primera línea
del mensaje, "no tenés sitio web": un hecho falso y verificable por el propio
prospecto en el peor momento posible, la primera llamada.

Dos sub-capas, en orden de costo:

- **Sub-capa A (gratis, siempre corre).** Deriva dominios candidatos del nombre del
  negocio (`candidate_domains`) y prueba cada uno con las mismas funciones de
  `net.py` que ya usa el resto del pipeline. Un dominio que responde no alcanza --
  se exige que el teléfono o el nombre del prospecto aparezcan en su HTML
  (`_corroborates`), porque un dominio parqueado o de otro negocio no es prueba de
  nada.
- **Sub-capa B (opcional, solo con `GTM_SEARCH_API_KEY`/`GTM_SEARCH_CX`).** Una
  consulta a la Google Programmable Search API (Custom Search JSON API) por el
  nombre, la ciudad y el oficio del prospecto. Los resultados se clasifican con el
  mismo criterio de `types.classify_web_presence`: si el primer resultado no-Google
  no es un directorio de terceros, es dominio propio.

Deliberadamente NO se raspa el HTML de una página de resultados de Google: viola
sus términos de servicio y es evasión de detección de bots -- la misma razón por la
que `docs/CHANNELS.md` ya prohíbe automatizar el envío de formularios protegidos
por CAPTCHA. La única forma de consultar resultados de búsqueda es la API oficial.

Como `crux.py` y `archive.py`, este módulo nunca puede tumbar la corrida: cualquier
fallo de red degrada a `DigitalTrace.UNVERIFIED`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from gtm.catalog import city_of
from gtm.factory.logs import get_logger
from gtm.factory.net import fetch_text_async, probe_url_async, request_json_async
from gtm.factory.types import DigitalTrace, Prospect, WebPresence, classify_web_presence

_logger = get_logger(__name__)

_SEARCH_ENDPOINT = "https://www.googleapis.com/customsearch/v1"

# Propiedades de Google que pueden aparecer en los resultados (la propia ficha de
# Maps, por ejemplo) -- no son ni un dominio propio ni un directorio de terceros,
# así que no cuentan para ninguno de los dos.
_IGNORED_SEARCH_HOSTS: tuple[str, ...] = ("google.com",)

# Sufijos genéricos de razón social: el dominio real casi nunca los incluye
# ("Legacy Tree Company" -> legacytree.com, no legacytreecompany.com solamente).
_GENERIC_TRAILING_WORDS = frozenset(
    {
        "llc", "inc", "incorporated", "co", "corp", "corporation",
        "ltd", "limited", "company", "services", "group", "enterprises",
    }
)  # fmt: skip

# Palabras cortas o genéricas que no sirven para corroborar identidad por nombre:
# "Tree Service Co" corroboraría con cualquier sitio de poda de árboles, no con
# este negocio en particular.
_NAME_STOPWORDS = _GENERIC_TRAILING_WORDS | frozenset({"the", "of", "and", "a", "an"})

_MAX_CANDIDATE_DOMAINS = 6
_CANDIDATE_TLDS = (".com", ".net")

# Mínimo de dígitos para intentar corroborar por teléfono: menos que esto (un
# 911 suelto en el HTML, por ejemplo) da falsos positivos.
_MIN_PHONE_DIGITS = 7

# Cuántos tokens del nombre tienen que aparecer en el HTML para corroborar por
# nombre. 2 evita que una sola palabra común ("tree", "services") baste.
_MIN_NAME_TOKEN_MATCHES = 2


@dataclass(frozen=True, slots=True)
class VerifyResult:
    kind: DigitalTrace
    url: str | None = None
    """El dominio propio corroborado, solo si `kind` es `OWN_DOMAIN`."""


def _slug_tokens(name: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", name.lower())


def candidate_domains(prospect: Prospect) -> list[str]:
    """Dominios `.com`/`.net` plausibles derivados del nombre del negocio.

    Dos variantes: el nombre completo unido, y el mismo sin los sufijos
    genéricos de razón social del final ("Company", "LLC", "Services"...).
    Ninguna prueba nada por sí sola -- `verify_absence` exige corroboración
    antes de declarar cualquiera de estas `OWN_DOMAIN`.
    """
    tokens = _slug_tokens(prospect.name)
    if not tokens:
        return []

    core = list(tokens)
    while len(core) > 1 and core[-1] in _GENERIC_TRAILING_WORDS:
        core.pop()

    slugs: list[str] = []
    for candidate_tokens in (tokens, core):
        slug = "".join(candidate_tokens)
        if slug and slug not in slugs:
            slugs.append(slug)

    domains = [f"{slug}{tld}" for slug in slugs for tld in _CANDIDATE_TLDS]
    return domains[:_MAX_CANDIDATE_DOMAINS]


def _contains_phone(html: str, phone: str) -> bool:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < _MIN_PHONE_DIGITS:
        return False
    # Tolera separadores típicos de formato ("(505) 555-0148") entre dígitos,
    # acotado para no exponerse a backtracking patológico en HTML grande.
    pattern = re.compile(r"[\s\-.()]{0,3}".join(re.escape(d) for d in digits))
    return pattern.search(html) is not None


def _contains_name(html: str, name: str) -> bool:
    tokens = [t for t in _slug_tokens(name) if len(t) >= 3 and t not in _NAME_STOPWORDS]
    if not tokens:
        return False
    haystack = html.lower()
    matches = sum(1 for token in tokens if token in haystack)
    required = min(_MIN_NAME_TOKEN_MATCHES, len(tokens))
    return matches >= required


def _corroborates(html: str, prospect: Prospect) -> bool:
    """¿Este HTML es de verdad el sitio de `prospect`, no un dominio
    parqueado o de otro negocio que casualmente respondió?"""
    if prospect.phone and _contains_phone(html, prospect.phone):
        return True
    return _contains_name(html, prospect.name)


async def _try_candidate_domain(
    client: httpx.AsyncClient, prospect: Prospect, domain: str
) -> VerifyResult | None:
    url = f"https://{domain}"
    try:
        if not await probe_url_async(client, url):
            return None
        fetched = await fetch_text_async(client, url)
    except Exception:  # noqa: BLE001 - un candidato malo no puede tumbar la corrida
        return None

    if fetched is None:
        return None

    _, html = fetched
    if _corroborates(html, prospect):
        return VerifyResult(DigitalTrace.OWN_DOMAIN, url=url)
    return None


def _is_ignored_search_host(host: str) -> bool:
    return any(host == ignored or host.endswith(f".{ignored}") for ignored in _IGNORED_SEARCH_HOSTS)


def _is_third_party_host(host: str) -> bool:
    """Reusa el mismo criterio que `classify_web_presence`: si un dominio se
    clasificaría como `SOCIAL_ONLY` viniendo de Maps, es un directorio de
    terceros viniendo de la búsqueda también -- un solo lugar donde vive la
    lista de directorios (`types._THIRD_PARTY_HOSTS`)."""
    return classify_web_presence(f"https://{host}") is WebPresence.SOCIAL_ONLY


async def _search(
    client: httpx.AsyncClient, prospect: Prospect, api_key: str, cx: str
) -> list[tuple[str, str]]:
    """Consulta la Custom Search JSON API por nombre + ciudad + oficio.

    Devuelve pares (host, link) en el orden que devolvió la API -- el
    llamador decide qué hacer con cada uno. Puede lanzar: `verify_absence`
    decide cómo degradar.
    """
    city = city_of(prospect.metro)
    query = f'"{prospect.name}" {city} {prospect.vertical}'
    payload = await request_json_async(
        client,
        "GET",
        _SEARCH_ENDPOINT,
        params={"key": api_key, "cx": cx, "q": query, "num": 5},
        max_retries=2,
    )

    results: list[tuple[str, str]] = []
    for item in payload.get("items", []):
        link = item.get("link")
        if not link:
            continue
        host = urlparse(link).netloc.lower().removeprefix("www.")
        if host:
            results.append((host, link))
    return results


def _classify_search_results(results: list[tuple[str, str]]) -> VerifyResult:
    saw_directory = False
    for host, link in results:
        if _is_ignored_search_host(host):
            continue
        if _is_third_party_host(host):
            saw_directory = True
            continue
        return VerifyResult(DigitalTrace.OWN_DOMAIN, url=link)

    if saw_directory:
        return VerifyResult(DigitalTrace.DIRECTORY_ONLY)
    return VerifyResult(DigitalTrace.NO_TRACE)


async def verify_absence(
    client: httpx.AsyncClient,
    prospect: Prospect,
    *,
    search_api_key: str | None = None,
    search_cx: str | None = None,
) -> VerifyResult:
    """Confirma si `prospect` -- reportado sin sitio propio por Google Maps --
    de verdad no tiene presencia web propia.

    Nunca lanza: cualquier fallo de red o falta de configuración degrada a
    `DigitalTrace.UNVERIFIED`, igual que `crux.fetch_crux_metrics` y
    `archive.last_meaningful_change` degradan ante un fallo de su fuente.
    """
    for domain in candidate_domains(prospect):
        found = await _try_candidate_domain(client, prospect, domain)
        if found is not None:
            return found

    if not search_api_key or not search_cx:
        return VerifyResult(DigitalTrace.UNVERIFIED)

    try:
        results = await _search(client, prospect, search_api_key, search_cx)
    except Exception as exc:  # noqa: BLE001 - la búsqueda nunca puede tumbar la corrida
        _logger.warning(
            "búsqueda general no respondió",
            extra={"event": "verify_search_failed", "place_id": prospect.place_id, "error": str(exc)},
        )
        return VerifyResult(DigitalTrace.UNVERIFIED)

    return _classify_search_results(results)
