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
import sys
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


def _ensure_utf8_console() -> None:
    """En Windows, cuando stdout/stderr no son una consola real —entubados,
    redirigidos, o corridos por un harness que los captura, que es exactamente
    cómo se ejecutan estos comandos en CI y en muchos entornos de desarrollo—
    Python cae al codepage ANSI del sistema (cp1252 en una instalación en
    español/inglés de Windows) en vez de UTF-8. Un `print()` con cualquier
    caracter no ASCII —el ✓ y el ★ que ya usa la CLI, o el texto en español
    ahora que el pipeline es bilingüe— revienta con `UnicodeEncodeError` en ese
    caso, y a diferencia del logger (que atrapa errores de `emit`), un `print()`
    sin capturar tumba el proceso entero.

    Se corre acá, no en cada `main()`: `config` es el primer import común a los
    8 stages, así que alcanza con una sola vez.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure") and stream.encoding not in ("utf-8", "UTF-8"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # Streams reemplazados por el entorno de test (pytest los captura con
            # su propio proxy) pueden no soportar reconfigure; no vale la pena
            # que la importación de config.py falle por esto.
            pass


_ensure_utf8_console()

load_dotenv(ROOT / ".env.personal")

# Variables por grupo, para que check_config() y reload_env() no dupliquen la lista.
_PLACES_VARS = ("GOOGLE_PLACES_API_KEY",)
_SENDER_VARS = ("GTM_FROM_NAME", "GTM_FROM_EMAIL", "GTM_PHYSICAL_ADDRESS", "GTM_UNSUBSCRIBE_URL")
_DEMO_BASE_URL_VARS = ("GTM_DEMO_BASE_URL",)


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


def check_config(
    *,
    need_places: bool = True,
    need_sender: bool = True,
    need_demo_base_url: bool = False,
) -> list[str]:
    """Nombres de variables de entorno faltantes, sin levantar nunca.

    `require_env` está bien para el CLI —falla ruidosamente en el momento en que
    hace falta el valor— pero es lo peor posible para un preflight de UI, que
    necesita mostrar TODO lo que falta de una sola vez, no una por una a los
    ponchazos de re-enviar el formulario.
    """
    wanted: list[str] = []
    if need_places:
        wanted += _PLACES_VARS
    if need_sender:
        wanted += _SENDER_VARS
    if need_demo_base_url:
        wanted += _DEMO_BASE_URL_VARS
    return [name for name in wanted if not optional_env(name)]


def reload_env() -> None:
    """Vuelve a leer `.env.personal`. `load_dotenv` corre una vez al importar el
    módulo; sin esto, editar credenciales desde la UI exigiría reiniciar el proceso
    para que se noten."""
    load_dotenv(ROOT / ".env.personal", override=True)


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
