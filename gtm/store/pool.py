"""Pool de conexiones async a Postgres, para la UI (FastAPI).

Se abre una sola vez, en el lifespan de la app (`gtm/ui/app.py`), no por
request — abrir un pool por request anularía el propósito de tener un pool.
"""

from __future__ import annotations

import asyncio
import sys

from psycopg_pool import AsyncConnectionPool

from gtm.factory.logs import get_logger
from gtm.store.dsn import get_dsn

_logger = get_logger(__name__)

if sys.platform == "win32":
    # psycopg (modo async, vía libpq) no funciona sobre el ProactorEventLoop
    # que asyncio usa por default en Windows desde Python 3.8 -- solo sobre un
    # SelectorEventLoop. Se fija acá, a nivel de módulo, porque este módulo se
    # importa (vía gtm/ui/app.py) durante `config.load_app()`, que uvicorn
    # corre *antes* de crear su propio event loop -- justo a tiempo para que
    # el loop que arme use la policy correcta. Sin esto, cada intento de
    # conexión falla con "Psycopg cannot use the 'ProactorEventLoop'" y el
    # pool nunca abre (aunque el DSN sea válido), degradando siempre al
    # outbox local en vez de escribir en el Postgres que de verdad configuraste.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def open_pool(*, timeout: float = 5.0) -> AsyncConnectionPool | None:
    """Abre el pool, o devuelve `None` si no hay DSN o no se pudo conectar.

    Nunca levanta: la UI tiene que poder arrancar sin Postgres (modo degradado,
    todo va al outbox local — ver `gtm/store/buffer.py`) en vez de no arrancar.
    """
    dsn = get_dsn()
    if dsn is None:
        _logger.info("sin SUPABASE_DB_URL: store deshabilitado", extra={"event": "store_disabled"})
        return None

    pool = AsyncConnectionPool(dsn, min_size=1, max_size=5, open=False)
    try:
        await pool.open(wait=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - degradamos, no abortamos el arranque de la UI
        _logger.warning(
            "no se pudo abrir el pool de Postgres",
            extra={"event": "pool_open_failed", "error": str(exc)},
        )
        await pool.close()
        return None

    _logger.info("pool de Postgres abierto", extra={"event": "pool_open_ok"})
    return pool


async def close_pool(pool: AsyncConnectionPool | None) -> None:
    if pool is not None:
        await pool.close()
