"""Tests de `gtm/ui/routes/pricing.py`.

Sin `SUPABASE_DB_URL` (igual que el resto de la suite de UI), `total_cost_usd`
y `total_minutes_logged` degradan a 0 -- así que estos tests no pueden ejercer
el camino de "venta real ya cargada" (necesitaría Postgres de verdad). Lo que
sí prueban es exactamente lo que puede pasar sin base de datos: el estado
vacío, y el camino de la estimación manual, que es el que hace que la
pantalla sirva hoy mismo con `gtm/funnel.jsonl` todavía vacío.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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


def _record(*events):
    from gtm.factory import ledger as ledger_mod

    ledger = ledger_mod.FunnelLedger()
    for place_id, event, kwargs in events:
        ledger.record(place_id, event, **kwargs)


class TestPricingVacio:
    def test_no_rompe_sin_datos(self, client):
        response = client.get("/pricing")
        assert response.status_code == 200

    def test_muestra_el_precio_del_paquete(self, client):
        response = client.get("/pricing")
        assert "950" in response.text

    def test_sin_horas_el_piso_es_desconocido(self, client):
        """Con una estimación cargada pero sin costos/horas en Postgres
        (`floor_usd_hour` es None), la comparación no puede colapsar a "por
        debajo": tiene que decir explícitamente que no se sabe."""
        response = client.get("/pricing?estimated_hours=6")
        assert "Piso desconocido" in response.text
        assert "Por debajo del piso" not in response.text

    def test_sin_venta_ni_estimacion_no_afirma_nada_sobre_el_paquete(self, client):
        from gtm.factory.types import FunnelEvent

        _record(("a", FunnelEvent.CONTACTED, {}))
        response = client.get("/pricing")
        assert "no tiene respuesta todavía" in response.text

    def test_sin_contactos_el_costo_por_contacto_es_desconocido(self, client):
        response = client.get("/pricing")
        assert "sin contactados todavía" in response.text


class TestEstimacionManual:
    def test_calcula_la_tarifa_implicita_del_paquete(self, client):
        response = client.get("/pricing?estimated_hours=6")
        # 950 / 6 = 158.33... -> 158.3 redondeado
        assert "158.3" in response.text

    def test_marca_la_estimacion_como_estimada_no_medida(self, client):
        response = client.get("/pricing?estimated_hours=6")
        assert "estimadas" in response.text.lower()

    def test_cero_horas_no_dispara_el_camino_de_estimacion(self, client):
        """0 es "sin estimar", no "instantáneo": evita una división por cero
        disfrazada de estimación real."""
        response = client.get("/pricing?estimated_hours=0")
        assert "no tiene respuesta todavía" in response.text


class TestCotizador:
    def test_sin_piso_no_hay_cotizacion(self, client):
        response = client.get("/pricing?quote_hours=4")
        assert "Cargá horas arriba" in response.text

    def test_no_rompe_con_horas_negativas(self, client):
        """El input HTML tiene min="0", pero la ruta no puede confiar en eso:
        un cliente que pega la URL a mano puede mandar cualquier cosa."""
        response = client.get("/pricing?quote_hours=-5&estimated_hours=-3")
        assert response.status_code == 200
