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

from gtm.factory import artifacts, config
from gtm.factory.logs import get_logger
from gtm.factory.net import (
    DEFAULT_CONCURRENCY,
    async_client,
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
    viewport = audits.get("viewport", {}).get("score")

    return PainScore(
        place_id="",  # lo completa score_prospect
        performance=performance,
        seo=_category_score(lighthouse, "seo"),
        accessibility=_category_score(lighthouse, "accessibility"),
        mobile_friendly=None if viewport is None else bool(viewport),
        has_web_presence=True,
        reachable=True,
    )


async def score_prospect(
    client: httpx.AsyncClient, prospect: Prospect, api_key: str | None = None
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

    return PainScore(
        place_id=prospect.place_id,
        performance=measured.performance,
        seo=measured.seo,
        accessibility=measured.accessibility,
        mobile_friendly=measured.mobile_friendly,
        notes=tuple(notes),
    )


async def score_all(
    prospects: list[Prospect],
    api_key: str | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    *,
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
                score = await score_prospect(client, prospect, api_key)
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
    scores = asyncio.run(score_all(prospects, api_key, args.concurrency))

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
