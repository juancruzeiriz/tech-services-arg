"""Tests de `gtm/ui/routes/time_log.py`.

Sin conexión a Postgres (no hay `SUPABASE_DB_URL` en estos tests), así que lo
que se verifica es que el endpoint no rompe con `pool=None` -- la escritura
real a la tabla `time_log` ya está probada en `test_store_repo.py`."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gtm.ui.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    from gtm.factory import config as config_mod

    monkeypatch.setattr(config_mod, "BUILD_DIR", tmp_path / "build")
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    with TestClient(create_app()) as test_client:
        yield test_client


class TestSaveTimeLog:
    def test_redirige_a_donde_se_le_pida(self, client):
        response = client.post(
            "/time-log",
            data={"minutes": "30", "activity": "llamadas", "redirect_to": "/queue?run_id=abc"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/queue?run_id=abc"

    def test_cero_minutos_no_rompe(self, client):
        """0 no es una sesión real -- no debe intentar escribir nada, pero
        tampoco debe fallar la request."""
        response = client.post(
            "/time-log", data={"minutes": "0", "redirect_to": "/queue"}, follow_redirects=False
        )
        assert response.status_code == 303

    def test_sin_pool_no_rompe(self, client):
        """El pool es None en este test (sin SUPABASE_DB_URL) -- el endpoint
        tiene que degradar al outbox, no devolver un 500."""
        response = client.post(
            "/time-log", data={"minutes": "15", "redirect_to": "/queue"}, follow_redirects=False
        )
        assert response.status_code == 303
