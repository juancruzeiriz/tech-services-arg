"""El worker de envío: tres tareas periódicas en segundo plano, lanzadas
desde el lifespan de `gtm/ui/app.py` junto al pool y al `RunRegistry`.

Cada 30s reclama mensajes listos y los manda; cada 10min lee la casilla de
rebotes; cada 15min revisa `demo_views` para confirmar entregas. Postgres es
requisito (`gtm/send/outbox.py` no funciona sin él): sin pool, `start_worker`
devuelve `None` y el envío automático queda deshabilitado limpiamente — la
cola manual sigue funcionando exactamente igual que siempre.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from collections.abc import Awaitable, Callable

from psycopg_pool import AsyncConnectionPool

from gtm.factory import config
from gtm.factory.logs import get_logger
from gtm.factory.types import ComplianceError, SenderIdentity
from gtm.send import bounces, outbox, smtp
from gtm.send.types import FailureKind, OutreachMessage, SmtpSettings

_logger = get_logger(__name__)

SEND_INTERVAL_SECONDS = 30
BOUNCE_INTERVAL_SECONDS = 600
DELIVERY_CHECK_INTERVAL_SECONDS = 900

# Veinte mails saliendo en ráfaga en dos segundos es exactamente el patrón
# que los filtros de spam buscan; el jitter imita el ritmo de una persona
# mandando mensajes uno por uno.
_MIN_JITTER_SECONDS = 60
_MAX_JITTER_SECONDS = 180


class Worker:
    """Encapsula las tres tareas periódicas y su ciclo de vida
    start/stop, para que `app.py` solo tenga que guardar una referencia."""

    def __init__(self, pool: AsyncConnectionPool, *, daily_cap: int = outbox.DEFAULT_DAILY_CAP) -> None:
        self.pool = pool
        self.daily_cap = daily_cap
        self._tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._loop(self.run_send_batch, SEND_INTERVAL_SECONDS), name="gtm-send"),
            asyncio.create_task(self._loop(self.run_bounce_check, BOUNCE_INTERVAL_SECONDS), name="gtm-bounces"),
            asyncio.create_task(
                self._loop(self.run_delivery_check, DELIVERY_CHECK_INTERVAL_SECONDS), name="gtm-delivery"
            ),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []

    async def _loop(self, fn: Callable[[], Awaitable[None]], interval: float) -> None:
        while True:
            try:
                await fn()
            except Exception as exc:  # noqa: BLE001 - una corrida fallida no puede matar al worker
                _logger.warning(
                    "tarea periódica de envío falló",
                    extra={"event": "worker_task_failed", "task": fn.__name__, "error": str(exc)},
                )
            await asyncio.sleep(interval)

    # --- envío -------------------------------------------------------------

    async def run_send_batch(self) -> None:
        messages = await outbox.claim_due(self.pool, limit=5, daily_cap=self.daily_cap)
        if not messages:
            return

        settings = config.load_smtp_settings()
        sender = config.load_sender_identity()

        for message in messages:
            await self._send_one(message, settings, sender)
            # Último mensaje del lote: no tiene sentido esperar el jitter
            # completo si no hay nada más para mandar detrás.
            if message is not messages[-1]:
                await asyncio.sleep(random.uniform(_MIN_JITTER_SECONDS, _MAX_JITTER_SECONDS))  # noqa: S311

    async def _send_one(
        self, message: OutreachMessage, settings: SmtpSettings, sender: SenderIdentity
    ) -> None:
        if message.channel != "email":
            # phone/contact_form son manuales a propósito (ver docs/CHANNELS.md):
            # el worker no manda nada por esos canales, solo email.
            return
        if not message.to_address:
            await outbox.mark_failed(self.pool, message, error="sin dirección de destino")
            return

        try:
            smtp.revalidate_before_send(message.body, sender)
        except ComplianceError as exc:
            await outbox.mark_failed(
                self.pool, message, error=str(exc), kind=FailureKind.COMPLIANCE
            )
            return

        verp_tag = message.verp_tag or smtp.new_verp_tag()
        envelope_sender = smtp.envelope_from(settings.bounce_address, verp_tag)
        mime = smtp.build_mime(message.subject or "", message.body, message.to_address, sender)

        result = await smtp.send_async(
            mime, settings=settings, envelope_sender=envelope_sender, to_address=message.to_address
        )

        if result.success:
            await outbox.mark_sent(
                self.pool, message, provider_message_id=result.provider_message_id, verp_tag=verp_tag
            )
        else:
            await outbox.mark_failed(
                self.pool, message, error=result.error or "error desconocido", verp_tag=verp_tag
            )

    # --- rebotes -------------------------------------------------------------

    async def run_bounce_check(self) -> None:
        imap_settings = config.load_imap_settings()
        raw_messages = await asyncio.to_thread(
            bounces.fetch_unseen,
            host=imap_settings.host,
            port=imap_settings.port,
            username=imap_settings.username,
            password=imap_settings.password,
        )
        for raw in raw_messages:
            await self._process_inbound(raw)

    async def _process_inbound(self, raw: str) -> None:
        classification = bounces.classify_inbound(raw)
        if classification.is_human_reply:
            # El evento más valioso del embudo entero -- no se toca, solo se
            # deja constancia de que llegó algo que no es un rebote.
            _logger.info(
                "posible respuesta humana en la casilla de rebotes",
                extra={"event": "possible_human_reply"},
            )
            return
        if classification.verp_tag is None or classification.bounce is None:
            return

        message = await outbox.get_by_verp_tag(self.pool, classification.verp_tag)
        if message is None:
            return

        hard = classification.bounce.kind is FailureKind.HARD_BOUNCE
        await outbox.mark_bounced(self.pool, message, hard=hard, detail=classification.bounce.detail)

    # --- confirmación de entrega --------------------------------------------

    async def run_delivery_check(self) -> None:
        opened = await outbox.find_opened_but_not_delivered(self.pool)
        for message in opened:
            await outbox.mark_delivered(self.pool, message)


def start_worker(pool: AsyncConnectionPool | None, *, daily_cap: int = outbox.DEFAULT_DAILY_CAP) -> Worker | None:
    """`None` sin pool: el envío automático se deshabilita limpiamente, igual
    que el resto de `gtm/store/` cuando no hay Postgres."""
    if pool is None:
        return None
    worker = Worker(pool, daily_cap=daily_cap)
    worker.start()
    return worker
