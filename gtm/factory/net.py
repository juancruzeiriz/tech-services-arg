"""Cliente HTTP con timeouts y reintentos con backoff exponencial.

Regla del proyecto: ninguna llamada externa sin timeout, y backoff exponencial con
base=2 y tope de 32s. Toda API externa del pipeline pasa por acá.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator, Awaitable, Sequence
from contextlib import asynccontextmanager
from typing import Any, TypeVar

import httpx

from gtm.factory.logs import get_logger

_logger = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RETRIES = 4
BACKOFF_BASE = 2.0
BACKOFF_MAX_SECONDS = 32.0

# Solo reintentamos lo que puede resolverse solo. Un 400/401/403 es un bug de
# configuración: reintentarlo quema cuota y esconde el error real.
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

# TypeVar en vez de la sintaxis PEP 695: mypy la rechaza cuando corre sobre 3.11,
# y esto tiene que verificar igual en local que en CI.
_T = TypeVar("_T")

# Identificarse es lo correcto y además evita que nos tomen por un bot anónimo.
USER_AGENT = "gtm-factory/1.0 (+contact-channel-discovery)"


def _backoff_delay(attempt: int) -> float:
    """Delay del intento `attempt` (0-indexed) con jitter completo.

    El jitter evita que N prospectos procesados en paralelo reintenten en fase y
    vuelvan a tumbar el endpoint que se está recuperando.
    """
    ceiling = min(BACKOFF_BASE**attempt, BACKOFF_MAX_SECONDS)
    return random.uniform(0, ceiling)  # noqa: S311 - jitter, no criptografía


def request_json(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = MAX_RETRIES,
) -> dict[str, Any]:
    """Ejecuta una request y devuelve el JSON, reintentando fallos transitorios.

    Raises:
        httpx.HTTPStatusError: si el status no es reintentable, o si se agotaron
            los reintentos.
        httpx.TransportError: si la conexión falla tras agotar los reintentos.
    """
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                response = client.request(
                    method, url, params=params, json=json_body, headers=headers
                )

            if response.status_code in _RETRYABLE_STATUS:
                response.raise_for_status()

            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            status = (
                exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            )
            # Un error no reintentable aborta de inmediato: no gastamos 4 intentos
            # en un 401.
            if status is not None and status not in _RETRYABLE_STATUS:
                raise

            last_error = exc
            if attempt == max_retries - 1:
                break

            delay = _backoff_delay(attempt)
            _logger.warning(
                "reintentando request externa",
                extra={
                    "event": "http_retry",
                    "url": url.split("?")[0],
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "status": status,
                    "delay_seconds": round(delay, 2),
                },
            )
            time.sleep(delay)

    assert last_error is not None  # invariante: solo salimos del loop con un error
    _logger.error(
        "request externa agotó reintentos",
        extra={"event": "http_exhausted", "url": url.split("?")[0], "attempts": max_retries},
    )
    raise last_error


# ─── Variantes async ─────────────────────────────────────────────────────────
#
# Las etapas que hacen N llamadas independientes (score, contact) son
# embarazosamente paralelas y en serie tardan minutos por espera de red, no por
# cómputo. El cliente se comparte en todo el lote a propósito: reusar conexiones
# es una parte grande de la mejora, no solo la concurrencia.

DEFAULT_CONCURRENCY = 8


@asynccontextmanager
async def async_client(
    timeout: float = DEFAULT_TIMEOUT_SECONDS, concurrency: int = DEFAULT_CONCURRENCY
) -> AsyncIterator[httpx.AsyncClient]:
    """Cliente async con pool dimensionado a la concurrencia real del lote."""
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, limits=limits, headers={"User-Agent": USER_AGENT}
    ) as client:
        yield client


async def gather_limited(  # noqa: UP047 - ver nota sobre PEP 695 arriba
    coros: Sequence[Awaitable[_T]], limit: int = DEFAULT_CONCURRENCY
) -> list[_T]:
    """Ejecuta las corrutinas con un techo de concurrencia, preservando el orden.

    El semáforo no es opcional: soltar 50 requests de golpe contra PageSpeed
    garantiza 429s, y el backoff posterior termina siendo más lento que haber ido
    de a poco desde el principio.
    """
    semaphore = asyncio.Semaphore(limit)

    async def _run(coro: Awaitable[_T]) -> _T:
        async with semaphore:
            return await coro

    return await asyncio.gather(*(_run(coro) for coro in coros))


async def request_json_async(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    max_retries: int = MAX_RETRIES,
) -> dict[str, Any]:
    """Equivalente async de `request_json`, con la misma política de reintentos."""
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            response = await client.request(
                method, url, params=params, json=json_body, headers=headers
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            if status is not None and status not in _RETRYABLE_STATUS:
                raise

            last_error = exc
            if attempt == max_retries - 1:
                break

            delay = _backoff_delay(attempt)
            _logger.warning(
                "reintentando request externa",
                extra={
                    "event": "http_retry",
                    "url": url.split("?")[0],
                    "attempt": attempt + 1,
                    "status": status,
                    "delay_seconds": round(delay, 2),
                },
            )
            # asyncio.sleep, no time.sleep: bloquear el event loop acá anularía
            # toda la concurrencia justo cuando más falta hace.
            await asyncio.sleep(delay)

    assert last_error is not None
    raise last_error


async def probe_url_async(client: httpx.AsyncClient, url: str) -> bool:
    """Como `probe_url`, sin reintentos: "no responde" es el dato que buscamos."""
    try:
        response = await client.get(url)
        return response.status_code < 500
    except httpx.HTTPError:
        return False


async def fetch_text_async(client: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
    """Como `fetch_text`, para lotes."""
    try:
        response = await client.get(url)
        if response.status_code >= 400:
            return None
        if "html" not in response.headers.get("content-type", "").lower():
            return None
        return str(response.url), response.text
    except httpx.HTTPError:
        return None


def fetch_text(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> tuple[str, str] | None:
    """Descarga una página y devuelve (url_final, html), o None si no se pudo.

    Devuelve la URL final para poder resolver links relativos después de un redirect.
    Sin reintentos: el sitio de un prospecto que no carga es un dato, no un fallo.
    """
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": USER_AGENT})
        if response.status_code >= 400:
            return None
        # Un PDF o una imagen en la home no nos sirve para buscar el formulario.
        if "html" not in response.headers.get("content-type", "").lower():
            return None
        return str(response.url), response.text
    except httpx.HTTPError:
        return None


def probe_url(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> bool:
    """Devuelve True si la URL responde algo que no sea un error de servidor.

    Sin reintentos a propósito: acá "no responde" no es un fallo del pipeline, es
    justamente el dato que queremos medir (y el mejor ángulo de venta que existe).
    """
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
        return response.status_code < 500
    except httpx.HTTPError:
        return False
