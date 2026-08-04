"""Carga histórica: JSONL local -> Postgres, y reintento del outbox.

Dos fuentes distintas, dos funciones:

  backfill_jsonl()  -- gtm/suppression.jsonl y gtm/funnel.jsonl -> Postgres.
                       Idempotente por diseño: las claves de conflicto de
                       `suppressions`/`funnel_events` son las mismas que esos
                       archivos ya usan para des-duplicar, así que correr esto
                       muchas veces es seguro y no crea filas repetidas.

  replay_outbox()   -- gtm/build/outbox.jsonl -> Postgres. Lo que se guardó ahí
                       porque Postgres no respondía en el momento de una
                       corrida. Un envelope que sigue sin poder escribirse
                       vuelve al outbox tal cual; solo se descartan los que sí
                       se escribieron.

Uso:
    python -m gtm.store.backfill              # las dos cosas
    python -m gtm.store.backfill --jsonl-only
    python -m gtm.store.backfill --outbox-only
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from psycopg_pool import AsyncConnectionPool

from gtm.factory.ledger import read_funnel_records, read_suppression_records
from gtm.factory.logs import get_logger
from gtm.store import buffer, repo
from gtm.store.dsn import get_dsn
from gtm.store.pool import close_pool, open_pool

_logger = get_logger(__name__)


def _suppression_row(record: dict) -> dict:
    return {
        "key": record["key"],
        "kind": record["kind"],
        "reason": record["reason"],
        "at": record["at"],
        "note": record.get("note", ""),
    }


def _funnel_row(record: dict) -> dict:
    """`place_id` queda en `None`: el JSONL nunca tuvo el valor real, solo el
    hash (ver el comentario en `schema/0001_init.sql`). `.get(...)` con
    default en los campos que `channel`/`language`/`run_id` no tenían antes de
    que se agregaran — un registro viejo del JSONL no debe hacer fallar el
    backfill."""
    return {
        "place_id_hash": record["key"],
        "place_id": None,
        "run_id": record.get("run_id") or None,
        "event": record["event"],
        "level": record["level"],
        "at": record["at"],
        "vertical": record.get("vertical", ""),
        "metro": record.get("metro", ""),
        "channel": record.get("channel") or None,
        "language": record.get("language") or None,
        "pain_score": record.get("pain_score", 0),
        "amount_usd": record.get("amount_usd", 0.0),
        "note": record.get("note", ""),
    }


async def backfill_jsonl(
    pool: AsyncConnectionPool | None,
    *,
    suppression_path: Path | None = None,
    funnel_path: Path | None = None,
) -> dict[str, int]:
    """Vuelca `gtm/suppression.jsonl` y `gtm/funnel.jsonl` a Postgres. Devuelve
    cuántos registros de cada uno se procesaron (no necesariamente escritos:
    con `pool=None` van al outbox, igual que cualquier otra escritura)."""
    suppression_rows = [_suppression_row(r) for r in read_suppression_records(suppression_path)]
    funnel_rows = [_funnel_row(r) for r in read_funnel_records(funnel_path)]

    await repo.upsert(pool, "suppressions", suppression_rows)
    await repo.upsert(pool, "funnel_events", funnel_rows)

    return {"suppressions": len(suppression_rows), "funnel_events": len(funnel_rows)}


async def replay_outbox(
    pool: AsyncConnectionPool | None, path: Path | None = None
) -> dict[str, int]:
    """Reintenta cada envelope pendiente. Sin pool, no hay nada que intentar --
    devuelve el conteo de pendientes tal cual, sin tocar el archivo."""
    target = path or buffer.OUTBOX_PATH
    if pool is None:
        return {"replayed": 0, "remaining": buffer.pending_count(target)}

    envelopes = buffer.read_all(target)
    if not envelopes:
        return {"replayed": 0, "remaining": 0}

    still_pending: list[dict] = []
    replayed = 0
    for envelope in envelopes:
        table = envelope["table"]
        rows = envelope["rows"]
        columns, conflict_columns = repo.TABLE_SPECS[table]
        sql = repo._build_upsert_sql(table, columns, conflict_columns)
        try:
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.executemany(sql, rows)
        except Exception as exc:  # noqa: BLE001 - se re-encola, no se aborta el resto
            _logger.warning(
                "envelope del outbox sigue sin poder escribirse",
                extra={"event": "outbox_replay_failed", "table": table, "count": len(rows), "error": str(exc)},
            )
            still_pending.append(envelope)
        else:
            replayed += 1

    # Se reescribe el archivo entero -- vacío si todo entró, o solo con lo que
    # sigue pendiente -- en vez de ir sacando líneas de a una: un envelope que
    # sí se escribió no debe poder volver a aparecer en un reintento futuro.
    buffer.clear(target)
    for envelope in still_pending:
        buffer.spool(envelope["table"], envelope["rows"], path=target)

    return {"replayed": replayed, "remaining": len(still_pending)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill del store: JSONL local y outbox pendiente -> Postgres"
    )
    parser.add_argument("--jsonl-only", action="store_true", help="solo gtm/*.jsonl")
    parser.add_argument("--outbox-only", action="store_true", help="solo el outbox pendiente")
    args = parser.parse_args(argv)

    if get_dsn() is None:
        print("Falta SUPABASE_DB_URL en .env.personal", file=sys.stderr)
        return 1

    async def _run() -> int:
        pool = await open_pool()
        if pool is None:
            print("No se pudo conectar a Postgres con el DSN configurado", file=sys.stderr)
            return 1
        try:
            if not args.outbox_only:
                counts = await backfill_jsonl(pool)
                print(
                    f"JSONL -> Postgres: {counts['suppressions']} supresiones, "
                    f"{counts['funnel_events']} eventos de embudo"
                )
            if not args.jsonl_only:
                result = await replay_outbox(pool)
                print(
                    f"Outbox: {result['replayed']} envelopes reintentados, "
                    f"{result['remaining']} siguen pendientes"
                )
        finally:
            await close_pool(pool)
        return 0

    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
