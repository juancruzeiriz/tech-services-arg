"""Tests de `gtm/store/repo.py`: construcción de filas, SQL genérico de upsert,
y la degradación al outbox cuando Postgres no está disponible o falla.

`upsert()` se prueba contra un pool falso en memoria -- no hay Postgres en CI --
que imita lo mínimo del protocolo async de psycopg3 (`pool.connection()` como
context manager async, `conn.cursor()` también, `executemany`)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gtm.factory.types import (
    ContactChannel,
    ContactPlan,
    Demo,
    Language,
    OutreachEmail,
    PainScore,
    Prospect,
    SenderIdentity,
)
from gtm.store import buffer, repo


class _FakeCursor:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls: list[tuple[str, list[dict]]] = []

    async def executemany(self, sql, rows):
        if self.should_fail:
            raise RuntimeError("conexión caída")
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
    """Doble en memoria de `AsyncConnectionPool`: solo lo que `upsert()` toca."""

    def __init__(self, should_fail: bool = False) -> None:
        self.cursor = _FakeCursor(should_fail=should_fail)
        self._conn = _FakeConnection(self.cursor)

    def connection(self):
        return _FakeConnectionCM(self._conn)


@pytest.fixture
def outbox_path(tmp_path, monkeypatch):
    path = tmp_path / "outbox.jsonl"
    monkeypatch.setattr(buffer, "OUTBOX_PATH", path)
    return path


class TestTableSpecs:
    def test_toda_tabla_tiene_columnas(self):
        for table, (columns, _conflict) in repo.TABLE_SPECS.items():
            assert columns, f"{table} sin columnas"

    def test_la_clave_de_conflicto_es_subconjunto_de_las_columnas(self):
        for table, (columns, conflict) in repo.TABLE_SPECS.items():
            assert set(conflict) <= set(columns), f"{table}: clave de conflicto fuera de columnas"

    def test_toda_tabla_tiene_clave_de_conflicto(self):
        """Ninguna tabla es insert-only puro: ver el comentario de client_id en
        schema/0001_init.sql para por qué incluso los logs de eventos la tienen."""
        for table, (_columns, conflict) in repo.TABLE_SPECS.items():
            assert conflict, f"{table} sin clave de conflicto: el replay no sería idempotente"


class TestBuildUpsertSql:
    def test_genera_on_conflict_do_update_cuando_hay_columnas_extra(self):
        sql = repo._build_upsert_sql("prospects", ("place_id", "name"), ("place_id",))
        assert "insert into prospects (place_id, name)" in sql
        assert "on conflict (place_id) do update set name = excluded.name" in sql

    def test_genera_do_nothing_cuando_todas_las_columnas_son_la_clave(self):
        sql = repo._build_upsert_sql("run_prospects", ("run_id", "place_id"), ("run_id", "place_id"))
        assert "on conflict (run_id, place_id) do nothing" in sql

    def test_placeholders_usan_el_nombre_de_columna(self):
        sql = repo._build_upsert_sql("costs", ("client_id", "amount_usd"), ("client_id",))
        assert "%(client_id)s" in sql
        assert "%(amount_usd)s" in sql


class TestUpsert:
    async def test_filas_vacias_no_toca_nada(self):
        pool = _FakePool()
        ok = await repo.upsert(pool, "prospects", [])
        assert ok is True
        assert pool.cursor.calls == []

    async def test_tabla_desconocida_levanta(self):
        with pytest.raises(ValueError, match="no_existe"):
            await repo.upsert(_FakePool(), "no_existe", [{"x": 1}])

    async def test_sin_pool_va_directo_al_outbox(self, outbox_path):
        row = repo.prospect_row(Prospect(place_id="p1", name="X", vertical="hvac", metro="Tucson, AZ"))
        ok = await repo.upsert(None, "prospects", [row])
        assert ok is False
        envelopes = buffer.read_all(outbox_path)
        assert len(envelopes) == 1
        assert envelopes[0]["table"] == "prospects"
        assert envelopes[0]["rows"] == [row]

    async def test_pool_exitoso_escribe_y_no_toca_el_outbox(self, outbox_path):
        pool = _FakePool()
        row = repo.prospect_row(Prospect(place_id="p1", name="X", vertical="hvac", metro="Tucson, AZ"))

        ok = await repo.upsert(pool, "prospects", [row])

        assert ok is True
        assert len(pool.cursor.calls) == 1
        assert buffer.read_all(outbox_path) == []

    async def test_pool_que_falla_degrada_al_outbox(self, outbox_path):
        pool = _FakePool(should_fail=True)
        row = repo.prospect_row(Prospect(place_id="p1", name="X", vertical="hvac", metro="Tucson, AZ"))

        ok = await repo.upsert(pool, "prospects", [row])

        assert ok is False
        envelopes = buffer.read_all(outbox_path)
        assert len(envelopes) == 1
        assert envelopes[0]["rows"] == [row]


class TestRowBuilders:
    def test_prospect_row_es_json_safe(self):
        prospect = Prospect(
            place_id="p1", name="Ramirez Plumbing", vertical="plumber", metro="Tucson, AZ",
            phone="(520) 555-0142", website="https://ramirez.example", rating=4.8, review_count=214,
        )
        row = repo.prospect_row(prospect)
        assert row["place_id"] == "p1"
        assert row["web_presence"] == "has_site"
        assert isinstance(row["first_seen_at"], str)

    def test_score_row_incluye_score_derivado(self):
        score = PainScore(place_id="p1", performance=30, seo=60)
        row = repo.score_row("run-1", score)
        assert row["score"] == score.score
        assert row["is_qualified"] == score.is_qualified
        assert row["notes"] == []

    def test_demo_row(self):
        demo = Demo(
            place_id="p1", slug="ramirez-plumbing-abc123", html_path="/tmp/index.html",
            url="https://demos.example.com/ramirez-plumbing-abc123/",
            deployed_at=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
        )
        row = repo.demo_row("run-1", demo, "es", bytes_=5000)
        assert row["language"] == "es"
        assert row["deployed_at"] == "2026-08-02T12:00:00+00:00"

    def test_contact_row(self):
        plan = ContactPlan(place_id="p1", channel=ContactChannel.PHONE, target="5205550142", rationale="x")
        row = repo.contact_row("run-1", plan)
        assert row["channel"] == "phone"
        assert row["is_actionable"] is True

    def test_outreach_email_row(self):
        sender = SenderIdentity("A", "a@example.com", "Calle 123, Ciudad, Pais completa", "https://x.example/unsub")
        email = OutreachEmail(
            place_id="p1", to_email=None, subject="s", body="b", sender=sender,
            demo_url="https://demo.example", language=Language.ES,
        )
        row = repo.outreach_email_row("run-1", email)
        assert row["language"] == "es"
        assert row["from_email"] == "a@example.com"
        assert row["sent_at"] is None

    def test_cost_row_tiene_client_id_unico(self):
        a = repo.cost_row(category="api", amount_usd=5.0)
        b = repo.cost_row(category="api", amount_usd=5.0)
        assert a["client_id"] != b["client_id"]

    def test_time_log_row(self):
        row = repo.time_log_row(minutes=30, activity="llamadas")
        assert row["minutes"] == 30
        assert row["activity"] == "llamadas"
        assert row["client_id"]


class TestPersistRun:
    """`persist_run` es lo que `run_pipeline` (o la UI) llama una vez al final de
    una corrida. Se prueba con datos reales de `run_pipeline` en modo simulado
    -- no fixtures a mano -- para que el test falle si algún campo nuevo del
    `RunResult` no llega a tener su columna."""

    async def _simulated_result(self, tmp_path):
        from gtm.factory.ledger import SuppressionList
        from gtm.factory.pipeline import RunContext, run_pipeline

        ctx = RunContext.create(
            "hvac", "Tucson, AZ", root=tmp_path / "runs", simulated=True, limit=4, seed=1,
            author_name="Test", author_url="https://example.com", base_url="https://demos.example.com",
        )
        result = await run_pipeline(ctx, suppression=SuppressionList(tmp_path / "suppression.jsonl"))
        return ctx, result

    async def test_sin_pool_todo_va_al_outbox(self, tmp_path, outbox_path):
        ctx, result = await self._simulated_result(tmp_path)

        await repo.persist_run(None, ctx, result)

        envelopes = buffer.read_all(outbox_path)
        tables = {e["table"] for e in envelopes}
        # runs, prospects y run_prospects siempre tienen filas en una corrida
        # simulada con calificados; scores/demos/contacts dependen de si algo
        # calificó, pero con seed=1/limit=4 ya sabemos (test_pipeline.py) que sí.
        assert {"runs", "prospects", "run_prospects", "scores", "demos", "contacts"} <= tables

    async def test_con_pool_exitoso_no_toca_el_outbox(self, tmp_path, outbox_path):
        ctx, result = await self._simulated_result(tmp_path)
        pool = _FakePool()

        await repo.persist_run(pool, ctx, result)

        assert buffer.read_all(outbox_path) == []
        assert len(pool.cursor.calls) >= 1

    async def test_run_row_ok_cuando_no_hay_etapas_fallidas(self, tmp_path):
        ctx, result = await self._simulated_result(tmp_path)
        row = repo.run_row(ctx, result)
        assert row["id"] == ctx.run_id
        assert row["status"] == "ok"
        assert row["error"] is None
        assert row["simulated"] is True
