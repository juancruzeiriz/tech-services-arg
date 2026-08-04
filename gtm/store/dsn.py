"""Resuelve el DSN de Postgres desde el entorno.

Separado de `gtm/factory/config.py` a propósito: la UI necesita poder consultar
el estado del store (dashboards de solo lectura, healthcheck) sin arrastrar el
`load_dotenv`/`require_env` orientado a las 8 etapas del pipeline de
prospección — son dos superficies de configuración distintas.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
_loaded = False


def _ensure_env_loaded() -> None:
    global _loaded
    if not _loaded:
        load_dotenv(_ROOT / ".env.personal")
        _loaded = True


def get_dsn() -> str | None:
    """El DSN de Postgres, o `None` si no está configurado.

    Nunca levanta: la ausencia de DB es un estado válido de la aplicación, no un
    error — ver `gtm/store/buffer.py` para la degradación elegante que depende
    de esto.
    """
    _ensure_env_loaded()
    value = os.getenv("SUPABASE_DB_URL", "").strip()
    return value or None


def is_pooler_dsn(dsn: str) -> bool:
    """True si el DSN apunta al pooler de transacción de Supabase (puerto 6543).

    Puramente informativo hoy — nada cambia de comportamiento — pero es la
    primera pregunta que hay que hacerse si aparece un error de "prepared
    statement does not exist": el modo transacción del pooler no soporta
    statements preparados del lado del server.
    """
    return ":6543" in dsn
