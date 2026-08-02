"""Logging estructurado en JSON para el pipeline de prospección.

Una línea = un objeto JSON. Permite `jq` sobre los logs de GitHub Actions sin parsear
texto libre, que es como se depuran las corridas que fallan a las 3 AM sin nadie mirando.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Serializa cada LogRecord como una línea JSON, incluyendo campos `extra`."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Cualquier kwarg pasado por `extra=` se promueve a campo de primer nivel.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Devuelve un logger con salida JSON a stderr.

    Idempotente: llamarlo dos veces con el mismo nombre no duplica handlers ni,
    por lo tanto, líneas de log.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(level)
    return logger
