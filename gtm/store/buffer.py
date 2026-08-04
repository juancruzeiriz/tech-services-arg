"""Outbox local: adónde van las filas que no se pudieron escribir en Postgres.

Degradación elegante, no un error: Postgres es el store analítico, no la fuente
de verdad operativa del pipeline (esa sigue siendo `gtm/factory/ledger.py`). Si
la DB está caída, sin configurar, o la red falla a mitad de una corrida, la
corrida tiene que terminar igual — lo que no se pudo escribir se encola acá y se
reintenta después con `python -m gtm.store.backfill`.

Formato: un archivo JSONL, una línea = un "envelope" con todas las filas de una
sola llamada de escritura (no una línea por fila) — así el replay reintenta por
lote, en el mismo tamaño en que se generó.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gtm.factory import config

OUTBOX_PATH = config.BUILD_DIR / "outbox.jsonl"


def spool(table: str, rows: list[dict[str, Any]], *, path: Path | None = None) -> None:
    """Encola un lote de filas para un `table` dado. No hace nada si `rows` está
    vacío -- un envelope vacío no tiene nada que reintentar."""
    if not rows:
        return
    target = path or OUTBOX_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "v": 1,
        "table": table,
        "at": datetime.now(UTC).isoformat(),
        "rows": rows,
    }
    # default=str: las filas pueden traer datetime/UUID: `write_rows` en
    # repo.py las arma como dicts JSON-safe, pero un valor que se cuele sin
    # convertir no debe tumbar el guardado de todo el lote.
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(envelope, ensure_ascii=False, default=str) + "\n")


def read_all(path: Path | None = None) -> list[dict[str, Any]]:
    """Todos los envelopes pendientes, en el orden en que se encolaron."""
    target = path or OUTBOX_PATH
    if not target.exists():
        return []
    envelopes: list[dict[str, Any]] = []
    with open(target, encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                envelopes.append(json.loads(stripped))
    return envelopes


def clear(path: Path | None = None) -> None:
    """Vacía el outbox. Se llama después de un replay exitoso -- nunca antes:
    perder un envelope sin haberlo escrito significaría perder datos de la
    corrida en silencio."""
    target = path or OUTBOX_PATH
    if target.exists():
        target.unlink()


def pending_count(path: Path | None = None) -> int:
    """Cuántos envelopes esperan replay -- para el panel de salud de la UI."""
    return len(read_all(path))
