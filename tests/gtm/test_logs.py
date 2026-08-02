"""Tests del logging estructurado.

Regresión importante: `logging` reserva atributos del LogRecord (`name`, `module`,
`args`, ...). Pasar uno de esos por `extra=` revienta en runtime, dentro del propio
logger, y tumba la corrida entera desde la línea que supuestamente solo observaba.
"""

from __future__ import annotations

import json
import logging

import pytest

from gtm.factory.logs import JsonFormatter, get_logger


def _record(**extra: object) -> logging.LogRecord:
    logger = logging.getLogger("test.gtm.logs")
    return logger.makeRecord(
        "test.gtm.logs", logging.INFO, __file__, 1, "mensaje", (), None, extra=extra or None
    )


class TestJsonFormatter:
    def test_emite_json_valido(self):
        payload = json.loads(JsonFormatter().format(_record()))
        assert payload["message"] == "mensaje"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "test.gtm.logs"
        assert "ts" in payload

    def test_promueve_los_campos_extra(self):
        payload = json.loads(JsonFormatter().format(_record(event="scored", pain_score=72)))
        assert payload["event"] == "scored"
        assert payload["pain_score"] == 72

    def test_serializa_tipos_no_json(self):
        from pathlib import Path

        payload = json.loads(JsonFormatter().format(_record(target=Path("/tmp/x"))))
        assert payload["target"] == "/tmp/x"

    def test_incluye_la_excepcion(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            logger = logging.getLogger("test.gtm.logs")
            record = logger.makeRecord(
                "test.gtm.logs", logging.ERROR, __file__, 1, "falló", (), sys.exc_info()
            )
        payload = json.loads(JsonFormatter().format(record))
        assert "ValueError: boom" in payload["exception"]


class TestReservedKeys:
    @pytest.mark.parametrize("reserved", ["name", "module", "args", "message", "levelname"])
    def test_las_claves_reservadas_revientan(self, reserved):
        """Documenta la trampa: por eso el pipeline usa `business`, no `name`."""
        with pytest.raises(KeyError):
            _record(**{reserved: "x"})

    def test_las_claves_del_pipeline_son_seguras(self):
        """Todas las claves que el pipeline pasa por `extra=` deben ser válidas."""
        safe = {
            "event": "scored",
            "place_id": "p1",
            "business": "Ramirez Plumbing",
            "pain_score": 72,
            "qualified": True,
            "vertical": "plumber",
            "metro": "Tucson, AZ",
            "pages_fetched": 2,
            "no_website": 4,
            "slug": "x-abc123",
            "bytes": 5083,
            "url": "https://x.example",
            "attempt": 1,
            "max_retries": 4,
            "status": 503,
            "delay_seconds": 1.5,
            "count": 3,
            "dry_run": False,
            "target": "/tmp/public",
            "error": "boom",
            "attempts": 4,
        }
        payload = json.loads(JsonFormatter().format(_record(**safe)))
        for key, value in safe.items():
            assert payload[key] == value


class TestGetLogger:
    def test_no_duplica_handlers(self):
        first = get_logger("test.gtm.idempotent")
        second = get_logger("test.gtm.idempotent")
        assert first is second
        assert len(first.handlers) == 1
