"""El mensaje de envío, su máquina de estados, y el resultado de un intento."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MessageStatus(StrEnum):
    """draft -> queued -> sending -> sent -> delivered
                                   \\-> failed/bounced -> (reintento) -> queued
       draft -> manual_pending -> manual_done   (formulario y teléfono)
       cualquiera -> cancelled  (suprimido antes de salir)
    """

    DRAFT = "draft"
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    BOUNCED = "bounced"
    FAILED = "failed"
    MANUAL_PENDING = "manual_pending"
    MANUAL_DONE = "manual_done"
    CANCELLED = "cancelled"

    def can_transition_to(self, target: MessageStatus) -> bool:
        """¿Es esta una transición válida? Un mensaje que ya salió (`sent`)
        nunca vuelve directo a `queued` — pasa por `failed`/`bounced` primero,
        que es lo que garantiza que un reenvío tiene una RAZÓN registrada y no
        puede duplicar un mensaje que en realidad ya llegó."""
        return target in _TRANSITIONS.get(self, frozenset())

    def is_terminal(self, *, hard: bool = False) -> bool:
        """`hard=True` es lo que pregunta un rebote duro: en ese caso `bounced`
        también es terminal (no se reintenta un email a una dirección que no
        existe), a diferencia de un rebote suave, que sí puede reencolarse."""
        if self in _TERMINAL_ALWAYS:
            return True
        return self is MessageStatus.BOUNCED and hard


_TERMINAL_ALWAYS = frozenset({MessageStatus.DELIVERED, MessageStatus.MANUAL_DONE, MessageStatus.CANCELLED})

_TRANSITIONS: dict[MessageStatus, frozenset[MessageStatus]] = {
    MessageStatus.DRAFT: frozenset(
        {MessageStatus.QUEUED, MessageStatus.MANUAL_PENDING, MessageStatus.CANCELLED}
    ),
    MessageStatus.QUEUED: frozenset({MessageStatus.SENDING, MessageStatus.CANCELLED}),
    MessageStatus.SENDING: frozenset(
        {MessageStatus.SENT, MessageStatus.FAILED, MessageStatus.BOUNCED}
    ),
    MessageStatus.SENT: frozenset({MessageStatus.DELIVERED, MessageStatus.BOUNCED}),
    MessageStatus.FAILED: frozenset({MessageStatus.QUEUED, MessageStatus.CANCELLED}),
    # Solo el rebote SUAVE vuelve a queued vía esta transición genérica; el
    # rebote duro es terminal (ver is_terminal) y en la práctica nunca pasa
    # por acá porque bounces.py suprime el prospecto en vez de reencolarlo.
    MessageStatus.BOUNCED: frozenset({MessageStatus.QUEUED}),
    MessageStatus.DELIVERED: frozenset(),
    MessageStatus.MANUAL_PENDING: frozenset({MessageStatus.MANUAL_DONE, MessageStatus.CANCELLED}),
    MessageStatus.MANUAL_DONE: frozenset(),
    MessageStatus.CANCELLED: frozenset(),
}


class FailureKind(StrEnum):
    HARD_BOUNCE = "hard_bounce"
    SOFT_BOUNCE = "soft_bounce"
    SMTP_ERROR = "smtp_error"
    COMPLIANCE = "compliance"


@dataclass(frozen=True, slots=True)
class OutreachMessage:
    """Un mensaje en la cola, en cualquier punto de su máquina de estados.

    `client_id` es la identidad estable, generada en Python antes del primer
    intento de escritura — `id` (bigserial) no se conoce hasta después del
    insert, y este mensaje se reescribe muchas veces contra la misma fila."""

    client_id: str
    place_id: str
    channel: str
    body: str
    id: int | None = None
    run_id: str | None = None
    to_address: str | None = None
    subject: str | None = None
    link_token: str | None = None
    status: MessageStatus = MessageStatus.DRAFT
    attempt_count: int = 0
    max_attempts: int = 3
    next_attempt_at: datetime | None = None
    provider_message_id: str | None = None
    verp_tag: str | None = None
    created_at: datetime | None = None
    queued_at: datetime | None = None
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    failed_at: datetime | None = None
    failure_kind: str | None = None
    failure_reason: str | None = None
    last_error: str | None = None


@dataclass(frozen=True, slots=True)
class SendResult:
    """Lo que devuelve un intento de envío real (SMTP)."""

    success: bool
    provider_message_id: str | None = None
    error: str | None = None
