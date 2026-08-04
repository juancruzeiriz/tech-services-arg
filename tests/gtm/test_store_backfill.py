"""Tests de `gtm/store/backfill.py`: JSONL -> Postgres, y reintento del outbox.

Igual que `test_store_repo.py`, contra un pool falso en memoria -- no hay
Postgres en CI. Lo que se prueba acá es la lógica de mapeo de filas y la
reescritura del outbox, no la conexión real."""

from __future__ import annotations

import json

import pytest

from gtm.store import backfill, buffer


class _FakeCursor:
    def __init__(self, fail_if_table_in: set[str] | None = None) -> None:
        self.fail_if_table_in = fail_if_table_in or set()
        self.calls: list[tuple[str, list[dict]]] = []

    async def executemany(self, sql, rows):
        for table in self.fail_if_table_in:
            if f"insert into {table} " in sql:
                raise RuntimeError(f"fallo simulado para {table}")
        self.calls.append((sql, rows))

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
    def __init__(self, fail_if_table_in: set[str] | None = None) -> None:
        self.cursor = _FakeCursor(fail_if_table_in)
        self._conn = _FakeConnection(self.cursor)

    def connection(self):
        return _FakeConnectionCM(self._conn)


@pytest.fixture
def suppression_file(tmp_path):
    path = tmp_path / "suppression.jsonl"
    lines = [
        {"key": "hash1", "kind": "place_id", "reason": "opted_out", "at": "2026-01-01T00:00:00+00:00", "note": "no llamar"},
        {"key": "hash2", "kind": "phone", "reason": "customer", "at": "2026-01-02T00:00:00+00:00", "note": ""},
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def funnel_file(tmp_path):
    path = tmp_path / "funnel.jsonl"
    lines = [
        # Registro "viejo", sin channel/language/run_id (de antes de esos campos).
        {"key": "hash1", "event": "contacted", "level": 1, "at": "2026-01-01T00:00:00+00:00",
         "vertical": "hvac", "metro": "Tucson, AZ", "pain_score": 90, "amount_usd": 0, "note": ""},
        # Registro nuevo, con todos los campos.
        {"key": "hash2", "event": "paid", "level": 5, "at": "2026-01-03T00:00:00+00:00",
         "vertical": "plumber", "metro": "Phoenix, AZ", "channel": "phone", "language": "es",
         "run_id": "abc123", "pain_score": 70, "amount_usd": 950.0, "note": "pagó"},
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def outbox_path(tmp_path, monkeypatch):
    path = tmp_path / "outbox.jsonl"
    monkeypatch.setattr(buffer, "OUTBOX_PATH", path)
    return path


class TestBackfillJsonl:
    async def test_cuenta_los_registros_de_cada_archivo(self, suppression_file, funnel_file):
        pool = _FakePool()
        counts = await backfill.backfill_jsonl(
            pool, suppression_path=suppression_file, funnel_path=funnel_file
        )
        assert counts == {"suppressions": 2, "funnel_events": 2}

    async def test_mapea_key_a_place_id_hash_y_deja_place_id_en_none(self, suppression_file, funnel_file):
        pool = _FakePool()
        await backfill.backfill_jsonl(pool, suppression_path=suppression_file, funnel_path=funnel_file)

        funnel_call = next(rows for sql, rows in pool.cursor.calls if "insert into funnel_events" in sql)
        assert funnel_call[0]["place_id_hash"] == "hash1"
        assert funnel_call[0]["place_id"] is None

    async def test_registro_viejo_sin_channel_no_rompe(self, suppression_file, funnel_file):
        """El primer registro del fixture no tiene channel/language/run_id --
        backfillarlo no debe levantar KeyError."""
        pool = _FakePool()
        await backfill.backfill_jsonl(pool, suppression_path=suppression_file, funnel_path=funnel_file)

        funnel_call = next(rows for sql, rows in pool.cursor.calls if "insert into funnel_events" in sql)
        old_record = next(r for r in funnel_call if r["place_id_hash"] == "hash1")
        assert old_record["channel"] is None
        assert old_record["language"] is None
        assert old_record["run_id"] is None

    async def test_registro_nuevo_conserva_channel_e_idioma(self, suppression_file, funnel_file):
        pool = _FakePool()
        await backfill.backfill_jsonl(pool, suppression_path=suppression_file, funnel_path=funnel_file)

        funnel_call = next(rows for sql, rows in pool.cursor.calls if "insert into funnel_events" in sql)
        new_record = next(r for r in funnel_call if r["place_id_hash"] == "hash2")
        assert new_record["channel"] == "phone"
        assert new_record["language"] == "es"
        assert new_record["run_id"] == "abc123"

    async def test_archivos_vacios_o_inexistentes_cuentan_cero(self, tmp_path):
        pool = _FakePool()
        counts = await backfill.backfill_jsonl(
            pool,
            suppression_path=tmp_path / "no-existe.jsonl",
            funnel_path=tmp_path / "tampoco.jsonl",
        )
        assert counts == {"suppressions": 0, "funnel_events": 0}

    async def test_sin_pool_va_al_outbox(self, suppression_file, funnel_file, outbox_path):
        counts = await backfill.backfill_jsonl(
            None, suppression_path=suppression_file, funnel_path=funnel_file
        )
        assert counts == {"suppressions": 2, "funnel_events": 2}
        tables = {e["table"] for e in buffer.read_all(outbox_path)}
        assert tables == {"suppressions", "funnel_events"}


class TestReplayOutbox:
    async def test_sin_pool_no_toca_el_archivo(self, outbox_path):
        buffer.spool("prospects", [{"place_id": "p1"}], path=outbox_path)
        result = await backfill.replay_outbox(None, outbox_path)
        assert result == {"replayed": 0, "remaining": 1}
        assert len(buffer.read_all(outbox_path)) == 1

    async def test_outbox_vacio(self, outbox_path):
        pool = _FakePool()
        result = await backfill.replay_outbox(pool, outbox_path)
        assert result == {"replayed": 0, "remaining": 0}

    async def test_todo_exitoso_vacia_el_outbox(self, outbox_path):
        buffer.spool("prospects", [{"place_id": "p1", "name": "X", "first_seen_at": "2026-01-01T00:00:00+00:00", "last_seen_at": "2026-01-01T00:00:00+00:00", "vertical": "hvac", "metro": "Tucson, AZ", "phone": None, "website": None, "rating": None, "review_count": 0, "address": None, "web_presence": "none"}], path=outbox_path)
        buffer.spool("suppressions", [{"key": "hash1", "kind": "place_id", "reason": "opted_out", "at": "2026-01-01T00:00:00+00:00", "note": ""}], path=outbox_path)
        pool = _FakePool()

        result = await backfill.replay_outbox(pool, outbox_path)

        assert result == {"replayed": 2, "remaining": 0}
        assert buffer.read_all(outbox_path) == []

    async def test_fallo_parcial_deja_solo_lo_que_sigue_pendiente(self, outbox_path):
        buffer.spool("prospects", [{"place_id": "p1", "name": "X", "first_seen_at": "2026-01-01T00:00:00+00:00", "last_seen_at": "2026-01-01T00:00:00+00:00", "vertical": "hvac", "metro": "Tucson, AZ", "phone": None, "website": None, "rating": None, "review_count": 0, "address": None, "web_presence": "none"}], path=outbox_path)
        buffer.spool("suppressions", [{"key": "hash1", "kind": "place_id", "reason": "opted_out", "at": "2026-01-01T00:00:00+00:00", "note": ""}], path=outbox_path)
        pool = _FakePool(fail_if_table_in={"suppressions"})

        result = await backfill.replay_outbox(pool, outbox_path)

        assert result == {"replayed": 1, "remaining": 1}
        remaining = buffer.read_all(outbox_path)
        assert len(remaining) == 1
        assert remaining[0]["table"] == "suppressions"

    async def test_reintentar_de_nuevo_despues_de_un_fallo_parcial_termina_de_vaciar(self, outbox_path):
        buffer.spool("suppressions", [{"key": "hash1", "kind": "place_id", "reason": "opted_out", "at": "2026-01-01T00:00:00+00:00", "note": ""}], path=outbox_path)
        failing_pool = _FakePool(fail_if_table_in={"suppressions"})
        await backfill.replay_outbox(failing_pool, outbox_path)
        assert buffer.pending_count(outbox_path) == 1

        healthy_pool = _FakePool()
        result = await backfill.replay_outbox(healthy_pool, outbox_path)

        assert result == {"replayed": 1, "remaining": 0}
        assert buffer.pending_count(outbox_path) == 0
