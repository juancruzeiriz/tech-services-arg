"""Crear corridas, verlas, y el stream de progreso en vivo (SSE).

El POST arma el `RunContext`, registra la corrida y lanza `run_pipeline` como
una tarea de asyncio *no esperada* (`asyncio.ensure_future`, guardada en
`handle.task` para que no la recoja el garbage collector a mitad de camino) —
así la respuesta vuelve al toque y el pipeline sigue corriendo en el mismo
proceso. `GET /runs/{id}/events` es lo que le permite al navegador ver ese
progreso sin sondear.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from gtm.factory import config
from gtm.factory.logs import get_logger
from gtm.factory.pipeline import ProgressEvent, RunContext, RunResult, run_pipeline
from gtm.factory.types import Language
from gtm.store import links, repo
from gtm.ui import presets as presets_mod
from gtm.ui.app import templates
from gtm.ui.deps import PoolDep, ProgressBusDep, RegistryDep

_logger = get_logger(__name__)

router = APIRouter(prefix="/runs")


@router.get("", response_class=HTMLResponse)
async def list_runs(request: Request, registry: RegistryDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "pages/runs_list.html", {"active": "runs", "handles": registry.all()}
    )


@router.post("")
async def create_run(
    registry: RegistryDep,
    pool: PoolDep,
    progress_bus: ProgressBusDep,
    vertical: str = Form(...),
    vertical_other: str = Form(""),
    metro: str = Form(...),
    metro_other: str = Form(""),
    language: str = Form("en"),
    mode: str = Form("simulate"),
    limit: int = Form(20),
    min_reviews: int = Form(50),
    min_rating: float = Form(4.0),
    seed: int = Form(42),
    probe_site: str | None = Form(None),
    publish: str | None = Form(None),
    base_url: str = Form(""),
    concurrency: int = Form(5),
    price_usd: str = Form("950"),
    price_usd_other: str | None = Form(None),
    with_outreach: str | None = Form(None),
    author_name: str = Form(""),
    author_url: str = Form(""),
    save_preset: str | None = Form(None),
    preset_name: str = Form(""),
) -> RedirectResponse:
    if registry.is_busy():
        # Un solo operador no gana nada corriendo dos a la vez -- ver
        # RunRegistry.is_busy. Se vuelve al formulario sin crear la corrida.
        return RedirectResponse("/", status_code=303)

    if save_preset and preset_name.strip():
        presets_mod.save_preset(
            preset_name,
            {
                "vertical": vertical,
                "vertical_other": vertical_other,
                "metro": metro,
                "metro_other": metro_other,
                "language": language,
                "mode": mode,
                "limit": limit,
                "min_reviews": min_reviews,
                "min_rating": min_rating,
                "concurrency": concurrency,
                "price_usd": price_usd,
                "price_usd_other": price_usd_other or "",
                "probe_site": probe_site is not None,
                "publish": publish is not None,
                "base_url": base_url,
            },
        )

    resolved_vertical = (vertical_other.strip() or vertical) if vertical == "__other__" else vertical
    resolved_metro = (metro_other.strip() or metro) if metro == "__other__" else metro

    if price_usd == "__other__" and price_usd_other:
        try:
            resolved_price = int(float(price_usd_other))
        except ValueError:
            resolved_price = 950
    else:
        try:
            resolved_price = int(price_usd)
        except ValueError:
            resolved_price = 950

    sender = None
    if with_outreach:
        try:
            sender = config.load_sender_identity()
        except Exception as exc:  # noqa: BLE001 - se degrada a "sin outreach", no se rompe la corrida
            _logger.warning(
                "remitente inválido, se omite outreach",
                extra={"event": "sender_invalid", "error": str(exc)},
            )

    ctx = RunContext.create(
        resolved_vertical,
        resolved_metro,
        language=Language(language),
        limit=limit,
        min_reviews=min_reviews,
        min_rating=min_rating,
        score_concurrency=concurrency,
        contact_concurrency=concurrency,
        probe_site=probe_site is not None,
        dry_run=publish is None,
        simulated=(mode == "simulate"),
        seed=seed,
        author_name=author_name,
        author_url=author_url,
        base_url=base_url,
        sender=sender,
        offer_price_usd=resolved_price,
    )

    handle = registry.register(ctx)

    async def _execute() -> RunResult | None:
        def emit(event: ProgressEvent) -> None:
            progress_bus.publish(event)

        try:
            result = await run_pipeline(ctx, emit=emit)
        except Exception as exc:  # noqa: BLE001 - se guarda en el handle, no hay quien lo espere
            handle.error = str(exc)
            progress_bus.publish(
                ProgressEvent(run_id=ctx.run_id, stage=None, kind="error", message=str(exc))
            )
            _logger.error(
                "corrida abortada", extra={"event": "run_crashed", "run_id": ctx.run_id, "error": str(exc)}
            )
            return None

        handle.result = result
        progress_bus.publish(
            ProgressEvent(
                run_id=ctx.run_id, stage=None, kind="done", message="ok" if result.ok else "failed"
            )
        )

        try:
            await repo.persist_run(pool, ctx, result)
            tokens = links.mint_links_for_run(ctx, result)
            if tokens:
                await repo.upsert(pool, "demo_links", links.demo_link_rows(ctx, result, tokens))
                handle.tokens = tokens
        except Exception as exc:  # noqa: BLE001 - la corrida ya terminó bien; esto es best-effort
            _logger.warning(
                "no se pudo persistir la corrida",
                extra={"event": "persist_run_failed", "run_id": ctx.run_id, "error": str(exc)},
            )
        return result

    # Referencia guardada en el registro: sin esto el garbage collector puede
    # recoger la tarea a mitad de camino (asyncio lo advierte explícitamente).
    handle.task = asyncio.ensure_future(_execute())
    return RedirectResponse(f"/runs/{ctx.run_id}", status_code=303)


@router.get("/{run_id}", response_class=HTMLResponse)
async def run_detail(request: Request, run_id: str, registry: RegistryDep) -> HTMLResponse:
    handle = registry.get(run_id)
    if handle is None:
        return templates.TemplateResponse(
            request, "pages/run_not_found.html", {"active": "runs", "run_id": run_id}, status_code=404
        )

    scores_by_id: dict[str, int] = {}
    demos_by_id: dict[str, str] = {}
    if handle.result is not None:
        scores_by_id = {s.place_id: s.score for s in handle.result.scores}
        demos_by_id = {d.place_id: d.url for d in handle.result.demos if d.url}

    return templates.TemplateResponse(
        request,
        "pages/run_detail.html",
        {"active": "runs", "handle": handle, "scores_by_id": scores_by_id, "demos_by_id": demos_by_id},
    )


def _event_to_dict(event: ProgressEvent) -> dict[str, Any]:
    return {
        "kind": event.kind,
        "stage": event.stage.value if event.stage else None,
        "index": event.index,
        "total": event.total,
        "message": event.message,
    }


@router.get("/{run_id}/events")
async def run_events(request: Request, run_id: str, progress_bus: ProgressBusDep, registry: RegistryDep) -> StreamingResponse:
    handle = registry.get(run_id)
    if handle is None:
        return StreamingResponse(iter([]), media_type="text/event-stream", status_code=404)

    queue = progress_bus.subscribe(run_id)

    async def event_stream() -> AsyncIterator[str]:
        try:
            if handle.status in ("ok", "failed"):
                # Ya terminó antes de que el navegador llegara a conectarse
                # (corridas simuladas chicas son casi instantáneas).
                yield f"data: {json.dumps({'kind': 'done', 'status': handle.status})}\n\n"
                return
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(_event_to_dict(event))}\n\n"
                if event.kind in ("done", "error"):
                    break
        finally:
            progress_bus.unsubscribe(run_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
