"""Datos de campo reales de la Chrome UX Report API.

PageSpeed/Lighthouse mide en laboratorio: un Moto G simulado en una red 4G
simulada, una sola corrida. CrUX es lo que le pasó de verdad a los visitantes
reales del sitio en los últimos 28 días — el mismo dataset con el que Google
decide sus propios Core Web Vitals en el ranking. "El 75% de tus visitantes
móviles espera 6,2 segundos" es un hecho verificable, no una simulación.

Uso opcional a propósito: sitios con poco tráfico no tienen datos de campo (la
API responde 404), y eso no es un error de la corrida — es la señal de que hay
que degradar al dato de laboratorio de PageSpeed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx

from gtm.factory.net import request_json_async

_CRUX_ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"

# Umbrales oficiales de Core Web Vitals (web.dev/articles/defining-core-web-vitals-thresholds).
_LCP_GOOD_MS = 2500
_LCP_POOR_MS = 4000
_INP_GOOD_MS = 200
_INP_POOR_MS = 500
_CLS_GOOD = 0.1
_CLS_POOR = 0.25

Rating = Literal["good", "needs-improvement", "poor"]


@dataclass(frozen=True, slots=True)
class CruxMetrics:
    lcp_ms: int | None = None
    inp_ms: int | None = None
    cls: float | None = None


def _p75(metrics: dict[str, Any], key: str) -> float | None:
    raw = metrics.get(key, {}).get("percentiles", {}).get("p75")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def parse_crux_payload(payload: dict[str, Any]) -> CruxMetrics:
    metrics = payload.get("record", {}).get("metrics", {})
    lcp = _p75(metrics, "largest_contentful_paint")
    inp = _p75(metrics, "interaction_to_next_paint")
    cls = _p75(metrics, "cumulative_layout_shift")
    return CruxMetrics(
        lcp_ms=None if lcp is None else round(lcp),
        inp_ms=None if inp is None else round(inp),
        cls=cls,
    )


def _classify(value: float | None, good: float, poor: float) -> Rating | None:
    if value is None:
        return None
    if value <= good:
        return "good"
    if value > poor:
        return "poor"
    return "needs-improvement"


def classify_lcp(lcp_ms: float | None) -> Rating | None:
    return _classify(lcp_ms, _LCP_GOOD_MS, _LCP_POOR_MS)


def classify_inp(inp_ms: float | None) -> Rating | None:
    return _classify(inp_ms, _INP_GOOD_MS, _INP_POOR_MS)


def classify_cls(cls: float | None) -> Rating | None:
    return _classify(cls, _CLS_GOOD, _CLS_POOR)


async def fetch_crux_metrics(
    client: httpx.AsyncClient,
    url: str,
    *,
    api_key: str,
) -> CruxMetrics | None:
    """Pide datos de campo para `url`; si la página exacta no tiene tráfico
    suficiente, reintenta con el origen completo antes de rendirse.

    Devuelve None si ni la URL ni el origen tienen datos (404 en ambos) — eso
    significa "sitio chico, sin señal de campo", no un fallo de la corrida.
    """
    for target in ({"url": url}, {"origin": _origin_of(url)}):
        try:
            payload = await request_json_async(
                client,
                "POST",
                _CRUX_ENDPOINT,
                params={"key": api_key},
                json_body={**target, "formFactor": "PHONE"},
                max_retries=2,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                continue
            raise
        return parse_crux_payload(payload)

    return None


def _origin_of(url: str) -> str:
    parsed = httpx.URL(url)
    return f"{parsed.scheme}://{parsed.host}"
