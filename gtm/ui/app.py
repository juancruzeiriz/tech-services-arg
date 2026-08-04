"""FastAPI app: arma el server, monta static, registra rutas.

`create_app()` es una factory, no un objeto a nivel de módulo — así
`gtm/ui/__main__.py` se lo pasa a uvicorn como string
(`"gtm.ui.app:create_app"`, `factory=True`) y los tests pueden crear una
instancia fresca por test sin compartir el pool ni el registro de corridas.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from gtm.factory import config
from gtm.factory.logs import get_logger
from gtm.send.worker import start_worker
from gtm.store.pool import close_pool, open_pool
from gtm.ui.registry import ProgressBus, RunRegistry

_logger = get_logger(__name__)

_UI_DIR = Path(__file__).resolve().parent
STATIC_DIR = _UI_DIR / "static"
TEMPLATES_DIR = _UI_DIR / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["thousands"] = lambda n: f"{int(n):,}".replace(",", ".")
templates.env.filters["pct"] = lambda x: f"{x * 100:.1f}%".replace(".0%", "%")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.pool = await open_pool()
    app.state.registry = RunRegistry()
    app.state.registry.rehydrate(config.BUILD_DIR)
    app.state.progress_bus = ProgressBus()
    # None sin pool: el envío automático queda deshabilitado limpiamente,
    # igual que el resto de gtm/store/ cuando no hay Postgres -- la cola
    # manual (/queue) sigue funcionando exactamente igual que siempre.
    app.state.worker = start_worker(app.state.pool, daily_cap=config.daily_send_cap())
    try:
        yield
    finally:
        if app.state.worker is not None:
            await app.state.worker.stop()
        await close_pool(app.state.pool)


def create_app() -> FastAPI:
    app = FastAPI(title="GTM — panel de prospección", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Import diferido: evita que gtm.ui.routes.* tenga que importar gtm.ui.app
    # (que las registra) antes de que create_app() termine de definirse.
    from gtm.ui.routes import costs, dashboard, outbox, pages, queue, runs, time_log

    app.include_router(pages.router)
    app.include_router(runs.router)
    app.include_router(queue.router)
    app.include_router(outbox.router)
    app.include_router(time_log.router)
    app.include_router(costs.router)
    app.include_router(dashboard.router)

    return app
