"""Envío SMTP directo a la casilla propia — nunca un ESP de terceros.

Los proveedores de email transaccional evaluados (Resend, Postmark, Amazon
SES, SendGrid...) prohíben outreach en frío en sus propios términos de
servicio (ver `docs/CHANNELS.md`). La casilla propia por SMTP no tiene esa
restricción: es tu buzón, mandando mail como lo haría cualquier persona.

`smtplib.SMTP_SSL` de la stdlib, no `aiosmtplib`: el tope diario recomendado
(`gtm/send/outbox.py:DEFAULT_DAILY_CAP`) es ~20 mensajes, uno cada varios
minutos — no hace falta un cliente async dedicado, y esto evita una
dependencia nueva. `send()` es síncrono a propósito; el worker lo corre en un
hilo (`send_async`, o `asyncio.to_thread` directo) para no bloquear el loop.

El cuerpo del mensaje ya es texto plano (`gtm/factory/outreach.py` nunca
generó HTML): armar `multipart/alternative` acá inventaría una parte HTML
que no existe en ningún lado del pipeline. Texto plano además es mejor señal
de entregabilidad para un mensaje 1:1 en frío que HTML con estilos — parece
lo que es, un mail que escribió una persona.
"""

from __future__ import annotations

import asyncio
import secrets
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

from gtm.factory.types import ComplianceError, SenderIdentity
from gtm.send.types import SendResult, SmtpSettings


def envelope_from(bounce_address: str, verp_tag: str) -> str:
    """El remitente de sobre (`MAIL FROM`) efectivo del mensaje —
    `usuario+tag@dominio`. El rebote llega a `bounce_address` igual (los MTA
    ignoran todo lo que sigue a un "+" en el local-part para el ruteo), pero
    el tag es lo que permite que `gtm/send/bounces.py` empareje ESE rebote
    puntual con ESTE mensaje puntual sin tener que mirar el cuerpo del DSN.
    """
    local, _, domain = bounce_address.partition("@")
    return f"{local}+{verp_tag}@{domain}"


def new_verp_tag() -> str:
    return secrets.token_urlsafe(12)


def build_mime(
    subject: str,
    body: str,
    to_address: str,
    sender: SenderIdentity,
    *,
    message_id: str | None = None,
) -> EmailMessage:
    """Arma el mensaje MIME completo. El contenido (¿cita una métrica real?,
    ¿tiene la dirección postal?, ¿el aviso comercial?) ya se validó en
    `outreach.build_email()` al redactarlo — acá solo se traduce a MIME y se
    agregan los headers de transporte."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender.from_name} <{sender.from_email}>"
    msg["To"] = to_address
    msg["Message-ID"] = message_id or make_msgid()
    msg["List-Unsubscribe"] = f"<{sender.unsubscribe_url}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(body)
    return msg


def revalidate_before_send(body: str, sender: SenderIdentity) -> None:
    """Re-chequea, justo antes de enviar, que el cuerpo YA ESCRITO siga
    conforme con la identidad de remitente ACTUAL — no la que existía cuando
    el mensaje se redactó y se encoló, que puede ser minutos o días antes.

    Deliberadamente más angosto que `outreach.validate_compliance`: acá no
    hace falta reconstruir un `OutreachEmail` completo (`gtm/send` no
    persiste el idioma del mensaje por prospecto), así que solo re-verifica
    los dos elementos cuya AUSENCIA sería un drift real de configuración —
    dirección postal y unsubscribe — no el asunto ni el aviso comercial, que
    no cambian por drift de config y ya se verificaron una vez al redactar.
    """
    if sender.physical_address not in body:
        raise ComplianceError(
            "el cuerpo no incluye la dirección postal física actual del remitente "
            "-- el mensaje se redactó con una configuración distinta a la de ahora"
        )
    if sender.unsubscribe_url not in body:
        raise ComplianceError(
            "el cuerpo no incluye el mecanismo de baja actual del remitente "
            "-- el mensaje se redactó con una configuración distinta a la de ahora"
        )


def send(
    message: EmailMessage,
    *,
    settings: SmtpSettings,
    envelope_sender: str,
    to_address: str,
    timeout: float = 30.0,
) -> SendResult:
    """Envío síncrono real. Se llama desde un hilo (`send_async`), nunca
    directo desde código async: `smtplib` bloquea el hilo durante todo el
    diálogo TLS + SMTP, que puede tardar varios segundos.

    Nunca levanta: un fallo de red o de credenciales es exactamente el tipo
    de error transitorio que `gtm/send/outbox.py:mark_failed` necesita para
    decidir si reintenta, no una excepción que tumbe el worker entero.
    """
    try:
        with smtplib.SMTP_SSL(settings.host, settings.port, timeout=timeout) as client:
            client.login(settings.username, settings.password)
            client.send_message(message, from_addr=envelope_sender, to_addrs=[to_address])
    except smtplib.SMTPException as exc:
        return SendResult(success=False, error=str(exc))
    except OSError as exc:  # timeout, conexión rechazada, resolución DNS
        return SendResult(success=False, error=str(exc))
    return SendResult(success=True, provider_message_id=message["Message-ID"])


async def send_async(
    message: EmailMessage,
    *,
    settings: SmtpSettings,
    envelope_sender: str,
    to_address: str,
    timeout: float = 30.0,
) -> SendResult:
    return await asyncio.to_thread(
        send,
        message,
        settings=settings,
        envelope_sender=envelope_sender,
        to_address=to_address,
        timeout=timeout,
    )
