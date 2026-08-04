"""Lector de rebotes: IMAP + RFC 3464 (Delivery Status Notifications).

`imaplib` de la stdlib en un hilo, no una librería de terceros: es una
casilla que se revisa cada 10 minutos (ver `gtm/send/worker.py`), no un
cliente de correo completo. La misma casilla recibe también respuestas
humanas reales — el evento más valioso del embudo entero — así que lo
primero que hace este módulo es distinguir un rebote de una respuesta, no
asumir que todo lo que llega es un rebote.
"""

from __future__ import annotations

import email
import imaplib
import re
from dataclasses import dataclass
from email.message import Message

from gtm.factory.logs import get_logger
from gtm.send.types import FailureKind

_logger = get_logger(__name__)

# RFC 3464 §2.3.3: "Status: 5.1.1", clase 2 (success, no debería aparecer acá),
# 4 (transitorio) o 5 (permanente). Solo nos importa la primera cifra.
_STATUS_RE = re.compile(r"\b([245])\.\d+\.\d+\b")
_SMTP_CODE_RE = re.compile(r"\b(\d{3})\b")


@dataclass(frozen=True, slots=True)
class BounceReport:
    kind: FailureKind
    recipient: str | None
    detail: str | None
    smtp_code: int | None


@dataclass(frozen=True, slots=True)
class InboundClassification:
    """Lo que se sabe de un mail recibido en la casilla de rebotes, antes de
    decidir qué hacer con él."""

    is_dsn: bool
    is_human_reply: bool
    bounce: BounceReport | None
    verp_tag: str | None
    in_reply_to: str | None


def verp_tag_from(address: str) -> str | None:
    """Extrae el tag de una dirección VERP (`usuario+tag@dominio`), o None
    si la dirección no tiene el separador `+`. Tolera un nombre para mostrar
    delante (`"Alguien" <usuario+tag@dominio>`)."""
    _, _, addr_part = address.rpartition("<")
    addr_part = addr_part.rstrip(">").strip() or address.strip()
    local = addr_part.split("@", 1)[0]
    if "+" not in local:
        return None
    return local.split("+", 1)[1]


def _status_fields(status_part: Message) -> Message:
    """El contenido de un `message/delivery-status` son DOS grupos de campos
    tipo header (RFC 3464 §2.2-2.3): el primero es "por-mensaje"
    (`Reporting-MTA`...), el o los siguientes son "por-destinatario"
    (`Final-Recipient`, `Action`, `Status`...). Python parsea esto como una
    lista de `Message` anidados, uno por bloque — hay que buscar
    específicamente el que tiene `Final-Recipient`, no asumir que es el
    primero de la lista (ese es el bloque por-mensaje)."""
    payload = status_part.get_payload()
    blocks: list[Message] = []
    if isinstance(payload, list):
        blocks = [p for p in payload if isinstance(p, Message)]
    elif isinstance(payload, str):
        blocks = [email.message_from_string(payload)]

    for block in blocks:
        if block.get("Final-Recipient") is not None:
            return block
    return blocks[-1] if blocks else email.message_from_string("")


def parse_dsn(raw: str) -> BounceReport | None:
    """Parsea un Delivery Status Notification. Devuelve `None` si `raw` no
    es un DSN — una respuesta humana real no puede tratarse como rebote."""
    try:
        msg = email.message_from_string(raw)
    except Exception:  # noqa: BLE001 - un mail mal formado no es un DSN, no es un fallo del poller
        return None

    if not msg.is_multipart():
        return None
    if msg.get_content_type() != "multipart/report":
        return None
    # get_param puede devolver una tupla (RFC 2231, valores con charset/idioma
    # codificado) en vez de un str plano -- "report-type" nunca viene así en
    # la práctica, pero mypy no lo sabe sin este chequeo.
    report_type = msg.get_param("report-type")
    if not isinstance(report_type, str) or report_type.lower() != "delivery-status":
        return None

    status_part = next(
        (part for part in msg.walk() if part.get_content_type() == "message/delivery-status"),
        None,
    )
    if status_part is None:
        return None

    fields = _status_fields(status_part)

    recipient = fields.get("Final-Recipient")
    if recipient:
        # "rfc822; info@plomeria.com" -> "info@plomeria.com"
        recipient = recipient.rsplit(";", 1)[-1].strip()

    diagnostic = fields.get("Diagnostic-Code", "")
    status_match = _STATUS_RE.search(fields.get("Status", "")) or _STATUS_RE.search(diagnostic)

    if status_match is None:
        # Sin evidencia de clase de status: nunca se asume terminal por
        # default. Un rebote duro solo se declara con un 5.x.x explícito.
        kind = FailureKind.SOFT_BOUNCE
    elif status_match.group(1) == "5":
        kind = FailureKind.HARD_BOUNCE
    else:
        kind = FailureKind.SOFT_BOUNCE

    code_match = _SMTP_CODE_RE.search(diagnostic)
    smtp_code = int(code_match.group(1)) if code_match else None

    return BounceReport(
        kind=kind,
        recipient=recipient,
        detail=diagnostic or fields.get("Status") or None,
        smtp_code=smtp_code,
    )


def classify_inbound(raw: str) -> InboundClassification:
    """Clasifica un mail recibido en la casilla de rebotes: ¿es un DSN, o
    una respuesta humana real? Lo que no es un DSN se marca como posible
    respuesta y no se toca — es el evento más valioso del embudo entero, y
    perderlo en el ruido de los rebotes sería el peor resultado posible acá.
    """
    try:
        msg = email.message_from_string(raw)
    except Exception:  # noqa: BLE001 - un mail mal formado tampoco es un DSN
        return InboundClassification(
            is_dsn=False, is_human_reply=True, bounce=None, verp_tag=None, in_reply_to=None
        )

    bounce = parse_dsn(raw)
    verp_tag = verp_tag_from(msg.get("To", "")) if msg.get("To") else None

    return InboundClassification(
        is_dsn=bounce is not None,
        is_human_reply=bounce is None,
        bounce=bounce,
        verp_tag=verp_tag,
        in_reply_to=msg.get("In-Reply-To"),
    )


def fetch_unseen(
    *, host: str, port: int, username: str, password: str, timeout: float = 30.0
) -> list[str]:
    """Trae el texto crudo de los mensajes no leídos y los marca como
    vistos. Síncrono a propósito — se corre en un hilo (`worker.py`), igual
    que `gtm/send/smtp.py:send`."""
    raw_messages: list[str] = []
    with imaplib.IMAP4_SSL(host, port, timeout=timeout) as client:
        client.login(username, password)
        client.select("INBOX")
        status, data = client.search(None, "UNSEEN")
        if status != "OK":
            return []
        for msg_id in data[0].split():
            status, msg_data = client.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                continue
            raw_messages.append(msg_data[0][1].decode("utf-8", errors="replace"))
    return raw_messages
