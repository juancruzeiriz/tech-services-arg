"""Rutas de solo lectura: home (placeholder hasta la tarea del formulario),
configuración/salud del entorno, y la página de docs (resumen de la oferta,
el pipeline, el público objetivo y el speech de venta). Crear una corrida, ver
su detalle y el SSE de progreso viven en `gtm/ui/routes/runs.py`."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from gtm.catalog import metros, trades
from gtm.factory import config
from gtm.store import buffer
from gtm.ui import presets as presets_mod
from gtm.ui.app import templates
from gtm.ui.deps import PoolDep, RegistryDep

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, registry: RegistryDep, preset: str = "") -> HTMLResponse:
    loaded_preset = presets_mod.get_preset(preset) if preset else None
    return templates.TemplateResponse(
        request,
        "pages/home.html",
        {
            "active": "new_run",
            "trades": trades(),
            "metros": metros(),
            "busy": registry.is_busy(),
            "missing_places": config.check_config(need_places=True, need_sender=False),
            "missing_sender": config.check_config(need_places=False, need_sender=True),
            "mode_default": "simulate",
            "base_url_default": config.optional_env("GTM_DEMO_BASE_URL"),
            "author_name_default": config.optional_env("GTM_FROM_NAME"),
            "author_url_default": (
                config.optional_env("GTM_AUTHOR_URL")
                or config.optional_env("GTM_UNSUBSCRIBE_URL")
            ),
            "preset_names": presets_mod.list_presets(),
            "preset": loaded_preset or {},
            "preset_loaded_name": preset if loaded_preset else "",
        },
    )


@router.get("/docs", response_class=HTMLResponse)
async def docs_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "pages/docs.html",
        {"active": "docs", "trade_count": len(trades()), "metro_count": len(metros())},
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, pool: PoolDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "pages/settings.html",
        {
            "active": "settings",
            "db_connected": pool is not None,
            "missing_places": config.check_config(need_places=True, need_sender=False),
            "missing_sender": config.check_config(need_places=False, need_sender=True),
            "missing_demo_base": config.check_config(
                need_places=False, need_sender=False, need_demo_base_url=True
            ),
            "outbox_pending": buffer.pending_count(),
        },
    )
