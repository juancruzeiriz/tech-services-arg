"""Cola de contacto: reemplaza a `gtm/build/queue.md`.

Arma el guion/mensaje de cada prospecto accionable (usando el link de
redirección con token si se minó uno — ver `gtm/store/links.py`) y deja
botones para registrar el evento del embudo con un clic, en vez de tipear
`python -m gtm.factory.ledger record --place-id ... --event ...` a mano.

El ledger local (`gtm/suppression.jsonl`, `gtm/funnel.jsonl`) sigue siendo la
fuente de verdad — se escribe siempre, sincrónico, antes de intentar nada con
Postgres. La escritura a Postgres es best-effort: si falla, el clic del
usuario ya quedó registrado igual.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from gtm.factory.contact import build_call_script, build_form_message
from gtm.factory.ledger import FunnelLedger, SuppressionList, hash_key
from gtm.factory.logs import get_logger
from gtm.factory.types import ContactChannel, FunnelEvent, SuppressionReason
from gtm.store import links, repo
from gtm.ui.app import templates
from gtm.ui.deps import PoolDep, RegistryDep
from gtm.ui.registry import RunRegistry

_logger = get_logger(__name__)

router = APIRouter(prefix="/queue")


def _queue_items(
    registry: RunRegistry, run_id: str | None, suppression: SuppressionList
) -> list[dict[str, Any]]:
    """La cola: un item por prospecto accionable con demo, de las corridas
    conocidas (la más reciente primero), sin los que ya están suprimidos."""
    items: list[dict[str, Any]] = []
    handles = registry.all()
    if run_id:
        handles = [h for h in handles if h.ctx.run_id == run_id]

    for handle in handles:
        if handle.result is None:
            continue
        demo_by_id = {d.place_id: d for d in handle.result.demos}
        prospect_by_id = {p.place_id: p for p in handle.result.prospects}

        for plan in handle.result.contacts:
            if not plan.is_actionable:
                continue
            prospect = prospect_by_id.get(plan.place_id)
            demo = demo_by_id.get(plan.place_id)
            if prospect is None or demo is None or not demo.is_live:
                continue
            if suppression.contains(prospect):
                continue

            token = handle.tokens.get(plan.place_id)
            link_url = (
                links.tracked_url(handle.ctx.base_url, token)
                if token and handle.ctx.base_url
                else demo.url
            )

            if plan.channel is ContactChannel.PHONE:
                message = build_call_script(
                    prospect, demo, language=handle.ctx.language, link_url=link_url
                )
            else:
                message = build_form_message(
                    prospect, demo, handle.ctx.author_name,
                    language=handle.ctx.language, link_url=link_url, price_usd=handle.ctx.offer_price_usd,
                )

            items.append(
                {
                    "run_id": handle.ctx.run_id,
                    "place_id": plan.place_id,
                    "prospect": prospect,
                    "plan": plan,
                    "demo": demo,
                    "language": handle.ctx.language.value,
                    "message": message,
                    "link_url": link_url,
                }
            )

    items.sort(key=lambda item: -item["plan"].pain_score)
    return items


@router.get("", response_class=HTMLResponse)
async def queue_page(request: Request, registry: RegistryDep, run_id: str | None = None) -> HTMLResponse:
    items = _queue_items(registry, run_id, SuppressionList())
    return templates.TemplateResponse(
        request, "pages/queue.html", {"active": "queue", "items": items, "run_id": run_id}
    )


async def _persist_funnel_event_best_effort(
    pool: Any, place_id: str, event: FunnelEvent, *, run_id: str, vertical: str, metro: str,
    channel: str, language: str, pain_score: int, amount_usd: float,
) -> None:
    from datetime import UTC, datetime

    row = {
        "place_id_hash": hash_key("place_id", place_id),
        "place_id": place_id,
        "run_id": run_id,
        "event": event.value,
        "level": event.level,
        "at": datetime.now(UTC).isoformat(),
        "vertical": vertical,
        "metro": metro,
        "channel": channel,
        "language": language,
        "pain_score": pain_score,
        "amount_usd": amount_usd,
        "note": "",
    }
    try:
        await repo.upsert(pool, "funnel_events", [row])
    except Exception as exc:  # noqa: BLE001 - el ledger local ya quedó escrito; esto es best-effort
        _logger.warning(
            "no se pudo espejar el evento a Postgres",
            extra={"event": "funnel_event_mirror_failed", "place_id": place_id, "error": str(exc)},
        )


@router.post("/{run_id}/{place_id}/event")
async def record_event(
    run_id: str,
    place_id: str,
    registry: RegistryDep,
    pool: PoolDep,
    event: str = Form(...),
    amount_usd: float = Form(0.0),
) -> RedirectResponse:
    handle = registry.get(run_id)
    plan = None
    if handle is not None and handle.result is not None:
        plan = next((p for p in handle.result.contacts if p.place_id == place_id), None)

    funnel_event = FunnelEvent(event)
    channel = plan.channel.value if plan else ""
    pain_score = plan.pain_score if plan else 0
    vertical = handle.ctx.vertical if handle else ""
    metro = handle.ctx.metro if handle else ""
    language = handle.ctx.language.value if handle else ""

    FunnelLedger().record(
        place_id,
        funnel_event,
        vertical=vertical,
        metro=metro,
        channel=channel,
        language=language,
        run_id=run_id,
        pain_score=pain_score,
        amount_usd=amount_usd,
    )

    if funnel_event is FunnelEvent.PAID:
        SuppressionList().add("place_id", place_id, SuppressionReason.CUSTOMER)

    await _persist_funnel_event_best_effort(
        pool, place_id, funnel_event, run_id=run_id, vertical=vertical, metro=metro,
        channel=channel, language=language, pain_score=pain_score, amount_usd=amount_usd,
    )

    return RedirectResponse(f"/queue?run_id={run_id}", status_code=303)


@router.post("/{run_id}/{place_id}/suppress")
async def suppress_prospect(
    run_id: str,
    place_id: str,
    reason: str = Form(...),
) -> RedirectResponse:
    SuppressionList().add("place_id", place_id, SuppressionReason(reason))
    return RedirectResponse(f"/queue?run_id={run_id}", status_code=303)
