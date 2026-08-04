"""Lectura y escritura de los artefactos JSON compartidos entre etapas.

Cada etapa del pipeline (`discover` -> `score` -> `generate` -> `deploy` ->
`contact`/`outreach`) se comunica con la siguiente a través de archivos bajo
`gtm/build/data/`, no de objetos en memoria. Antes de este módulo, los 8 stages
abrían esos archivos a mano con `json.load`/`json.dump` casi idénticos repetidos
ocho veces — con cobertura de campos que ya había divergido en algún punto (ver
`from_dict` en `types.py`). Un solo lugar para leer y escribir cada tipo es lo que
permite que la orquestación programática (`gtm/factory/pipeline.py`, usada por la
UI) y la CLI produzcan exactamente los mismos archivos, byte a byte.

Deliberadamente NO absorbe el manejo de `FileNotFoundError`: cada etapa decide si
la ausencia del archivo es un error fatal o un caso a degradar (con su propio
mensaje de log), así que estas funciones dejan pasar la excepción tal cual.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from gtm.factory.types import ContactPlan, Demo, OutreachEmail, PainScore, Prospect


def _write_json(path: str | Path, payload: list[dict[str, object]]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def read_prospects(path: str | Path) -> list[Prospect]:
    with open(path, encoding="utf-8") as handle:
        return [Prospect.from_dict(item) for item in json.load(handle)]


def write_prospects(path: str | Path, prospects: Iterable[Prospect]) -> None:
    _write_json(path, [p.to_dict() for p in prospects])


def read_scores(path: str | Path) -> list[PainScore]:
    with open(path, encoding="utf-8") as handle:
        return [PainScore.from_dict(item) for item in json.load(handle)]


def write_scores(path: str | Path, scores: Iterable[PainScore]) -> None:
    _write_json(path, [s.to_dict() for s in scores])


def read_demos(path: str | Path) -> list[Demo]:
    with open(path, encoding="utf-8") as handle:
        return [Demo.from_dict(item) for item in json.load(handle)]


def write_demos(path: str | Path, demos: Iterable[Demo]) -> None:
    _write_json(path, [d.to_dict() for d in demos])


def read_contacts(path: str | Path) -> list[ContactPlan]:
    with open(path, encoding="utf-8") as handle:
        return [ContactPlan.from_dict(item) for item in json.load(handle)]


def write_contacts(path: str | Path, plans: Iterable[ContactPlan]) -> None:
    _write_json(path, [plan.to_dict() for plan in plans])


def read_emails(path: str | Path) -> list[OutreachEmail]:
    with open(path, encoding="utf-8") as handle:
        return [OutreachEmail.from_dict(item) for item in json.load(handle)]


def write_emails(path: str | Path, emails: Iterable[OutreachEmail]) -> None:
    _write_json(path, [e.to_dict() for e in emails])


def write_queue(path: str | Path, markdown: str) -> None:
    Path(path).write_text(markdown, encoding="utf-8")


def write_meta(path: str | Path, data: dict[str, object]) -> None:
    """Metadatos de la corrida (vertical, metro, idioma...) que ningún otro
    artefacto guarda -- sin esto `RunRegistry.rehydrate` no podría reconstruir
    un `RunContext` a partir de lo que quedó en disco."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def read_meta(path: str | Path) -> dict[str, object]:
    with open(path, encoding="utf-8") as handle:
        result: dict[str, object] = json.load(handle)
        return result
