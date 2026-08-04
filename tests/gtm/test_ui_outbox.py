"""Tests de la pantalla de envíos (`gtm/ui/routes/outbox.py`).

Igual que `test_ui_queue.py`, aísla los ledgers a `tmp_path`. El pool de
Postgres se inyecta con un doble en memoria (mismo patrón que
`test_send_outbox.py`) vía `app.dependency_overrides[deps.get_pool]`, porque
`gtm/send/outbox.py` no funciona sin `UPDATE`/`SELECT ... FOR UPDATE SKIP
LOCKED`, que un fixture sin Postgres real no puede dar de otra forma.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from gtm.ui import deps
from gtm.ui.app import create_app


class _FakeCursor:
    def __init__(self, *, fetchall_result=None, fetchone_result=None) -> None:
        self.executed: list[tuple[str, object]] = []
        self._fetchall_result = fetchall_result or []
        self._fetchone_result = fetchone_result

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))

    async def executemany(self, sql, rows):
        self.executed.append((sql, rows))

    async def fetchall(self):
        return self._fetchall_result

    async def fetchone(self):
        return self._fetchone_result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeConnectionCM:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, cursor: _FakeCursor) -> None:
        self.cursor = cursor

    def connection(self):
        return _FakeConnectionCM(_FakeConnection(self.cursor))


def _row(**overrides) -> tuple:
    defaults = {
        "id": 1, "client_id": "c1", "run_id": None, "place_id": "p1", "channel": "phone",
        "to_address": "+15550100", "subject": None, "body": "hola", "link_token": None,
        "status": "manual_pending", "attempt_count": 0, "max_attempts": 1, "next_attempt_at": None,
        "provider_message_id": None, "verp_tag": None,
        "created_at": datetime(2026, 8, 1, tzinfo=UTC), "queued_at": None, "sent_at": None,
        "delivered_at": None, "failed_at": None, "failure_kind": None, "failure_reason": None,
        "last_error": None,
    }
    defaults.update(overrides)
    return tuple(defaults.values())


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


def _with_fake_pool(client: TestClient, cursor: _FakeCursor) -> None:
    pool = _FakePool(cursor)
    client.app.dependency_overrides[deps.get_pool] = lambda: pool


def _wait_for_run(client, run_id: str, timeout: float = 5.0):
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
        "vertical": "hvac", "vertical_other": "", "metro": "tucson-az", "metro_other": "",
        "language": "es", "mode": "simulate", "limit": "6", "min_reviews": "50",
        "min_rating": "4.0", "seed": "1", "concurrency": "5", "price_usd": "950",
        "base_url": "https://demos.example.com", "author_name": "Test", "author_url": "https://example.com",
    }
    data.update(overrides)
    response = client.post("/runs", data=data, follow_redirects=False)
    run_id = response.headers["location"].removeprefix("/runs/")
    handle = _wait_for_run(client, run_id)
    assert handle.result is not None, f"la corrida simulada terminó con error: {handle.error}"
    return run_id


class TestOutboxPageSinPool:
    def test_sin_postgres_la_pantalla_explica_por_que_esta_deshabilitada(self, client):
        # No alcanza con delenv("SUPABASE_DB_URL"): gtm/store/dsn.py vuelve a
        # leer .env.personal (que en esta máquina de desarrollo sí tiene un
        # DSN real) la primera vez que algo llama a get_dsn() en el proceso.
        # Se pisa la dependencia directamente para simular "sin Postgres" de
        # forma determinística, sin importar qué haya en .env.personal.
        client.app.dependency_overrides[deps.get_pool] = lambda: None

        response = client.get("/outbox")
        assert response.status_code == 200
        assert "deshabilitado" in response.text.lower()
        assert "SUPABASE_DB_URL" in response.text


class TestOutboxPageConPool:
    def test_lista_los_mensajes_con_su_estado(self, client):
        cursor = _FakeCursor(fetchall_result=[_row()])
        _with_fake_pool(client, cursor)

        response = client.get("/outbox")

        assert response.status_code == 200
        assert "p1" in response.text
        assert "a mano: pendiente" in response.text

    def test_el_boton_de_reenvio_aparece_solo_en_los_fallados(self, client):
        cursor = _FakeCursor(
            fetchall_result=[
                _row(id=1, status="failed", last_error="smtp timeout"),
                _row(id=2, status="sent"),
            ]
        )
        _with_fake_pool(client, cursor)

        response = client.get("/outbox")

        assert response.text.count("Reintentar") == 1

    def test_un_bounce_duro_no_ofrece_reenvio(self, client):
        cursor = _FakeCursor(fetchall_result=[_row(id=1, status="bounced", failure_kind="hard_bounce")])
        _with_fake_pool(client, cursor)

        response = client.get("/outbox")

        assert "Reintentar" not in response.text

    def test_el_boton_marcar_enviado_aparece_solo_en_manual_pending(self, client):
        cursor = _FakeCursor(fetchall_result=[_row(id=1, status="manual_pending")])
        _with_fake_pool(client, cursor)

        response = client.get("/outbox")

        assert "Marcar enviado" in response.text


class TestEnqueueSelected:
    def test_seleccionar_y_encolar_varios_de_una(self, client):
        run_id = _create_simulated_run(client)
        handle = client.app.state.registry.get(run_id)
        actionable = [p for p in handle.result.contacts if p.is_actionable]
        assert actionable, "el fixture simulado tiene que producir al menos un contacto accionable"

        cursor = _FakeCursor()
        _with_fake_pool(client, cursor)

        selected = [f"{run_id}|{plan.place_id}" for plan in actionable]
        response = client.post("/outbox/enqueue", data={"selected": selected}, follow_redirects=False)

        assert response.status_code == 303
        assert response.headers["location"] == "/outbox"
        sql, rows = cursor.executed[0]
        assert "insert into outreach_messages" in sql
        assert len(rows) == len(actionable)
        assert all(row["status"] == "manual_pending" for row in rows)

    def test_sin_seleccion_no_toca_el_pool(self, client):
        _create_simulated_run(client)
        cursor = _FakeCursor()
        _with_fake_pool(client, cursor)

        client.post("/outbox/enqueue", data={}, follow_redirects=False)

        assert cursor.executed == []


class TestRetryCancelManualDone:
    def test_reenviar_incrementa_el_intento_y_no_duplica_la_fila(self, client):
        cursor = _FakeCursor(fetchone_result=_row(id=1, channel="email", status="failed", attempt_count=1))
        _with_fake_pool(client, cursor)

        response = client.post("/outbox/1/retry", follow_redirects=False)

        assert response.status_code == 303
        assert len(cursor.executed) == 2  # el SELECT de get_by_id, y el UPDATE del requeue
        _, rows = cursor.executed[1]
        assert rows[0]["status"] == "queued"
        assert rows[0]["client_id"] == "c1"  # misma fila, no una nueva

    def test_un_bounce_duro_no_se_puede_reencolar_por_esta_ruta(self, client):
        cursor = _FakeCursor(
            fetchone_result=_row(id=1, channel="email", status="bounced", failure_kind="hard_bounce")
        )
        _with_fake_pool(client, cursor)

        response = client.post("/outbox/1/retry", follow_redirects=False)

        assert response.status_code == 303
        assert len(cursor.executed) == 1  # solo el SELECT: el UPDATE nunca se emite

    def test_cancelar_un_mensaje_encolado(self, client):
        cursor = _FakeCursor(fetchone_result=_row(id=1, status="queued"))
        _with_fake_pool(client, cursor)

        response = client.post("/outbox/1/cancel", follow_redirects=False)

        assert response.status_code == 303
        _, rows = cursor.executed[1]
        assert rows[0]["status"] == "cancelled"

    def test_marcar_enviado_a_mano(self, client):
        cursor = _FakeCursor(fetchone_result=_row(id=1, status="manual_pending"))
        _with_fake_pool(client, cursor)

        response = client.post("/outbox/1/manual-done", follow_redirects=False)

        assert response.status_code == 303
        _, rows = cursor.executed[1]
        assert rows[0]["status"] == "manual_done"

    def test_mensaje_inexistente_no_lanza(self, client):
        cursor = _FakeCursor(fetchone_result=None)
        _with_fake_pool(client, cursor)

        response = client.post("/outbox/999/retry", follow_redirects=False)

        assert response.status_code == 303
        assert len(cursor.executed) == 1  # solo el SELECT, que no encontró nada
