"""Pantalla de envíos: elegir de la cola de contacto, encolar, ver el estado
de cada mensaje y reintentar los que fallaron.

`phone` y `contact_form` se encolan como `manual_pending`, no `queued`: el
worker (`gtm/send/worker.py`) ignora esos dos canales a propósito, así que
`manual_pending` es lo que le dice al operador "prepará esto y avisá cuando
lo mandes" en vez de dejarlo colgado a la espera de un envío automático que
nunca va a llegar. Sin Postgres (`pool is None`) la pantalla se deshabilita
limpiamente, igual que el resto de `gtm/ui/` -- `gtm/send/outbox.py` necesita
`UPDATE` y `SELECT ... FOR UPDATE SKIP LOCKED`, que un JSONL no puede dar.
"""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gtm.factory.ledger import SuppressionList
from gtm.factory.logs import get_logger
from gtm.send import outbox
from gtm.send.types import OutreachMessage
from gtm.ui.app import templates
from gtm.ui.deps import PoolDep, RegistryDep
from gtm.ui.routes.queue import _queue_items

_logger = get_logger(__name__)

router = APIRouter(prefix="/outbox")


def _item_key(item: dict[str, object]) -> str:
    return f"{item['run_id']}|{item['place_id']}"


async def _status_response(request: Request, pool: PoolDep) -> HTMLResponse:
    messages = await outbox.list_messages(pool) if pool is not None else []
    return templates.TemplateResponse(
        request, "fragments/outbox_table.html", {"messages": messages}
    )


@router.get("", response_class=HTMLResponse)
async def outbox_page(request: Request, registry: RegistryDep, pool: PoolDep) -> HTMLResponse:
    items = _queue_items(registry, None, SuppressionList())
    messages = await outbox.list_messages(pool) if pool is not None else []
    return templates.TemplateResponse(
        request,
        "pages/outbox.html",
        {
            "active": "outbox",
            "items": items,
            "messages": messages,
            "has_pool": pool is not None,
            "item_key": _item_key,
        },
    )


@router.get("/status", response_class=HTMLResponse)
async def outbox_status(request: Request, pool: PoolDep) -> HTMLResponse:
    return await _status_response(request, pool)


@router.post("/enqueue")
async def enqueue_selected(
    registry: RegistryDep,
    pool: PoolDep,
    selected: Annotated[list[str], Form()] = [],  # noqa: B006 - FastAPI Form necesita el default acá
) -> RedirectResponse:
    if pool is None or not selected:
        return RedirectResponse("/outbox", status_code=303)

    by_key = {_item_key(item): item for item in _queue_items(registry, None, SuppressionList())}
    messages: list[OutreachMessage] = []
    for key in selected:
        item = by_key.get(key)
        if item is None:
            continue
        plan = item["plan"]
        messages.append(
            OutreachMessage(
                client_id=str(uuid4()),
                run_id=item["run_id"],
                place_id=item["place_id"],
                channel=plan.channel.value,
                to_address=plan.target,
                body=item["message"],
                max_attempts=1,
            )
        )
    if messages:
        await outbox.enqueue_manual(pool, messages)
    return RedirectResponse("/outbox", status_code=303)


@router.post("/{message_id}/retry")
async def retry_message(message_id: int, pool: PoolDep) -> RedirectResponse:
    if pool is not None:
        message = await outbox.get_by_id(pool, message_id)
        if message is not None:
            try:
                await outbox.requeue(pool, message)
            except ValueError as exc:
                _logger.warning(
                    "no se pudo reintentar el mensaje",
                    extra={"event": "outbox_retry_failed", "message_id": message_id, "error": str(exc)},
                )
    return RedirectResponse("/outbox", status_code=303)


@router.post("/{message_id}/cancel")
async def cancel_message(message_id: int, pool: PoolDep) -> RedirectResponse:
    if pool is not None:
        message = await outbox.get_by_id(pool, message_id)
        if message is not None:
            try:
                await outbox.cancel(pool, message)
            except ValueError as exc:
                _logger.warning(
                    "no se pudo cancelar el mensaje",
                    extra={"event": "outbox_cancel_failed", "message_id": message_id, "error": str(exc)},
                )
    return RedirectResponse("/outbox", status_code=303)


@router.post("/{message_id}/manual-done")
async def manual_done_message(message_id: int, pool: PoolDep) -> RedirectResponse:
    if pool is not None:
        message = await outbox.get_by_id(pool, message_id)
        if message is not None:
            try:
                await outbox.mark_manual_done(pool, message)
            except ValueError as exc:
                _logger.warning(
                    "no se pudo marcar como enviado",
                    extra={"event": "outbox_manual_done_failed", "message_id": message_id, "error": str(exc)},
                )
    return RedirectResponse("/outbox", status_code=303)
