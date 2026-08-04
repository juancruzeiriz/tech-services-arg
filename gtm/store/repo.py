"""Escritura al store analítico: genérica por tabla, con degradación elegante.

`upsert()` arma el SQL de inserción a partir de una lista de columnas y de
cuáles forman la clave de conflicto -- no hay una función por tabla que repita
el mismo `INSERT ... ON CONFLICT` a mano. `TABLE_SPECS` es el catálogo de qué
columnas y qué clave tiene cada una de las 11 tablas; es lo que le permite a
`gtm/store/backfill.py` reintentar un envelope del outbox sin saber de qué
dataclass salió originalmente — solo necesita el nombre de la tabla.

Todo entra por acá con dicts JSON-safe (`str`, `int`, `float`, `bool`, `None` —
nunca `datetime`/`UUID`/enum crudos), porque son exactamente los mismos dicts
que, si Postgres no responde, terminan en el outbox (`gtm/store/buffer.py`) para
reintentar después. Mantener un solo formato evita tener una conversión para
"escribir directo" y otra distinta para "reintentar desde el outbox".
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg_pool import AsyncConnectionPool

from gtm.factory.logs import get_logger
from gtm.factory.pipeline import RunContext, RunResult
from gtm.factory.types import ContactPlan, Demo, OutreachEmail, PainScore, Prospect
from gtm.store import buffer

_logger = get_logger(__name__)

# tabla -> (columnas en orden, columnas que forman la clave de conflicto).
# Una clave de conflicto vacía significa "insert-only, sin upsert" -- ninguna
# tabla de acá cae en ese caso: ver el comentario de client_id en
# schema/0001_init.sql para por qué costs/time_log/demo_views sí tienen una.
TABLE_SPECS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "runs": (
        (
            "id", "started_at", "finished_at", "vertical", "metro", "language",
            "limit_n", "simulated", "dry_run", "seed", "author_name", "base_url",
            "status", "error",
        ),
        ("id",),
    ),
    "prospects": (
        (
            "place_id", "first_seen_at", "last_seen_at", "name", "vertical", "metro",
            "phone", "website", "rating", "review_count", "address", "web_presence",
        ),
        ("place_id",),
    ),
    "run_prospects": (("run_id", "place_id", "position"), ("run_id", "place_id")),
    "scores": (
        (
            "run_id", "place_id", "measured_at", "performance", "seo", "accessibility",
            "mobile_friendly", "has_web_presence", "reachable", "score", "is_qualified", "notes",
            "speed_score", "mobile_score", "seo_score", "modernity_score", "conversion_score",
            "crux_lcp_ms", "crux_inp_ms", "crux_cls", "has_field_data", "last_changed", "findings",
        ),
        ("run_id", "place_id"),
    ),
    "demos": (
        ("run_id", "place_id", "slug", "html_path", "url", "deployed_at", "language", "bytes"),
        ("run_id", "place_id"),
    ),
    "contacts": (
        ("run_id", "place_id", "channel", "target", "rationale", "pain_score", "is_actionable"),
        ("run_id", "place_id"),
    ),
    "outreach_emails": (
        (
            "run_id", "place_id", "to_email", "subject", "body", "demo_url", "language",
            "from_name", "from_email", "physical_address", "unsubscribe_url", "created_at", "sent_at",
        ),
        ("run_id", "place_id"),
    ),
    "funnel_events": (
        (
            "place_id_hash", "place_id", "run_id", "event", "level", "at", "vertical",
            "metro", "channel", "language", "pain_score", "amount_usd", "note",
        ),
        ("place_id_hash", "event", "at"),
    ),
    "suppressions": (("key", "kind", "reason", "at", "note"), ("key",)),
    "costs": (
        ("client_id", "at", "category", "vendor", "amount_usd", "run_id", "note"),
        ("client_id",),
    ),
    "time_log": (
        ("client_id", "at", "minutes", "activity", "run_id", "place_id", "note"),
        ("client_id",),
    ),
    "demo_links": (
        ("token", "demo_slug", "place_id", "channel", "run_id", "created_at"),
        ("token",),
    ),
    "demo_views": (
        (
            "client_id", "token", "demo_slug", "place_id", "at", "ip_hash",
            "user_agent", "referer", "is_probable_bot",
        ),
        ("client_id",),
    ),
}


def _build_upsert_sql(table: str, columns: tuple[str, ...], conflict_columns: tuple[str, ...]) -> str:
    col_list = ", ".join(columns)
    placeholders = ", ".join(f"%({c})s" for c in columns)
    update_cols = [c for c in columns if c not in conflict_columns]
    if update_cols:
        set_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
        conflict_clause = f"on conflict ({', '.join(conflict_columns)}) do update set {set_clause}"
    else:
        conflict_clause = f"on conflict ({', '.join(conflict_columns)}) do nothing"
    return f"insert into {table} ({col_list}) values ({placeholders}) {conflict_clause}"


async def upsert(
    pool: AsyncConnectionPool | None,
    table: str,
    rows: list[dict[str, Any]],
) -> bool:
    """Escribe `rows` en `table`. Devuelve `True` si se escribió en Postgres,
    `False` si se guardó en el outbox en su lugar (sin pool, o la escritura
    falló). Nunca levanta: ver el docstring del módulo."""
    if not rows:
        return True
    if table not in TABLE_SPECS:
        raise ValueError(f"tabla desconocida: {table!r} -- agregala a TABLE_SPECS")

    if pool is None:
        buffer.spool(table, rows)
        return False

    columns, conflict_columns = TABLE_SPECS[table]
    sql = _build_upsert_sql(table, columns, conflict_columns)
    try:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.executemany(sql, rows)
    except Exception as exc:  # noqa: BLE001 - degradamos, nunca abortamos la corrida
        _logger.warning(
            "no se pudo escribir en Postgres, se guarda en el outbox",
            extra={"event": "store_write_failed", "table": table, "count": len(rows), "error": str(exc)},
        )
        buffer.spool(table, rows)
        return False
    return True


# --- Constructores de filas: dataclass del pipeline -> dict JSON-safe --------


def prospect_row(prospect: Prospect, *, now: datetime | None = None) -> dict[str, Any]:
    at = (now or datetime.now(UTC)).isoformat()
    return {
        "place_id": prospect.place_id,
        "first_seen_at": at,
        "last_seen_at": at,
        "name": prospect.name,
        "vertical": prospect.vertical,
        "metro": prospect.metro,
        "phone": prospect.phone,
        "website": prospect.website,
        "rating": prospect.rating,
        "review_count": prospect.review_count,
        "address": prospect.address,
        "web_presence": prospect.web_presence.value,
    }


def run_prospect_row(run_id: str, prospect: Prospect, position: int) -> dict[str, Any]:
    return {"run_id": run_id, "place_id": prospect.place_id, "position": position}


def score_row(run_id: str, score: PainScore, *, now: datetime | None = None) -> dict[str, Any]:
    sub_scores = score.sub_scores
    return {
        "run_id": run_id,
        "place_id": score.place_id,
        "measured_at": (now or datetime.now(UTC)).isoformat(),
        "performance": score.performance,
        "seo": score.seo,
        "accessibility": score.accessibility,
        "mobile_friendly": score.mobile_friendly,
        "has_web_presence": score.has_web_presence,
        "reachable": score.reachable,
        "score": score.score,
        "is_qualified": score.is_qualified,
        "notes": list(score.notes),
        "speed_score": sub_scores["speed"],
        "mobile_score": sub_scores["mobile"],
        "seo_score": sub_scores["seo"],
        "modernity_score": sub_scores["modernity"],
        "conversion_score": sub_scores["conversion"],
        "crux_lcp_ms": score.crux_lcp_ms,
        "crux_inp_ms": score.crux_inp_ms,
        "crux_cls": score.crux_cls,
        "has_field_data": score.has_field_data,
        "last_changed": score.last_changed.isoformat() if score.last_changed else None,
        "findings": [
            {"code": f.code, "evidence": f.evidence, "weight": f.weight, "extra": dict(f.extra)}
            for f in score.findings
        ],
    }


def demo_row(run_id: str, demo: Demo, language: str, *, bytes_: int | None = None) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "place_id": demo.place_id,
        "slug": demo.slug,
        "html_path": demo.html_path,
        "url": demo.url,
        "deployed_at": demo.deployed_at.isoformat() if demo.deployed_at else None,
        "language": language,
        "bytes": bytes_,
    }


def contact_row(run_id: str, plan: ContactPlan) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "place_id": plan.place_id,
        "channel": plan.channel.value,
        "target": plan.target,
        "rationale": plan.rationale,
        "pain_score": plan.pain_score,
        "is_actionable": plan.is_actionable,
    }


def outreach_email_row(run_id: str, email: OutreachEmail) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "place_id": email.place_id,
        "to_email": email.to_email,
        "subject": email.subject,
        "body": email.body,
        "demo_url": email.demo_url,
        "language": email.language.value,
        "from_name": email.sender.from_name,
        "from_email": email.sender.from_email,
        "physical_address": email.sender.physical_address,
        "unsubscribe_url": email.sender.unsubscribe_url,
        "created_at": email.created_at.isoformat(),
        "sent_at": None,
    }


def cost_row(
    *, category: str, amount_usd: float, vendor: str | None = None,
    run_id: str | None = None, note: str = "", at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "client_id": str(uuid4()),
        "at": (at or datetime.now(UTC)).isoformat(),
        "category": category,
        "vendor": vendor,
        "amount_usd": amount_usd,
        "run_id": run_id,
        "note": note,
    }


def time_log_row(
    *, minutes: int, activity: str, run_id: str | None = None,
    place_id: str | None = None, note: str = "", at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "client_id": str(uuid4()),
        "at": (at or datetime.now(UTC)).isoformat(),
        "minutes": minutes,
        "activity": activity,
        "run_id": run_id,
        "place_id": place_id,
        "note": note,
    }


def run_row(
    ctx: RunContext, result: RunResult, *, finished_at: datetime | None = None
) -> dict[str, Any]:
    return {
        "id": ctx.run_id,
        "started_at": ctx.started_at.isoformat(),
        "finished_at": (finished_at or datetime.now(UTC)).isoformat(),
        "vertical": ctx.vertical,
        "metro": ctx.metro,
        "language": ctx.language.value,
        "limit_n": ctx.limit,
        "simulated": ctx.simulated,
        "dry_run": ctx.dry_run,
        "seed": ctx.seed,
        "author_name": ctx.author_name,
        "base_url": ctx.base_url,
        "status": "ok" if result.ok else "failed",
        "error": next((s.error for s in result.stages if not s.ok), None),
    }


async def persist_run(pool: AsyncConnectionPool | None, ctx: RunContext, result: RunResult) -> None:
    """Escribe una corrida completa: la fila de `runs`, y una fila por cada
    prospecto/score/demo/contacto/email que produjo. Se llama una vez, al final
    de `run_pipeline` -- por lote, no por etapa, porque ya viene todo junto en
    el `RunResult` y no hay ninguna ventaja en partirlo.

    Cada tabla se escribe por separado y cada una degrada al outbox por su
    cuenta si falla (ver `upsert`): que `scores` no se haya podido escribir no
    debe impedir que `prospects` sí se guarde.
    """
    await upsert(pool, "runs", [run_row(ctx, result)])
    await upsert(pool, "prospects", [prospect_row(p) for p in result.prospects])
    await upsert(
        pool,
        "run_prospects",
        [run_prospect_row(ctx.run_id, p, i) for i, p in enumerate(result.prospects)],
    )
    await upsert(pool, "scores", [score_row(ctx.run_id, s) for s in result.scores])
    await upsert(
        pool, "demos", [demo_row(ctx.run_id, d, ctx.language.value) for d in result.demos]
    )
    await upsert(pool, "contacts", [contact_row(ctx.run_id, c) for c in result.contacts])
    await upsert(
        pool, "outreach_emails", [outreach_email_row(ctx.run_id, e) for e in result.emails]
    )


async def record_cost(
    pool: AsyncConnectionPool | None,
    *,
    category: str,
    amount_usd: float,
    vendor: str | None = None,
    run_id: str | None = None,
    note: str = "",
) -> bool:
    """El "write path" de costos: sin esto, `FunnelReport.spend_usd` seguía
    siendo un número tipeado a mano en `ledger report --spend`, y
    `cost_per_call` nunca fue un dato real. Devuelve `True` si se escribió en
    Postgres, `False` si quedó en el outbox (ver `upsert`)."""
    return await upsert(pool, "costs", [cost_row(category=category, amount_usd=amount_usd, vendor=vendor, run_id=run_id, note=note)])


async def total_cost_usd(pool: AsyncConnectionPool | None) -> float:
    """Suma de `costs.amount_usd` en Postgres. `0.0` sin pool o si la lectura
    falla -- el dashboard tiene que poder renderizar sin DB, igual que el resto
    de la UI (ver el docstring del módulo). No ve lo que quedó en el outbox sin
    reintentar todavía; `python -m gtm.store.backfill` lo resuelve."""
    if pool is None:
        return 0.0
    try:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute("select coalesce(sum(amount_usd), 0) from costs")
            row = await cur.fetchone()
            return float(row[0]) if row else 0.0
    except Exception as exc:  # noqa: BLE001 - degradamos a 0, no rompemos el dashboard
        _logger.warning(
            "no se pudo leer costos", extra={"event": "read_costs_failed", "error": str(exc)}
        )
        return 0.0


async def total_minutes_logged(pool: AsyncConnectionPool | None) -> int:
    """Suma de `time_log.minutes` en Postgres -- ver `total_cost_usd` para las
    mismas salvedades (degradación y outbox no reintentado)."""
    if pool is None:
        return 0
    try:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute("select coalesce(sum(minutes), 0) from time_log")
            row = await cur.fetchone()
            return int(row[0]) if row else 0
    except Exception as exc:  # noqa: BLE001 - degradamos a 0, no rompemos el dashboard
        _logger.warning(
            "no se pudo leer horas cargadas",
            extra={"event": "read_time_log_failed", "error": str(exc)},
        )
        return 0


async def record_time(
    pool: AsyncConnectionPool | None,
    *,
    minutes: int,
    activity: str,
    run_id: str | None = None,
    place_id: str | None = None,
    note: str = "",
) -> bool:
    """El "write path" de horas: sin esto, `horas_mes_por_cliente` (el
    desempate por mantenibilidad de `decision_criteria.yaml`) nunca tuvo un
    dato real -- "¿esto da un ingreso extra por hora?" era literalmente
    incalculable."""
    return await upsert(pool, "time_log", [time_log_row(minutes=minutes, activity=activity, run_id=run_id, place_id=place_id, note=note)])
