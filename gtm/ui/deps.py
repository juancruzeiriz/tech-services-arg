"""Dependencias compartidas de FastAPI.

El pool de Postgres se abre una vez en el lifespan de `gtm/ui/app.py`, nunca
por request — estas funciones solo lo leen de `request.app.state`.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request
from psycopg_pool import AsyncConnectionPool

from gtm.factory.pipeline import RunContext
from gtm.ui.registry import ProgressBus, RunRegistry


def get_pool(request: Request) -> AsyncConnectionPool | None:
    """`None` es un estado válido: sin `SUPABASE_DB_URL` configurada, o si
    Postgres no respondió al arrancar — la UI sigue funcionando igual, todo lo
    que se hubiera escrito queda en el outbox local (`gtm/store/buffer.py`)."""
    return cast("AsyncConnectionPool | None", request.app.state.pool)


def get_registry(request: Request) -> RunRegistry:
    return cast(RunRegistry, request.app.state.registry)


def get_progress_bus(request: Request) -> ProgressBus:
    return cast(ProgressBus, request.app.state.progress_bus)


PoolDep = Annotated[AsyncConnectionPool | None, Depends(get_pool)]
RegistryDep = Annotated[RunRegistry, Depends(get_registry)]
ProgressBusDep = Annotated[ProgressBus, Depends(get_progress_bus)]

__all__ = ["PoolDep", "ProgressBusDep", "RegistryDep", "RunContext"]
