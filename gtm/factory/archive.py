"""Última modificación real de un sitio, vía la Wayback Machine.

La señal más fuerte y más barata para responder "¿esta web es vieja?": la CDX
API del Internet Archive es pública, gratuita, sin autenticación, y con
`collapse=digest` devuelve una fila por cada vez que el CONTENIDO realmente
cambió (no una por captura). Si la última fila es de 2016, el sitio lleva diez
años sin que nadie lo toque — un hecho con fecha, público y verificable por el
propio dueño, no una opinión estética sobre el diseño.

El servicio es lento e inestable, y eso nunca puede tumbar una corrida: ante
cualquier fallo, `last_meaningful_change` devuelve None y `score.py` sigue sin
esa señal, igual que ya hace cuando PageSpeed no responde.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from gtm.factory.logs import get_logger
from gtm.factory.net import request_json_async

_logger = get_logger(__name__)

_CDX_ENDPOINT = "http://web.archive.org/cdx/search/cdx"
_TIMEOUT_SECONDS = 20.0

_MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip


def parse_cdx_rows(rows: list[list[str]]) -> date | None:
    """Extrae la fecha del cambio de contenido más reciente.

    La primera fila es el header (`["timestamp", "digest"]`), no una captura.
    No asume que las filas ya vienen ordenadas, e ignora timestamps corruptos
    en vez de romper la corrida por un dato externo mal formado.
    """
    dates: list[date] = []
    for row in rows[1:]:
        if not row or not row[0]:
            continue
        timestamp = row[0]
        try:
            dates.append(date(int(timestamp[0:4]), int(timestamp[4:6]), int(timestamp[6:8])))
        except (ValueError, IndexError):
            continue
    return max(dates) if dates else None


def format_month_year(value: date, language: str) -> str:
    if language == "es":
        return f"{_MESES_ES[value.month - 1]} de {value.year}"
    return f"{value.strftime('%B')} {value.year}"


_cache: dict[str, date | None] = {}


async def last_meaningful_change(
    client: httpx.AsyncClient, host: str, *, timeout: float = _TIMEOUT_SECONDS
) -> date | None:
    """Fecha del último cambio de contenido real para `host`, o None.

    Cacheado por host normalizado: dentro de la misma corrida no tiene sentido
    volver a pedirle al Archive el mismo dato dos veces. `functools.lru_cache`
    no sirve acá porque cachearía la corrutina sin awaitear, no el resultado.
    """
    if host in _cache:
        return _cache[host]

    params: dict[str, Any] = {
        "url": f"{host}/*",
        "output": "json",
        "fl": "timestamp,digest",
        "collapse": "digest",
        "filter": "statuscode:200",
        "limit": "-200",
    }

    try:
        rows = await request_json_async(
            client, "GET", _CDX_ENDPOINT, params=params, max_retries=2
        )
    except Exception as exc:  # noqa: BLE001 - el Archive nunca puede tumbar la corrida
        _logger.warning(
            "Wayback CDX no respondió",
            extra={"event": "archive_failed", "host": host, "error": str(exc)},
        )
        _cache[host] = None
        return None

    result = parse_cdx_rows(rows) if isinstance(rows, list) else None
    _cache[host] = result
    return result


last_meaningful_change.cache_clear = _cache.clear  # type: ignore[attr-defined]
