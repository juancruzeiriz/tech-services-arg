"""La cola de envío: máquina de estados sobre `outreach_messages`.

Postgres es requisito acá, a diferencia del resto del pipeline: este módulo
necesita UPDATE, `SELECT ... FOR UPDATE SKIP LOCKED` y un `next_attempt_at`
consultado por rango, y un archivo JSONL append-only no puede hacer ninguna
de las tres. Consecuencia asumida: sin `SUPABASE_DB_URL` no hay envío
automático — la cola manual (`gtm/ui/routes/queue.py`) sigue funcionando
exactamente igual que siempre.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg_pool import AsyncConnectionPool

from gtm.send.types import DEFAULT_DAILY_CAP, FailureKind, MessageStatus, OutreachMessage
from gtm.store import repo

# DEFAULT_DAILY_CAP se re-exporta desde gtm.send.types (ver el comentario ahí
# sobre por qué vive en ese módulo y no en este) -- gtm.factory.config lo usa
# a través de gtm.send.types directamente, y el resto del código lo sigue
# viendo como outbox.DEFAULT_DAILY_CAP, sin cambios.

# Un rebote suave suele ser un buzón lleno o un greylist temporal: reintentar
# en el mismo minuto garantiza el mismo fallo. Las horas crecen y frenan en
# 72h -- no tiene sentido esperar una semana por un mensaje de prospección.
_BACKOFF_HOURS = (4, 24, 72)

_CLAIM_COLUMNS = (
    "id", "client_id", "run_id", "place_id", "channel", "to_address", "subject", "body",
    "link_token", "status", "attempt_count", "max_attempts", "next_attempt_at",
    "provider_message_id", "verp_tag", "created_at", "queued_at", "sent_at",
    "delivered_at", "failed_at", "failure_kind", "failure_reason", "last_error",
)


def backoff_for_attempt(attempt: int) -> timedelta:
    """Espera antes del intento `attempt` (1-indexed)."""
    index = min(max(attempt, 1), len(_BACKOFF_HOURS)) - 1
    return timedelta(hours=_BACKOFF_HOURS[index])


async def enqueue(pool: AsyncConnectionPool, messages: list[OutreachMessage]) -> int:
    """Encola mensajes para envío. Devuelve cuántos se procesaron (en
    Postgres o en el outbox local si Postgres no respondió — `repo.upsert`
    nunca levanta)."""
    if not messages:
        return 0
    now = datetime.now(UTC)
    queued = [
        replace(m, status=MessageStatus.QUEUED, queued_at=now, next_attempt_at=now)
        for m in messages
    ]
    await repo.upsert(pool, "outreach_messages", [repo.outreach_message_row(m) for m in queued])
    return len(queued)


async def daily_sent_count(pool: AsyncConnectionPool) -> int:
    """Cuántos mensajes salieron hoy (UTC) — lo que compara `claim_due`
    contra el tope diario antes de reclamar más trabajo."""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "select count(*) from outreach_messages where sent_at >= date_trunc('day', now())"
        )
        row = await cur.fetchone()
        return int(row[0]) if row else 0


def _row_to_message(row: tuple[Any, ...]) -> OutreachMessage:
    data = dict(zip(_CLAIM_COLUMNS, row, strict=True))
    return OutreachMessage(
        id=data["id"],
        client_id=data["client_id"],
        run_id=data["run_id"],
        place_id=data["place_id"],
        channel=data["channel"],
        to_address=data["to_address"],
        subject=data["subject"],
        body=data["body"],
        link_token=data["link_token"],
        status=MessageStatus(data["status"]),
        attempt_count=data["attempt_count"],
        max_attempts=data["max_attempts"],
        next_attempt_at=data["next_attempt_at"],
        provider_message_id=data["provider_message_id"],
        verp_tag=data["verp_tag"],
        created_at=data["created_at"],
        queued_at=data["queued_at"],
        sent_at=data["sent_at"],
        delivered_at=data["delivered_at"],
        failed_at=data["failed_at"],
        failure_kind=data["failure_kind"],
        failure_reason=data["failure_reason"],
        last_error=data["last_error"],
    )


async def claim_due(
    pool: AsyncConnectionPool, limit: int, *, daily_cap: int = DEFAULT_DAILY_CAP
) -> list[OutreachMessage]:
    """Reclama hasta `limit` mensajes listos para enviar, sin superar
    `daily_cap` envíos por día civil UTC. `FOR UPDATE SKIP LOCKED`: dos
    workers corriendo a la vez nunca reclaman el mismo mensaje dos veces —
    el segundo simplemente salta las filas que el primero ya tomó, en vez de
    esperarlas o duplicar el envío.
    """
    already_sent = await daily_sent_count(pool)
    remaining = max(0, daily_cap - already_sent)
    if remaining <= 0:
        return []
    take = min(limit, remaining)

    cols = ", ".join(_CLAIM_COLUMNS)
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            f"""
            select {cols} from outreach_messages
            where status = %(status)s
              and (next_attempt_at is null or next_attempt_at <= now())
            order by next_attempt_at nulls first, created_at
            for update skip locked
            limit %(take)s
            """,
            {"status": MessageStatus.QUEUED.value, "take": take},
        )
        rows = await cur.fetchall()
        if not rows:
            return []

        ids = [row[0] for row in rows]
        await cur.execute(
            "update outreach_messages set status = %(status)s where id = any(%(ids)s)",
            {"status": MessageStatus.SENDING.value, "ids": ids},
        )

    return [replace(_row_to_message(row), status=MessageStatus.SENDING) for row in rows]


async def enqueue_manual(pool: AsyncConnectionPool, messages: list[OutreachMessage]) -> int:
    """Encola mensajes de canal manual (`phone`/`contact_form`): a diferencia de
    `enqueue`, quedan en `manual_pending`, no en `queued`. El worker de envío
    ignora a propósito esos dos canales (ver `gtm/send/worker.py`) -- dejarlos
    en `queued` haría que `claim_due` los reclame, los suba a `sending`, y ahí
    se queden colgados para siempre, porque nada los mueve de ese estado."""
    if not messages:
        return 0
    now = datetime.now(UTC)
    queued = [replace(m, status=MessageStatus.MANUAL_PENDING, queued_at=now) for m in messages]
    await repo.upsert(pool, "outreach_messages", [repo.outreach_message_row(m) for m in queued])
    return len(queued)


async def mark_manual_done(pool: AsyncConnectionPool, message: OutreachMessage) -> OutreachMessage:
    """El botón "Marcar enviado" de `/outbox`, para teléfono y formulario --
    canales que el operador despacha a mano y confirma él mismo."""
    if not message.status.can_transition_to(MessageStatus.MANUAL_DONE):
        raise ValueError(f"no se puede marcar como enviado un mensaje en estado {message.status.value!r}")
    updated = replace(message, status=MessageStatus.MANUAL_DONE, sent_at=datetime.now(UTC))
    await repo.upsert(pool, "outreach_messages", [repo.outreach_message_row(updated)])
    return updated


async def cancel(pool: AsyncConnectionPool, message: OutreachMessage) -> OutreachMessage:
    """El botón "Cancelar" de `/outbox`, para un mensaje que todavía no salió."""
    if not message.status.can_transition_to(MessageStatus.CANCELLED):
        raise ValueError(f"no se puede cancelar un mensaje en estado {message.status.value!r}")
    updated = replace(message, status=MessageStatus.CANCELLED)
    await repo.upsert(pool, "outreach_messages", [repo.outreach_message_row(updated)])
    return updated


async def get_by_id(pool: AsyncConnectionPool, message_id: int) -> OutreachMessage | None:
    cols = ", ".join(_CLAIM_COLUMNS)
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            f"select {cols} from outreach_messages where id = %(id)s", {"id": message_id}
        )
        row = await cur.fetchone()
    return _row_to_message(row) if row else None


async def list_messages(
    pool: AsyncConnectionPool, *, status: MessageStatus | None = None, limit: int = 200
) -> list[OutreachMessage]:
    """Para la pantalla `/outbox`: los mensajes más recientes primero, con
    filtro opcional por estado."""
    cols = ", ".join(_CLAIM_COLUMNS)
    where = "where status = %(status)s" if status is not None else ""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            f"select {cols} from outreach_messages {where} order by created_at desc limit %(limit)s",
            {"status": status.value if status is not None else None, "limit": limit},
        )
        rows = await cur.fetchall()
    return [_row_to_message(row) for row in rows]


async def get_by_verp_tag(pool: AsyncConnectionPool, verp_tag: str) -> OutreachMessage | None:
    """El mensaje que generó ese tag VERP, o None. Es cómo `worker.py`
    empareja un rebote recién leído con el mensaje que lo causó, sin tener
    que abrir el cuerpo del DSN para buscar una referencia."""
    cols = ", ".join(_CLAIM_COLUMNS)
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            f"select {cols} from outreach_messages where verp_tag = %(tag)s",
            {"tag": verp_tag},
        )
        row = await cur.fetchone()
    return _row_to_message(row) if row else None


async def find_opened_but_not_delivered(pool: AsyncConnectionPool) -> list[OutreachMessage]:
    """Mensajes `sent` cuyo link con token tuvo una apertura no-bot en
    `demo_views` — la confirmación de entrega para los tres canales, no solo
    email: el mismo link con tracking se manda por formulario y por teléfono.
    """
    cols = ", ".join(f"m.{c}" for c in _CLAIM_COLUMNS)
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            f"""
            select {cols} from outreach_messages m
            where m.status = %(status)s
              and m.link_token is not null
              and exists (
                  select 1 from demo_views v
                  where v.token = m.link_token and v.is_probable_bot = false
              )
            """,
            {"status": MessageStatus.SENT.value},
        )
        rows = await cur.fetchall()
    return [_row_to_message(row) for row in rows]


async def mark_sent(
    pool: AsyncConnectionPool,
    message: OutreachMessage,
    *,
    provider_message_id: str | None,
    verp_tag: str | None = None,
) -> OutreachMessage:
    """`verp_tag`: el que se usó como remitente de sobre en este intento
    (`smtp.envelope_from`) -- si no se persiste acá, un rebote que llegue
    después nunca podría encontrar este mensaje por `get_by_verp_tag`."""
    updated = replace(
        message,
        status=MessageStatus.SENT,
        sent_at=datetime.now(UTC),
        attempt_count=message.attempt_count + 1,
        provider_message_id=provider_message_id,
        verp_tag=verp_tag or message.verp_tag,
    )
    await repo.upsert(pool, "outreach_messages", [repo.outreach_message_row(updated)])
    return updated


async def mark_failed(
    pool: AsyncConnectionPool,
    message: OutreachMessage,
    *,
    error: str,
    kind: FailureKind = FailureKind.SMTP_ERROR,
    verp_tag: str | None = None,
) -> OutreachMessage:
    """Un error no conforme (`FailureKind.COMPLIANCE`) nunca se reintenta,
    aunque queden intentos disponibles: un mensaje no conforme reintentado
    tres veces es tres infracciones, no una recuperación de un error
    transitorio."""
    attempt = message.attempt_count + 1
    can_retry = attempt < message.max_attempts and kind is not FailureKind.COMPLIANCE

    updated = replace(
        message,
        status=MessageStatus.QUEUED if can_retry else MessageStatus.FAILED,
        attempt_count=attempt,
        failure_kind=kind.value,
        failure_reason=error,
        last_error=error,
        failed_at=datetime.now(UTC),
        next_attempt_at=(datetime.now(UTC) + backoff_for_attempt(attempt)) if can_retry else None,
        verp_tag=verp_tag or message.verp_tag,
    )
    await repo.upsert(pool, "outreach_messages", [repo.outreach_message_row(updated)])
    return updated


async def mark_bounced(
    pool: AsyncConnectionPool, message: OutreachMessage, *, hard: bool, detail: str | None = None
) -> OutreachMessage:
    """Un rebote duro es terminal (la dirección no existe: reintentar no
    cambia eso, y `bounces.py` además suprime el prospecto). Uno suave
    reencola con el mismo backoff que un error transitorio cualquiera."""
    kind = FailureKind.HARD_BOUNCE if hard else FailureKind.SOFT_BOUNCE

    if hard:
        updated = replace(
            message,
            status=MessageStatus.BOUNCED,
            failure_kind=kind.value,
            failure_reason=detail,
            failed_at=datetime.now(UTC),
        )
    else:
        attempt = max(1, message.attempt_count)
        updated = replace(
            message,
            status=MessageStatus.QUEUED,
            failure_kind=kind.value,
            failure_reason=detail,
            next_attempt_at=datetime.now(UTC) + backoff_for_attempt(attempt),
        )

    await repo.upsert(pool, "outreach_messages", [repo.outreach_message_row(updated)])
    return updated


async def mark_delivered(pool: AsyncConnectionPool, message: OutreachMessage) -> OutreachMessage:
    """Confirmado por la apertura del link con token — ver `demo_views` y la
    Cloudflare Pages Function. No requiere que el mensaje haya pasado por
    `sent` primero porque un canal manual (formulario/teléfono) puede
    marcarse `delivered` sin haber pasado por el worker de SMTP."""
    updated = replace(message, status=MessageStatus.DELIVERED, delivered_at=datetime.now(UTC))
    await repo.upsert(pool, "outreach_messages", [repo.outreach_message_row(updated)])
    return updated


async def requeue(pool: AsyncConnectionPool, message: OutreachMessage) -> OutreachMessage:
    """Reenvío manual (el botón "Reintentar" de la UI). Rechaza estados
    terminales explícitamente en vez de dejar que el `UPDATE` simplemente no
    tenga efecto — un botón de reintentar que falla en silencio es peor que
    uno que no aparece.

    `MessageStatus.BOUNCED.can_transition_to(QUEUED)` por sí solo no alcanza:
    la máquina de estados genérica solo conoce el `status`, y `bounced` cubre
    tanto el rebote duro (la dirección no existe, terminal) como el suave
    (reintentable) — la diferencia vive en `failure_kind`, no en el estado.
    """
    is_hard_bounce = (
        message.status is MessageStatus.BOUNCED and message.failure_kind == FailureKind.HARD_BOUNCE.value
    )
    if is_hard_bounce or not message.status.can_transition_to(MessageStatus.QUEUED):
        raise ValueError(
            f"no se puede reencolar un mensaje en estado {message.status.value!r}"
        )
    updated = replace(
        message,
        status=MessageStatus.QUEUED,
        next_attempt_at=datetime.now(UTC),
        failure_kind=None,
        failure_reason=None,
        last_error=None,
    )
    await repo.upsert(pool, "outreach_messages", [repo.outreach_message_row(updated)])
    return updated
