"""Configuración y rutas del pipeline. Ningún secreto vive en el código.

Variables de entorno (cargadas desde `.env.personal` en la raíz del repo):

    GOOGLE_PLACES_API_KEY   Requerida por `discover`. Places API (New).
    PAGESPEED_API_KEY       Opcional en `score`. Sin key hay cuota reducida.
    GTM_FROM_NAME           Remitente real (CAN-SPAM).
    GTM_FROM_EMAIL          Email de respuesta real y monitoreado (CAN-SPAM).
    GTM_PHYSICAL_ADDRESS    Dirección postal física (CAN-SPAM, obligatoria).
    GTM_UNSUBSCRIBE_URL     URL o mailto de baja (CAN-SPAM, obligatoria).
    GTM_DEMO_BASE_URL       Base pública donde se sirven las demos.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from gtm.factory.types import GTMError, SenderIdentity

ROOT = Path(__file__).resolve().parents[2]
GTM_DIR = ROOT / "gtm"
TEMPLATE_DIR = GTM_DIR / "template"

# Artefactos generados. Fuera de git: son datos de prospectos, no código.
BUILD_DIR = GTM_DIR / "build"
DEMOS_DIR = BUILD_DIR / "demos"
DATA_DIR = BUILD_DIR / "data"

load_dotenv(ROOT / ".env.personal")


class MissingConfigError(GTMError):
    """Falta una variable de entorno obligatoria."""


def require_env(name: str) -> str:
    """Lee una env var obligatoria o falla con un mensaje accionable."""
    value = os.getenv(name, "").strip()
    if not value:
        raise MissingConfigError(
            f"Falta {name}. Definila en .env.personal o en los secrets del workflow."
        )
    return value


def optional_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def demo_base_url() -> str:
    """Base pública de las demos, sin barra final."""
    return require_env("GTM_DEMO_BASE_URL").rstrip("/")


def load_sender_identity() -> SenderIdentity:
    """Construye y valida la identidad del remitente.

    Valida acá, en el borde del sistema, para que un email no conforme no llegue a
    existir: una multa de CAN-SPAM se cuenta por mensaje enviado.
    """
    sender = SenderIdentity(
        from_name=require_env("GTM_FROM_NAME"),
        from_email=require_env("GTM_FROM_EMAIL"),
        physical_address=require_env("GTM_PHYSICAL_ADDRESS"),
        unsubscribe_url=require_env("GTM_UNSUBSCRIBE_URL"),
    )
    sender.validate()
    return sender


def ensure_dirs() -> None:
    """Crea los directorios de build. Idempotente."""
    for directory in (BUILD_DIR, DEMOS_DIR, DATA_DIR):
        directory.mkdir(parents=True, exist_ok=True)
