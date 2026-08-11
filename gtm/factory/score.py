"""Etapa 2: medir cuánto le duele al prospecto su presencia web actual.

Usa la PageSpeed Insights API (Lighthouse hosteado por Google) en vez de correr
Lighthouse local: sin dependencia de Node, sin mantener una instalación de Chrome, y
el número sale del mismo motor que el prospecto puede verificar por su cuenta —lo
cual importa, porque el email de prospección cita ese número.

Es async porque es la etapa lenta del pipeline: Lighthouse tarda 30-60s por sitio y
en serie 50 prospectos son 25-50 minutos de espera pura de red. Con un techo de
concurrencia baja a unos 3 minutos.

Uso:
    python -m gtm.factory.score --input gtm/build/data/prospects.json
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable
from typing import Any

import httpx

from gtm.factory import artifacts, config, forensics
from gtm.factory.archive import last_meaningful_change
from gtm.factory.crux import CruxMetrics, classify_inp, classify_lcp, fetch_crux_metrics
from gtm.factory.findings import FINDINGS, Finding
from gtm.factory.logs import get_logger
from gtm.factory.net import (
    DEFAULT_CONCURRENCY,
    async_client,
    fetch_text_async,
    gather_limited,
    probe_url_async,
    request_json_async,
)
from gtm.factory.types import PainScore, Prospect, ScoringError, WebPresence

_logger = get_logger(__name__)

_PAGESPEED_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# Lighthouse tarda; este endpoint es lento por diseño. Un timeout corto acá produce
# falsos "sitio caído" que arruinarían el ángulo de venta.
_PAGESPEED_TIMEOUT = 60.0

# Más conservador que el default: sin API key, PageSpeed rate-limitea rápido y los
# 429 resultantes terminan siendo más lentos que haber ido de a cinco desde el inicio.
_DEFAULT_SCORE_CONCURRENCY = 5


def _category_score(lighthouse: dict[str, Any], category: str) -> int | None:
    """Extrae un score de categoría de Lighthouse y lo lleva a escala 0-100."""
    raw = (lighthouse.get("categories", {}).get(category) or {}).get("score")
    if raw is None:
        return None
    return round(float(raw) * 100)


def _audit_failed(lighthouse: dict[str, Any], audit_id: str) -> bool:
    """True si Lighthouse corrió esta auditoría puntual y dio mal (score < 1).

    `target-size` es una señal que la propia forensics.py NO puede medir
    desde el HTML crudo (depende del layout ya renderizado) — por eso vive
    acá y no ahí, aunque termina como el mismo tipo de Finding con evidencia
    citable que las de forensics.py.
    """
    raw = lighthouse.get("audits", {}).get(audit_id, {}).get("score")
    return raw is not None and float(raw) < 1.0


async def score_website(
    client: httpx.AsyncClient, url: str, api_key: str | None = None
) -> PainScore | None:
    """Corre PageSpeed sobre una URL. Devuelve None si la API no pudo analizarla."""
    params: dict[str, Any] = {
        "url": url,
        "strategy": "mobile",  # home services es tráfico móvil casi puro
        "category": ["performance", "seo", "accessibility"],
    }
    if api_key:
        params["key"] = api_key

    try:
        payload = await request_json_async(
            client,
            "GET",
            _PAGESPEED_ENDPOINT,
            params=params,
            # PageSpeed rate-limitea con agresividad; conviene rendirse rápido y
            # seguir con el próximo prospecto en vez de bloquear la corrida.
            max_retries=2,
        )
    except Exception as exc:  # noqa: BLE001 - degradamos, no abortamos la corrida
        _logger.warning(
            "PageSpeed no pudo analizar el sitio",
            extra={"event": "pagespeed_failed", "url": url, "error": str(exc)},
        )
        return None

    lighthouse = payload.get("lighthouseResult", {})
    if not lighthouse:
        return None

    performance = _category_score(lighthouse, "performance")
    audits = lighthouse.get("audits", {})
    # "viewport" y "tap-targets" son los IDs que Lighthouse usaba hasta 2025;
    # PageSpeed Insights los renombró a "meta-viewport" y "target-size" (
    # confirmado en vivo el 2026-08-11 contra la API real: los IDs viejos ya
    # no aparecen en la respuesta, así que `_audit_failed`/este `.get()` con
    # el nombre viejo devolvía siempre "sin señal" y `mobile` quedaba en 0
    # para absolutamente todos los sitios, sin que ningún test lo detectara
    # porque todos mockean `score_website` entero — ver test_score.py).
    viewport = audits.get("meta-viewport", {}).get("score")

    lab_findings: list[Finding] = []
    if _audit_failed(lighthouse, "target-size"):
        lab_findings.append(
            Finding(
                code="tap_targets",
                # El nombre del audit de Lighthouse, no una descripción del
                # problema en español: ya lo dice el template de
                # findings.py, y esta evidencia era antes una traducción
                # hardcodeada que se colaba tal cual dentro de emails en
                # inglés (encontrado leyendo emails reales en el Día 7).
                evidence="Lighthouse target-size",
                weight=FINDINGS["tap_targets"].weight,
            )
        )
    # "font-size" (texto ilegible en celular) no tiene reemplazo: Lighthouse
    # lo sacó de la API sin dejar un ID sucesor (confirmado el 2026-08-11
    # contra la lista completa de audits de una respuesta real). El Finding
    # `tiny_font` sigue existiendo en findings.py porque el concepto de venta
    # sigue siendo válido, pero hoy no hay forma de detectarlo automático —
    # si Google reintroduce la señal bajo otro ID, reactivar acá.

    return PainScore(
        place_id="",  # lo completa score_prospect
        performance=performance,
        seo=_category_score(lighthouse, "seo"),
        accessibility=_category_score(lighthouse, "accessibility"),
        mobile_friendly=None if viewport is None else bool(viewport),
        has_web_presence=True,
        reachable=True,
        findings=tuple(lab_findings),
    )


async def _fetch_crux_safe(
    client: httpx.AsyncClient, url: str, crux_api_key: str | None
) -> CruxMetrics | None:
    """Como `crux.fetch_crux_metrics`, pero sin dejar pasar nada más que un
    404 (que esa función ya resuelve sola). CrUX puede estar caído, dar 500 o
    agotar reintentos, y nada de eso puede tumbar la corrida — exactamente la
    misma regla que ya aplica `archive.last_meaningful_change` para el
    Wayback Machine."""
    if not crux_api_key:
        return None
    try:
        return await fetch_crux_metrics(client, url, api_key=crux_api_key)
    except Exception as exc:  # noqa: BLE001 - CrUX nunca puede tumbar la corrida
        _logger.warning(
            "CrUX no respondió", extra={"event": "crux_failed", "url": url, "error": str(exc)}
        )
        return None


async def score_prospect(
    client: httpx.AsyncClient,
    prospect: Prospect,
    api_key: str | None = None,
    *,
    crux_api_key: str | None = None,
) -> PainScore:
    """Puntúa un prospecto, degradando a señales estructurales si no hay sitio medible."""
    presence = prospect.web_presence

    if presence is WebPresence.NONE:
        return PainScore(
            place_id=prospect.place_id,
            has_web_presence=False,
            notes=("Sin sitio web: el negocio es invisible fuera de Google Maps.",),
        )

    if presence is WebPresence.SOCIAL_ONLY:
        # Un perfil de Facebook no es un sitio: no rankea, no convierte y no es suyo.
        return PainScore(
            place_id=prospect.place_id,
            has_web_presence=False,
            notes=(
                f"Solo presencia en redes ({prospect.website}): "
                "no controla su canal ni aparece en búsquedas de servicio.",
            ),
        )

    assert prospect.website is not None  # garantizado por HAS_SITE

    if not await probe_url_async(client, prospect.website):
        return PainScore(
            place_id=prospect.place_id,
            reachable=False,
            notes=(f"El sitio {prospect.website} no responde.",),
        )

    measured = await score_website(client, prospect.website, api_key)
    if measured is None:
        raise ScoringError(f"No se pudo puntuar {prospect.website} para {prospect.name!r}")

    notes: list[str] = []
    if measured.performance is not None and measured.performance < 50:
        notes.append(
            f"Rendimiento móvil {measured.performance}/100: el sitio tarda tanto "
            "que una parte del tráfico se va antes de verlo."
        )
    if measured.seo is not None and measured.seo < 70:
        notes.append(f"SEO {measured.seo}/100: pierde búsquedas locales.")

    # Tres señales independientes entre sí y de PageSpeed, en paralelo: ninguna
    # puede alargar la etapa en serie, y las tres funciones ya se tragan sus
    # propios errores (ver sus docstrings), así que ninguna puede tumbarla.
    html_result, crux_metrics, last_changed = await asyncio.gather(
        fetch_text_async(client, prospect.website),
        _fetch_crux_safe(client, prospect.website, crux_api_key),
        last_meaningful_change(client, _host_of(prospect.website)),
    )

    findings: list[Finding] = list(measured.findings)  # tap_targets/tiny_font, si Lighthouse los vio

    if html_result is not None:
        _, html = html_result
        findings.extend(forensics.analyse_html(html, prospect.website))

    if crux_metrics is not None:
        lcp_ms = crux_metrics.lcp_ms
        if lcp_ms is not None and classify_lcp(lcp_ms) == "poor":
            findings.append(
                Finding(
                    code="crux_lcp_poor",
                    evidence=f"{lcp_ms / 1000:.1f}s",
                    weight=FINDINGS["crux_lcp_poor"].weight,
                )
            )
        inp_ms = crux_metrics.inp_ms
        if inp_ms is not None and classify_inp(inp_ms) == "poor":
            findings.append(
                Finding(
                    code="crux_inp_poor",
                    evidence=f"{inp_ms}ms",
                    weight=FINDINGS["crux_inp_poor"].weight,
                )
            )

    if last_changed is not None:
        findings.append(
            Finding(
                code="stale_since",
                evidence=last_changed.isoformat(),
                weight=FINDINGS["stale_since"].weight,
            )
        )

    return PainScore(
        place_id=prospect.place_id,
        performance=measured.performance,
        seo=measured.seo,
        accessibility=measured.accessibility,
        mobile_friendly=measured.mobile_friendly,
        notes=tuple(notes),
        findings=tuple(findings),
        crux_lcp_ms=crux_metrics.lcp_ms if crux_metrics else None,
        crux_inp_ms=crux_metrics.inp_ms if crux_metrics else None,
        crux_cls=crux_metrics.cls if crux_metrics else None,
        has_field_data=crux_metrics is not None,
        last_changed=last_changed,
    )


def _host_of(url: str) -> str:
    return httpx.URL(url).host


async def score_all(
    prospects: list[Prospect],
    api_key: str | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    *,
    crux_api_key: str | None = None,
    on_item: Callable[[str], None] | None = None,
) -> list[PainScore]:
    """Puntúa una lista de prospectos en paralelo.

    Un fallo individual no aborta la corrida: `gather_limited` propagaría la primera
    excepción y perderíamos los 49 prospectos que sí se puntuaron, así que cada
    tarea captura su propio error y devuelve None.

    `on_item`, si se pasa, se llama una vez por prospecto terminado (con su
    place_id) — es lo que le permite a la UI mostrar progreso en vivo sin que
    `score_all` sepa nada de SSE ni de la UI. Sincrónico a propósito: las tres
    formas de consumirlo (CLI imprimiendo, un callback que hace
    `queue.put_nowait`, una barra de progreso) no necesitan `await`.
    """
    async with async_client(timeout=_PAGESPEED_TIMEOUT, concurrency=concurrency) as client:

        async def _one(prospect: Prospect) -> PainScore | None:
            try:
                score = await score_prospect(client, prospect, api_key, crux_api_key=crux_api_key)
            except ScoringError as exc:
                _logger.warning(
                    "prospecto sin puntuar",
                    extra={
                        "event": "score_skipped",
                        "place_id": prospect.place_id,
                        "error": str(exc),
                    },
                )
                if on_item is not None:
                    on_item(prospect.place_id)
                return None
            _logger.info(
                "prospecto puntuado",
                extra={
                    "event": "scored",
                    "place_id": prospect.place_id,
                    # No usar "name": choca con el atributo reservado de LogRecord.
                    "business": prospect.name,
                    "pain_score": score.score,
                    "qualified": score.is_qualified,
                },
            )
            if on_item is not None:
                on_item(prospect.place_id)
            return score

        results = await gather_limited([_one(p) for p in prospects], concurrency)

    scores = [score for score in results if score is not None]
    scores.sort(key=lambda s: -s.score)
    return scores


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Puntúa el dolor digital de los prospectos")
    parser.add_argument(
        "--input", default=None, help="JSON de discover (default: gtm/build/data/prospects.json)"
    )
    parser.add_argument(
        "--output", default=None, help="default: gtm/build/data/scores.json"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=_DEFAULT_SCORE_CONCURRENCY,
        help=f"requests simultáneas a PageSpeed (default: {_DEFAULT_SCORE_CONCURRENCY})",
    )
    args = parser.parse_args(argv)

    config.ensure_dirs()
    input_path = args.input or str(config.DATA_DIR / "prospects.json")
    output_path = args.output or str(config.DATA_DIR / "scores.json")

    prospects = artifacts.read_prospects(input_path)

    api_key = config.optional_env("PAGESPEED_API_KEY") or None
    # Mismo proyecto de Google Cloud habilita las dos APIs: si no hay una key
    # dedicada para CrUX, la de PageSpeed también sirve.
    crux_api_key = config.optional_env("CRUX_API_KEY") or api_key
    scores = asyncio.run(
        score_all(prospects, api_key, args.concurrency, crux_api_key=crux_api_key)
    )

    artifacts.write_scores(output_path, scores)

    by_id = {p.place_id: p for p in prospects}
    qualified = [s for s in scores if s.is_qualified]
    print(f"{len(qualified)}/{len(scores)} prospectos calificados -> {output_path}")
    for score in scores:
        name = by_id[score.place_id].name if score.place_id in by_id else score.place_id
        mark = "✓" if score.is_qualified else " "
        print(f"  {mark} {score.score:>3}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
