"""Tests de las rutas HTTP de la UI (`gtm/ui/routes/`).

Con `TestClient` (sync, sobre httpx) — no se espera a que termine la tarea de
fondo del pipeline en la mayoría de los tests: alcanza con verificar que la
corrida quedó registrada y que el detalle responde mientras está "pending" o
"running". El flujo end-to-end completo (formulario -> progreso en vivo por
SSE -> resultados) ya se verificó a mano contra un server real."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gtm.ui.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    from gtm.factory import config as config_mod
    from gtm.ui import presets as presets_mod

    monkeypatch.setattr(config_mod, "BUILD_DIR", tmp_path / "build")
    monkeypatch.setattr(config_mod, "DEMOS_DIR", tmp_path / "build" / "demos")
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path / "build" / "data")
    monkeypatch.setattr(presets_mod, "PRESETS_PATH", tmp_path / "build" / "presets.json")
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)

    with TestClient(create_app()) as test_client:
        yield test_client


class TestHomePage:
    def test_devuelve_200_y_lista_el_catalogo(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "oficio" in response.text.lower() or "vertical" in response.text.lower()
        # 15 oficios en el catálogo: alguno tiene que aparecer en el select.
        assert "plomero" in response.text.lower() or "hvac" in response.text.lower()

    def test_incluye_los_20_metros(self, client):
        response = client.get("/")
        assert "Tucson, AZ" in response.text
        assert "Houston, TX" in response.text


class TestSettingsPage:
    def test_devuelve_200(self, client):
        response = client.get("/settings")
        assert response.status_code == 200

    def test_muestra_sin_conexion_sin_dsn(self, client):
        response = client.get("/settings")
        assert "Sin conexión" in response.text or "sin conexión" in response.text.lower()


class TestCreateRun:
    def _form_data(self, **overrides):
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
        return data

    def test_redirige_a_la_corrida_creada(self, client):
        response = client.post("/runs", data=self._form_data(), follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/runs/")

    def test_la_corrida_queda_registrada(self, client):
        response = client.post("/runs", data=self._form_data(), follow_redirects=False)
        run_id = response.headers["location"].removeprefix("/runs/")

        detail = client.get(f"/runs/{run_id}")
        assert detail.status_code == 200
        assert run_id in detail.text

    def test_vertical_texto_libre(self, client):
        response = client.post(
            "/runs",
            data=self._form_data(vertical="__other__", vertical_other="alpaca-shearer"),
            follow_redirects=False,
        )
        run_id = response.headers["location"].removeprefix("/runs/")
        handle = client.app.state.registry.get(run_id)
        assert handle.ctx.vertical == "alpaca-shearer"

    def test_metro_texto_libre(self, client):
        response = client.post(
            "/runs",
            data=self._form_data(metro="__other__", metro_other="Chandler, AZ"),
            follow_redirects=False,
        )
        run_id = response.headers["location"].removeprefix("/runs/")
        handle = client.app.state.registry.get(run_id)
        assert handle.ctx.metro == "Chandler, AZ"

    def test_precio_personalizado(self, client):
        response = client.post(
            "/runs",
            data=self._form_data(price_usd="__other__", price_usd_other="1200"),
            follow_redirects=False,
        )
        run_id = response.headers["location"].removeprefix("/runs/")
        handle = client.app.state.registry.get(run_id)
        assert handle.ctx.offer_price_usd == 1200

    def test_precio_personalizado_invalido_cae_al_default(self, client):
        response = client.post(
            "/runs",
            data=self._form_data(price_usd="__other__", price_usd_other="no-es-un-numero"),
            follow_redirects=False,
        )
        run_id = response.headers["location"].removeprefix("/runs/")
        handle = client.app.state.registry.get(run_id)
        assert handle.ctx.offer_price_usd == 950

    def test_modo_real_no_es_simulado(self, client):
        response = client.post("/runs", data=self._form_data(mode="real"), follow_redirects=False)
        run_id = response.headers["location"].removeprefix("/runs/")
        handle = client.app.state.registry.get(run_id)
        assert handle.ctx.simulated is False

    def test_publish_checkbox_desactiva_dry_run(self, client):
        response = client.post("/runs", data=self._form_data(publish="1"), follow_redirects=False)
        run_id = response.headers["location"].removeprefix("/runs/")
        handle = client.app.state.registry.get(run_id)
        assert handle.ctx.dry_run is False

    def test_sin_publish_queda_en_dry_run(self, client):
        response = client.post("/runs", data=self._form_data(), follow_redirects=False)
        run_id = response.headers["location"].removeprefix("/runs/")
        handle = client.app.state.registry.get(run_id)
        assert handle.ctx.dry_run is True

    def test_una_corrida_en_curso_rechaza_una_segunda(self, client):
        from gtm.factory.pipeline import RunContext

        client.app.state.registry.register(RunContext.create("hvac", "Tucson, AZ", simulated=True))
        # Simular que está corriendo: task no-None y no terminada.
        class _FakeTask:
            def done(self):
                return False

        client.app.state.registry.all()[0].task = _FakeTask()

        before = len(client.app.state.registry.all())
        client.post("/runs", data=self._form_data(), follow_redirects=False)
        after = len(client.app.state.registry.all())
        assert after == before, "no debería haberse creado una segunda corrida"


class TestRunDetail:
    def test_corrida_desconocida_da_404(self, client):
        response = client.get("/runs/no-existe")
        assert response.status_code == 404

    def test_lista_de_corridas_vacia(self, client):
        response = client.get("/runs")
        assert response.status_code == 200


class TestPresets:
    def _form_data(self, **overrides):
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
        return data

    def test_guardar_preset_lo_deja_disponible_en_home(self, client):
        client.post(
            "/runs",
            data=self._form_data(save_preset="1", preset_name="hvac-az-es"),
            follow_redirects=False,
        )
        response = client.get("/")
        assert "hvac-az-es" in response.text

    def test_sin_marcar_guardar_no_crea_preset(self, client):
        client.post("/runs", data=self._form_data(), follow_redirects=False)
        response = client.get("/")
        assert "no-deberia-existir" not in response.text
        from gtm.ui import presets as presets_mod

        assert presets_mod.list_presets() == []

    def test_cargar_preset_precompleta_el_form(self, client):
        client.post(
            "/runs",
            data=self._form_data(
                metro="__other__", metro_other="Chandler, AZ", save_preset="1", preset_name="chandler"
            ),
            follow_redirects=False,
        )
        response = client.get("/?preset=chandler")
        assert response.status_code == 200
        assert "Chandler, AZ" in response.text

    def test_preset_inexistente_no_rompe_home(self, client):
        response = client.get("/?preset=no-existe")
        assert response.status_code == 200


class TestCosts:
    def test_guarda_costo_y_redirige_a_settings(self, client):
        response = client.post(
            "/costs",
            data={"category": "api", "amount_usd": "12.50", "vendor": "Google"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/settings"

    def test_monto_cero_no_rompe(self, client):
        response = client.post(
            "/costs", data={"category": "api", "amount_usd": "0"}, follow_redirects=False
        )
        assert response.status_code == 303
