"""Presets de corrida: configuraciones con nombre para no volver a elegir los
15 parámetros cada vez que se quiere repetir (o casi repetir) una corrida.

Archivo JSON local (`gtm/build/presets.json`), no Postgres: son conveniencia
de la UI, no datos de negocio, y tienen que funcionar aunque no haya
`SUPABASE_DB_URL` configurada — el mismo criterio que ya usa el outbox.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gtm.factory import config

PRESETS_PATH = config.BUILD_DIR / "presets.json"

# Campos del formulario que tiene sentido guardar. No se guarda el nombre del
# autor/URL ni el remitente: eso ya vive en .env.personal y no varía por preset.
_FIELDS = (
    "vertical", "vertical_other", "metro", "metro_other", "language", "mode",
    "limit", "min_reviews", "min_rating", "concurrency", "price_usd", "price_usd_other",
    "probe_site", "publish", "base_url",
)


def _read_all(path: Path | None = None) -> dict[str, dict[str, Any]]:
    target = path or PRESETS_PATH
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_all(presets: dict[str, dict[str, Any]], path: Path | None = None) -> None:
    target = path or PRESETS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")


def list_presets(path: Path | None = None) -> list[str]:
    return sorted(_read_all(path))


def get_preset(name: str, path: Path | None = None) -> dict[str, Any] | None:
    return _read_all(path).get(name)


def save_preset(name: str, form_values: dict[str, Any], path: Path | None = None) -> None:
    """Guarda solo los campos conocidos de `form_values` -- lo que venga de
    más (tokens CSRF, campos nuevos del form que todavía no se agregaron acá)
    no ensucia el preset."""
    name = name.strip()
    if not name:
        return
    presets = _read_all(path)
    presets[name] = {field: form_values[field] for field in _FIELDS if field in form_values}
    _write_all(presets, path)


def delete_preset(name: str, path: Path | None = None) -> None:
    presets = _read_all(path)
    presets.pop(name, None)
    _write_all(presets, path)
