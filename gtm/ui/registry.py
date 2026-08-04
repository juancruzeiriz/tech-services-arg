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
from pathlib import Path

from gtm.factory import artifacts
from gtm.factory.logs import get_logger
from gtm.factory.pipeline import ProgressEvent, RunContext, RunResult
from gtm.factory.types import Language

_logger = get_logger(__name__)


def _meta_str(meta: dict[str, object], key: str, default: str) -> str:
    value = meta.get(key, default)
    return str(value) if value is not None else default


def _meta_int(meta: dict[str, object], key: str, default: int) -> int:
    value = meta.get(key, default)
    return int(value) if isinstance(value, int | float | str) else default


def _meta_float(meta: dict[str, object], key: str, default: float) -> float:
    value = meta.get(key, default)
    return float(value) if isinstance(value, int | float | str) else default


def _meta_bool(meta: dict[str, object], key: str, default: bool) -> bool:
    value = meta.get(key, default)
    return bool(value) if isinstance(value, bool | int) else default


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

    def rehydrate(self, build_dir: Path) -> None:
        """Reconstruye corridas terminadas leyendo `gtm/build/runs/*/data/` --
        sin esto, reiniciar `uvicorn` vacía `/queue` aunque los artefactos y
        Postgres tengan todo. Corridas sin `meta.json` (versiones del pipeline
        previas a esta función, o corridas a medio escribir) se saltean: no
        hay forma de reconstruir su `RunContext` sin esos datos.
        """
        runs_dir = build_dir / "runs"
        if not runs_dir.is_dir():
            return

        run_paths = sorted(
            (p for p in runs_dir.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
        )
        for run_path in run_paths:
            if run_path.name in self._runs:
                continue
            handle = self._rehydrate_one(run_path, runs_dir)
            if handle is not None:
                self._runs[run_path.name] = handle

    def _rehydrate_one(self, run_path: Path, runs_dir: Path) -> RunHandle | None:
        data_dir = run_path / "data"
        meta_path = data_dir / "meta.json"
        if not meta_path.exists():
            return None
        try:
            meta = artifacts.read_meta(meta_path)
            ctx = RunContext.create(
                _meta_str(meta, "vertical", ""),
                _meta_str(meta, "metro", ""),
                run_id=run_path.name,
                root=runs_dir,
                language=Language(_meta_str(meta, "language", "en")),
                limit=_meta_int(meta, "limit", 20),
                min_reviews=_meta_int(meta, "min_reviews", 50),
                min_rating=_meta_float(meta, "min_rating", 4.0),
                score_concurrency=_meta_int(meta, "score_concurrency", 5),
                contact_concurrency=_meta_int(meta, "contact_concurrency", 8),
                probe_site=_meta_bool(meta, "probe_site", True),
                dry_run=_meta_bool(meta, "dry_run", True),
                simulated=_meta_bool(meta, "simulated", True),
                seed=_meta_int(meta, "seed", 42),
                author_name=_meta_str(meta, "author_name", ""),
                author_url=_meta_str(meta, "author_url", ""),
                base_url=_meta_str(meta, "base_url", ""),
                offer_price_usd=_meta_int(meta, "offer_price_usd", 950),
            )
            prospects = (
                artifacts.read_prospects(data_dir / "prospects.json")
                if (data_dir / "prospects.json").exists()
                else []
            )
            scores = (
                artifacts.read_scores(data_dir / "scores.json")
                if (data_dir / "scores.json").exists()
                else []
            )
            demos = (
                artifacts.read_demos(data_dir / "demos.json") if (data_dir / "demos.json").exists() else []
            )
            contacts = (
                artifacts.read_contacts(data_dir / "contacts.json")
                if (data_dir / "contacts.json").exists()
                else []
            )
            emails = (
                artifacts.read_emails(data_dir / "emails.json")
                if (data_dir / "emails.json").exists()
                else []
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            _logger.warning(
                "no se pudo rehidratar la corrida",
                extra={"event": "run_rehydrate_failed", "run_id": run_path.name, "error": str(exc)},
            )
            return None

        result = RunResult(
            ctx,
            stages=(),
            prospects=tuple(prospects),
            scores=tuple(scores),
            demos=tuple(demos),
            contacts=tuple(contacts),
            emails=tuple(emails),
        )
        return RunHandle(ctx=ctx, result=result)


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
