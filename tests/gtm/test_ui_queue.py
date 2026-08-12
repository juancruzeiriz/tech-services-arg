"""Tests de la cola de contacto (`gtm/ui/routes/queue.py`).

Aísla `gtm.factory.ledger.FUNNEL_PATH`/`SUPPRESSION_PATH` a `tmp_path` en cada
test -- son constantes de módulo evaluadas una vez al importar `ledger.py`, así
que monkeypatchear `config.GTM_DIR` no alcanza; hay que pisar las constantes
directamente. Sin esto, correr estos tests escribiría en el ledger real del
proyecto (el mismo que se commitea a git)."""

from __future__ import annotations

import json

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


def _wait_for_run(client, run_id: str, timeout: float = 5.0):
    """`TestClient` corre la tarea de fondo en el mismo loop, pero el POST
    vuelve antes de que esa tarea llegue a terminar -- a diferencia de un
    server real, acá nada sigue empujando el loop una vez que la request
    original devolvió. Un GET liviano entre reintentos le da al loop la
    chance de avanzar la tarea pendiente."""
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


class TestQueuePage:
    def test_vacia_sin_corridas(self, client):
        response = client.get("/queue")
        assert response.status_code == 200
        assert "pendientes" in response.text.lower() or "no hay nada" in response.text.lower()

    def test_muestra_items_de_una_corrida_terminada(self, client):
        run_id = _create_simulated_run(client)

        response = client.get("/queue")

        assert response.status_code == 200
        assert run_id in response.text or "pendientes" in response.text.lower()

    def test_el_mensaje_incluye_el_link_con_token(self, client):
        run_id = _create_simulated_run(client)
        handle = client.app.state.registry.get(run_id)
        assert handle.tokens, "debería haber minado al menos un token"

        response = client.get(f"/queue?run_id={run_id}")
        token = next(iter(handle.tokens.values()))
        assert f"/v/{token}" in response.text

    def test_filtra_por_run_id(self, client):
        run_a = _create_simulated_run(client, seed="1")
        _create_simulated_run(client, seed="2")  # una segunda corrida: la que NO debe aparecer al filtrar

        response = client.get(f"/queue?run_id={run_a}")

        handle_a = client.app.state.registry.get(run_a)
        target_place_id = next(p.place_id for p in handle_a.result.contacts if p.is_actionable)
        assert f"item-{target_place_id}" in response.text

    def test_badge_de_recordatorio_a_los_3_dias(self, client):
        from datetime import UTC, datetime, timedelta

        from gtm.factory.ledger import FunnelLedger
        from gtm.factory.types import FunnelEvent

        run_id = _create_simulated_run(client)
        handle = client.app.state.registry.get(run_id)
        target_place_id = next(p.place_id for p in handle.result.contacts if p.is_actionable)

        FunnelLedger().record(
            target_place_id, FunnelEvent.CONTACTED, at=datetime.now(UTC) - timedelta(days=4)
        )

        response = client.get(f"/queue?run_id={run_id}")

        assert "día 3" in response.text.lower()

    def test_badge_de_cierre_a_los_7_dias(self, client):
        from datetime import UTC, datetime, timedelta

        from gtm.factory.ledger import FunnelLedger
        from gtm.factory.types import FunnelEvent

        run_id = _create_simulated_run(client)
        handle = client.app.state.registry.get(run_id)
        target_place_id = next(p.place_id for p in handle.result.contacts if p.is_actionable)

        FunnelLedger().record(
            target_place_id, FunnelEvent.CONTACTED, at=datetime.now(UTC) - timedelta(days=8)
        )

        response = client.get(f"/queue?run_id={run_id}")

        assert "día 7" in response.text.lower()

    def test_sin_contacto_previo_no_hay_badge_de_seguimiento(self, client):
        run_id = _create_simulated_run(client)

        response = client.get(f"/queue?run_id={run_id}")

        assert "día 3" not in response.text.lower()
        assert "día 7" not in response.text.lower()

    def test_usa_el_idioma_de_la_demo_no_el_de_la_corrida(self, client, monkeypatch):
        """Regresión: la cola armaba el mensaje con `handle.ctx.language` --
        el idioma de la corrida entera -- en vez de `demo.language` (detectado
        por prospecto, gtm/factory/lang.py). Con `detect_language` forzado a
        ES para todos y una corrida creada en EN, el mensaje tiene que salir
        en español de todas formas."""
        from gtm.factory import pipeline as pipeline_mod
        from gtm.factory.types import Language

        monkeypatch.setattr(
            pipeline_mod, "detect_language", lambda prospect, *, default: Language.ES
        )

        run_id = _create_simulated_run(client, language="en")

        response = client.get(f"/queue?run_id={run_id}")

        assert "Hola," in response.text


class TestRecordEvent:
    def test_registra_en_el_ledger_local(self, client, tmp_path):
        run_id = _create_simulated_run(client)
        handle = client.app.state.registry.get(run_id)
        place_id = next(p.place_id for p in handle.result.contacts if p.is_actionable)

        response = client.post(
            f"/queue/{run_id}/{place_id}/event", data={"event": "contacted"}, follow_redirects=False
        )

        assert response.status_code == 303
        funnel_path = tmp_path / "funnel.jsonl"
        assert funnel_path.exists()
        record = json.loads(funnel_path.read_text(encoding="utf-8").strip().splitlines()[0])
        assert record["event"] == "contacted"
        assert record["run_id"] == run_id
        assert record["language"] == "es"

    def test_registra_el_canal(self, client, tmp_path):
        run_id = _create_simulated_run(client)
        handle = client.app.state.registry.get(run_id)
        plan = next(p for p in handle.result.contacts if p.is_actionable)

        client.post(f"/queue/{run_id}/{plan.place_id}/event", data={"event": "replied"})

        record = json.loads((tmp_path / "funnel.jsonl").read_text(encoding="utf-8").strip())
        assert record["channel"] == plan.channel.value

    def test_registra_el_idioma_de_la_demo_no_el_de_la_corrida(self, client, tmp_path, monkeypatch):
        """Regresión: el evento del embudo grababa `handle.ctx.language` --
        `decision_criteria.yaml` exige segmentar por idioma, y con el valor
        de la corrida esa segmentación mentiría apenas hubiera un prospecto
        detectado en el otro idioma dentro de la misma corrida."""
        from gtm.factory import pipeline as pipeline_mod
        from gtm.factory.types import Language

        monkeypatch.setattr(
            pipeline_mod, "detect_language", lambda prospect, *, default: Language.ES
        )

        run_id = _create_simulated_run(client, language="en")
        handle = client.app.state.registry.get(run_id)
        place_id = next(p.place_id for p in handle.result.contacts if p.is_actionable)

        client.post(f"/queue/{run_id}/{place_id}/event", data={"event": "contacted"})

        record = json.loads((tmp_path / "funnel.jsonl").read_text(encoding="utf-8").strip())
        assert record["language"] == "es"

    def test_pagar_suprime_como_cliente(self, client, tmp_path):
        run_id = _create_simulated_run(client)
        handle = client.app.state.registry.get(run_id)
        place_id = next(p.place_id for p in handle.result.contacts if p.is_actionable)

        client.post(f"/queue/{run_id}/{place_id}/event", data={"event": "paid", "amount_usd": "950"})

        suppression_path = tmp_path / "suppression.jsonl"
        assert suppression_path.exists()
        record = json.loads(suppression_path.read_text(encoding="utf-8").strip())
        assert record["reason"] == "customer"


class TestSuppress:
    def test_desaparece_de_la_cola(self, client):
        run_id = _create_simulated_run(client)
        handle = client.app.state.registry.get(run_id)
        place_id = next(p.place_id for p in handle.result.contacts if p.is_actionable)

        before = client.get(f"/queue?run_id={run_id}")
        assert f"item-{place_id}" in before.text

        client.post(f"/queue/{run_id}/{place_id}/suppress", data={"reason": "opted_out"})

        after = client.get(f"/queue?run_id={run_id}")
        assert f"item-{place_id}" not in after.text
