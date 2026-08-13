"""Configuración y rutas del pipeline. Ningún secreto vive en el código.

Variables de entorno (cargadas desde `.env.personal` en la raíz del repo):

    GOOGLE_PLACES_API_KEY   Requerida por `discover`. Places API (New).
    PAGESPEED_API_KEY       Opcional en `score`. Sin key hay cuota reducida.
    CRUX_API_KEY            Opcional en `score`, para datos de campo (Chrome UX
                             Report). Si falta, cae a PAGESPEED_API_KEY: es el
                             mismo proyecto de Google Cloud el que habilita las dos APIs.
    GTM_SEARCH_API_KEY      Opcional en `score`. Habilita la sub-capa B de
                             gtm.factory.verify (Google Programmable Search / Custom
                             Search JSON API): confirma con una búsqueda general si un
                             prospecto sin sitio en Maps de verdad no tiene dominio
                             propio. Sin key, esa sub-capa se salta (degrada a
                             UNVERIFIED); la sub-capa A (gratis) sigue corriendo igual.
    GTM_SEARCH_CX           Opcional en `score`. ID del Programmable Search Engine
                             (motor "Search the entire web") asociado a GTM_SEARCH_API_KEY.
    GTM_SMTP_HOST           Requerida por `gtm.send` para enviar de verdad.
    GTM_SMTP_PORT           Puerto SMTP sobre TLS implícito (default 465).
    GTM_SMTP_USER           Usuario de la casilla de envío.
    GTM_SMTP_PASSWORD       Contraseña o app password de la casilla de envío.
    GTM_BOUNCE_ADDRESS      Casilla que recibe los rebotes (VERP y lectura IMAP).
    GTM_IMAP_HOST           Requerida por `gtm.send.bounces`. IMAP y SMTP suelen
                             vivir en subdominios distintos del mismo proveedor.
    GTM_IMAP_PORT           Puerto IMAP sobre TLS implícito (default 993).
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
from gtm.send.types import DEFAULT_DAILY_CAP, ImapSettings, SmtpSettings

ROOT = Path(__file__).resolve().parents[2]
GTM_DIR = ROOT / "gtm"
TEMPLATE_DIR = GTM_DIR / "template"

# Assets compartidos por todas las demos (fotos por oficio, fuentes). A diferencia
# de BUILD_DIR, esto SÍ va en git: son insumos del producto, no datos de prospectos.
# `deploy.py` los copia una sola vez a <public>/assets/, así las 22 demos referencian
# los mismos archivos y el navegador los descarga una vez, no una por demo.
ASSETS_DIR = GTM_DIR / "assets"
PHOTOS_DIR = ASSETS_DIR / "photos"

# Artefactos generados. Fuera de git: son datos de prospectos, no código.
BUILD_DIR = GTM_DIR / "build"
DEMOS_DIR = BUILD_DIR / "demos"
DATA_DIR = BUILD_DIR / "data"

# Informes de auditoría (gtm/factory/audit.py). Directorio propio, separado de
# DEMOS_DIR: a diferencia de las demos, estos informes nunca pasan por
# deploy.py ni terminan en gtm/public/ -- son material interno para la
# llamada, no un artefacto que se le manda al prospecto.
AUDITS_DIR = BUILD_DIR / "audits"


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
_SMTP_VARS = ("GTM_SMTP_HOST", "GTM_SMTP_USER", "GTM_SMTP_PASSWORD", "GTM_BOUNCE_ADDRESS")
_IMAP_VARS = ("GTM_IMAP_HOST",)


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
    need_smtp: bool = False,
    need_imap: bool = False,
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
    if need_smtp:
        wanted += _SMTP_VARS
    if need_imap:
        wanted += _IMAP_VARS
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


def load_smtp_settings() -> SmtpSettings:
    """Construye la config SMTP, o falla ruidosamente si falta algo -- igual
    que `load_sender_identity`, ver ese docstring para el porqué."""
    return SmtpSettings(
        host=require_env("GTM_SMTP_HOST"),
        port=int(optional_env("GTM_SMTP_PORT", "465")),
        username=require_env("GTM_SMTP_USER"),
        password=require_env("GTM_SMTP_PASSWORD"),
        bounce_address=require_env("GTM_BOUNCE_ADDRESS"),
    )


def load_imap_settings() -> ImapSettings:
    """Mismas credenciales que `load_smtp_settings` (es la misma casilla),
    host/puerto propios porque IMAP y SMTP suelen vivir en subdominios
    distintos del mismo proveedor."""
    return ImapSettings(
        host=require_env("GTM_IMAP_HOST"),
        port=int(optional_env("GTM_IMAP_PORT", "993")),
        username=require_env("GTM_SMTP_USER"),
        password=require_env("GTM_SMTP_PASSWORD"),
    )


def daily_send_cap() -> int:
    """Tope de mensajes por día que el worker (`gtm/send/worker.py`) puede
    mandar. Configurable porque lo correcto depende de cuántos días lleva
    calentando la casilla — ver docs/CHANNELS.md."""
    return int(optional_env("GTM_DAILY_SEND_CAP", str(DEFAULT_DAILY_CAP)))


def ensure_dirs() -> None:
    """Crea los directorios de build. Idempotente."""
    for directory in (BUILD_DIR, DEMOS_DIR, DATA_DIR, AUDITS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
