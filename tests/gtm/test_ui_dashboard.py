"""Tests de `gtm/ui/routes/dashboard.py` -- el embudo lee `gtm/funnel.jsonl`
(aislado a `tmp_path`, igual que en `test_ui_queue.py`), no Postgres."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gtm.factory.types import ContactChannel, FunnelEvent, Language
from gtm.ui.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    from gtm.factory import config as config_mod
    from gtm.factory import ledger as ledger_mod

    monkeypatch.setattr(config_mod, "BUILD_DIR", tmp_path / "build")
    monkeypatch.setattr(config_mod, "DEMOS_DIR", tmp_path / "build" / "demos")
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path / "build" / "data")
    monkeypatch.setattr(ledger_mod, "FUNNEL_PATH", tmp_path / "funnel.jsonl")
    monkeypatch.setattr(ledger_mod, "SUPPRESSION_PATH", tmp_path / "suppression.jsonl")
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)

    with TestClient(create_app()) as test_client:
        yield test_client


def _record(client, *events):
    from gtm.factory import ledger as ledger_mod

    ledger = ledger_mod.FunnelLedger()
    for place_id, event, kwargs in events:
        ledger.record(place_id, event, **kwargs)


def _wait_for_run(client, run_id: str, timeout: float = 5.0):
    """Ver `test_ui_queue.py`: `TestClient` no avanza la tarea de fondo del
    pipeline por su cuenta -- un GET liviano entre reintentos le da al loop
    compartido la chance de terminarla."""
    import time

    deadline = time.monotonic() + timeout
    handle = client.app.state.registry.get(run_id)
    while time.monotonic() < deadline:
        if handle.result is not None or handle.error is not None:
            return handle
        client.get("/settings")
        time.sleep(0.02)
    raise TimeoutError(f"la corrida {run_id} no terminó dentro de {timeout}s")


def _create_simulated_run(client, **overrides) -> str:
    data = {
        "vertical": "hvac",
        "vertical_other": "",
        "metro": "tucson-az",
        "metro_other": "",
        "language": "es",
        "mode": "simulate",
        "limit": "6",
        "min_reviews": "50",
        "min_rating": "4.0",
        "seed": "1",
        "concurrency": "5",
        "price_usd": "950",
        "base_url": "https://demos.example.com",
        "author_name": "Test",
        "author_url": "https://example.com",
    }
    data.update(overrides)
    response = client.post("/runs", data=data, follow_redirects=False)
    run_id = response.headers["location"].removeprefix("/runs/")
    handle = _wait_for_run(client, run_id)
    assert handle.result is not None, f"la corrida simulada terminó con error: {handle.error}"
    return run_id


class TestFunnelDashboardEmpty:
    def test_sin_datos_muestra_estado_vacio(self, client):
        response = client.get("/dashboard/funnel")
        assert response.status_code == 200
        assert "Todavía no hay datos" in response.text


class TestFunnelDashboardConDatos:
    def test_cuenta_contactados_y_pagos(self, client):
        _record(
            client,
            ("a", FunnelEvent.CONTACTED, {"vertical": "hvac"}),
            ("b", FunnelEvent.CONTACTED, {"vertical": "hvac"}),
            ("a", FunnelEvent.REPLIED, {"vertical": "hvac"}),
            ("a", FunnelEvent.PAID, {"vertical": "hvac", "amount_usd": 950}),
        )
        response = client.get("/dashboard/funnel")
        assert response.status_code == 200
        assert "GANADOR" in response.text

    def test_filtra_por_vertical_en_la_url(self, client):
        _record(
            client,
            ("a", FunnelEvent.CONTACTED, {"vertical": "hvac"}),
            ("b", FunnelEvent.CONTACTED, {"vertical": "plumber"}),
        )
        response = client.get("/dashboard/funnel?vertical=hvac")
        assert response.status_code == 200
        assert "Todavía no hay datos" not in response.text

        response_plumber_only = client.get("/dashboard/funnel?vertical=roofer")
        assert "Todavía no hay datos" in response_plumber_only.text

    def test_filtra_por_canal_e_idioma(self, client):
        _record(
            client,
            ("a", FunnelEvent.CONTACTED, {"channel": ContactChannel.PHONE, "language": Language.ES}),
        )
        response = client.get("/dashboard/funnel?channel=phone&language=es")
        assert "Todavía no hay datos" not in response.text

        response_miss = client.get("/dashboard/funnel?channel=contact_form")
        assert "Todavía no hay datos" in response_miss.text

    def test_kill_se_muestra_cuando_se_dispara(self, client):
        for i in range(200):
            _record(client, (f"p{i}", FunnelEvent.CONTACTED, {}))
        for i in range(4):
            _record(client, (f"p{i}", FunnelEvent.REPLIED, {}))
        response = client.get("/dashboard/funnel")
        assert "KILL" in response.text

    def test_muestra_faltantes_para_calibracion_sin_horas_cargadas(self, client):
        _record(client, ("a", FunnelEvent.CONTACTED, {}))
        response = client.get("/dashboard/funnel")
        assert "calibración" in response.text.lower()


class TestEconomicsDashboard:
    def test_sin_datos_no_rompe(self, client):
        response = client.get("/dashboard/economics")
        assert response.status_code == 200
        assert "USD 0" in response.text

    def test_sin_ventas_cac_no_calculable(self, client):
        _record(client, ("a", FunnelEvent.CONTACTED, {}))
        response = client.get("/dashboard/economics")
        assert "no es calculable" in response.text.lower()

    def test_cohortes_aparecen_con_datos_segmentados(self, client):
        _record(
            client,
            (
                "a",
                FunnelEvent.CONTACTED,
                {"vertical": "hvac", "metro": "tucson-az", "language": "es", "pain_score": 80},
            ),
            (
                "a",
                FunnelEvent.PAID,
                {"vertical": "hvac", "metro": "tucson-az", "language": "es", "amount_usd": 950},
            ),
        )
        response = client.get("/dashboard/economics")
        assert response.status_code == 200
        assert "hvac" in response.text
        assert "tucson-az" in response.text

    def test_correlacion_de_dolor_cuenta_el_bucket_correcto(self, client):
        _record(
            client,
            ("a", FunnelEvent.CONTACTED, {"pain_score": 85}),
            ("a", FunnelEvent.PAID, {"amount_usd": 950}),
        )
        response = client.get("/dashboard/economics")
        assert "70-100" in response.text

    def test_salud_de_datos_muestra_la_corrida_simulada(self, client):
        run_id = _create_simulated_run(client)
        response = client.get("/dashboard/economics")
        assert response.status_code == 200
        assert run_id in response.text
