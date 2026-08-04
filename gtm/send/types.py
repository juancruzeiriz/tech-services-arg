"""El mensaje de envío, su máquina de estados, y el resultado de un intento."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

# Lo que protege la reputación del dominio de envío más que cualquier otra
# cosa: 20-25/día es lo que ya recomienda docs/CHANNELS.md para una casilla
# nueva, y coincide con el volumen real del proyecto (25 prospectos/semana).
#
# Vive acá, no en gtm/send/outbox.py, para que gtm/factory/config.py pueda
# leerlo sin un ciclo de imports: config -> outbox -> gtm.store.repo ->
# gtm.factory.pipeline -> gtm.factory.config otra vez. Este módulo (types.py)
# no importa nada del propio paquete, así que es un punto seguro desde
# cualquier lado.
DEFAULT_DAILY_CAP = 20


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


@dataclass(frozen=True, slots=True)
class SmtpSettings:
    """Credenciales de la casilla de envío. `bounce_address` es la casilla
    que actúa como remitente VERP (`gtm/send/smtp.py`) -- normalmente la
    misma casilla que `gtm/send/bounces.py` lee por IMAP, aunque ese módulo
    tiene su propia configuración de host/puerto porque IMAP y SMTP suelen
    vivir en subdominios distintos del mismo proveedor."""

    host: str
    port: int
    username: str
    password: str
    bounce_address: str


@dataclass(frozen=True, slots=True)
class ImapSettings:
    """Host/puerto propios (IMAP y SMTP suelen vivir en subdominios
    distintos), pero mismas credenciales que `SmtpSettings`: es la misma
    casilla, solo que leída por otro protocolo."""

    host: str
    port: int
    username: str
    password: str
