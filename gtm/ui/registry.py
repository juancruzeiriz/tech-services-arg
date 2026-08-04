"""Registro de corridas en memoria y el bus de eventos de progreso (SSE).

Todo vive en memoria del proceso — reiniciar la UI pierde el estado de
corridas pasadas. Aceptable: esto es un panel local de un solo operador, no un
servicio que tenga que sobrevivir un restart. Lo que sí sobrevive es lo que ya
quedó escrito en disco (`gtm/build/runs/<run_id>/`) y en Postgres.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime

from gtm.factory.pipeline import ProgressEvent, RunContext, RunResult


@dataclass
class RunHandle:
    """Lo que la UI sabe de una corrida: su contexto, la tarea async que la
    está corriendo (o corrió), y el resultado o error una vez que termina."""

    ctx: RunContext
    task: asyncio.Task[RunResult | None] | None = None
    result: RunResult | None = None
    error: str | None = None
    registered_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    tokens: dict[str, str] = field(default_factory=dict)
    """place_id -> token de redirección (`gtm/store/links.py`), minados al
    terminar la corrida. En memoria además de en Postgres/outbox: la cola de
    contacto (`/queue`) tiene que poder armar los links aunque no haya DB."""

    @property
    def status(self) -> str:
        """"pending" | "running" | "ok" | "failed" — lo que la UI pinta como badge."""
        if self.result is not None:
            return "ok" if self.result.ok else "failed"
        if self.error is not None:
            return "failed"
        if self.task is not None and not self.task.done():
            return "running"
        return "pending"


class RunRegistry:
    """Corridas conocidas por la UI, en memoria. Un solo operador no gana nada
    corriendo dos pipelines a la vez, y sí se arriesga a confundir cuál cola de
    contacto le pertenece a cuál corrida — por eso el límite de concurrencia
    se hace cumplir acá, no en `run_pipeline` (que no sabe nada de la UI)."""

    def __init__(self) -> None:
        self._runs: dict[str, RunHandle] = {}

    def register(self, ctx: RunContext) -> RunHandle:
        handle = RunHandle(ctx=ctx)
        self._runs[ctx.run_id] = handle
        return handle

    def get(self, run_id: str) -> RunHandle | None:
        return self._runs.get(run_id)

    def all(self) -> list[RunHandle]:
        """Más reciente primero. Por orden de inserción del dict (Python 3.7+
        lo garantiza), no por `registered_at`: dos corridas registradas en el
        mismo tick de reloj no tienen por qué desempatar en orden de llegada
        si se ordena por timestamp."""
        return list(reversed(self._runs.values()))

    def is_busy(self) -> bool:
        return any(h.status == "running" for h in self._runs.values())


class ProgressBus:
    """Fan-out de `ProgressEvent` a N suscriptores (pestañas SSE abiertas) por
    `run_id`. Cada suscriptor tiene su propia cola: uno lento en consumir no
    bloquea a los demás ni al pipeline — `publish()` nunca espera, por eso
    `run_pipeline` puede llamarlo desde un callback sincrónico."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[ProgressEvent]]] = {}

    def publish(self, event: ProgressEvent) -> None:
        for queue in self._subscribers.get(event.run_id, []):
            queue.put_nowait(event)

    def subscribe(self, run_id: str) -> asyncio.Queue[ProgressEvent]:
        queue: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        self._subscribers.setdefault(run_id, []).append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[ProgressEvent]) -> None:
        subscribers = self._subscribers.get(run_id, [])
        if queue in subscribers:
            subscribers.remove(queue)
        if not subscribers:
            self._subscribers.pop(run_id, None)
