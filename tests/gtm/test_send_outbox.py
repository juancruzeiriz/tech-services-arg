"""Tests de la máquina de estados del outbox (gtm/send/outbox.py).

Pool falso en memoria, en la misma línea que `test_store_repo.py`: sin
Postgres en CI, solo lo mínimo del protocolo async que `outbox.py` toca
(`execute`, `executemany`, `fetchall`, `fetchone`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from gtm.send import outbox
from gtm.send.types import FailureKind, MessageStatus, OutreachMessage


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


def _message(**overrides) -> OutreachMessage:
    defaults = {"client_id": "c1", "place_id": "p1", "channel": "email", "body": "hola"}
    defaults.update(overrides)
    return OutreachMessage(**defaults)


class TestBackoff:
    def test_el_backoff_crece_y_tiene_techo(self):
        delays = [outbox.backoff_for_attempt(n) for n in range(1, 6)]
        assert delays == sorted(delays)
        assert delays[-1] <= timedelta(days=3)

    def test_el_primer_reintento_no_es_inmediato(self):
        # Un rebote suave suele ser un buzón lleno o un greylist temporal:
        # reintentar en el mismo minuto garantiza el mismo fallo.
        assert outbox.backoff_for_attempt(1) >= timedelta(hours=1)


class TestEnqueue:
    async def test_enqueue_pone_status_queued_y_next_attempt_at(self):
        cursor = _FakeCursor()
        pool = _FakePool(cursor)
        n = await outbox.enqueue(pool, [_message()])
        assert n == 1
        sql, rows = cursor.executed[0]
        assert "insert into outreach_messages" in sql
        assert rows[0]["status"] == "queued"
        assert rows[0]["queued_at"] is not None

    async def test_enqueue_vacio_no_toca_el_pool(self):
        cursor = _FakeCursor()
        pool = _FakePool(cursor)
        n = await outbox.enqueue(pool, [])
        assert n == 0
        assert cursor.executed == []


class TestDailySentCount:
    async def test_cuenta_lo_que_devuelve_postgres(self):
        cursor = _FakeCursor(fetchone_result=(7,))
        pool = _FakePool(cursor)
        assert await outbox.daily_sent_count(pool) == 7

    async def test_sin_filas_es_cero(self):
        cursor = _FakeCursor(fetchone_result=None)
        pool = _FakePool(cursor)
        assert await outbox.daily_sent_count(pool) == 0


class TestClaimDue:
    _ROW = (
        1, "c1", None, "p1", "email", "to@x.com", "asunto", "cuerpo", None,
        "queued", 0, 3, None, None, None,
        datetime(2026, 8, 1, tzinfo=UTC), None, None, None, None, None, None, None,
    )

    async def test_reclama_y_marca_sending(self, monkeypatch):
        cursor = _FakeCursor(fetchall_result=[self._ROW])
        pool = _FakePool(cursor)
        monkeypatch.setattr(outbox, "daily_sent_count", lambda _pool: _async_return(0))

        claimed = await outbox.claim_due(pool, limit=5, daily_cap=20)

        assert len(claimed) == 1
        assert claimed[0].id == 1
        assert claimed[0].status is MessageStatus.SENDING  # el SELECT trae 'queued'; claim_due lo sube
        # dos statements: el SELECT ... FOR UPDATE SKIP LOCKED y el UPDATE que marca sending.
        assert len(cursor.executed) == 2
        assert "for update skip locked" in cursor.executed[0][0].lower()
        assert "update outreach_messages" in cursor.executed[1][0].lower()

    async def test_respeta_el_tope_diario(self, monkeypatch):
        cursor = _FakeCursor(fetchall_result=[self._ROW])
        pool = _FakePool(cursor)
        monkeypatch.setattr(outbox, "daily_sent_count", lambda _pool: _async_return(20))

        claimed = await outbox.claim_due(pool, limit=5, daily_cap=20)

        assert claimed == []
        assert cursor.executed == []  # ni siquiera consulta: ya se sabe que no hay cupo

    async def test_pide_menos_si_el_cupo_restante_es_chico(self, monkeypatch):
        cursor = _FakeCursor(fetchall_result=[])
        pool = _FakePool(cursor)
        monkeypatch.setattr(outbox, "daily_sent_count", lambda _pool: _async_return(18))

        await outbox.claim_due(pool, limit=5, daily_cap=20)

        _, params = cursor.executed[0]
        assert params["take"] == 2  # 20 - 18


def _async_return(value):
    async def _inner(*_a, **_k):
        return value

    return _inner()


class TestGetByVerpTag:
    _ROW = (
        1, "c1", None, "p1", "email", "to@x.com", "asunto", "cuerpo", None,
        "sent", 1, 3, None, "<abc@x>", "tag123",
        datetime(2026, 8, 1, tzinfo=UTC), None, datetime(2026, 8, 1, tzinfo=UTC), None, None, None, None, None,
    )

    async def test_encuentra_el_mensaje_por_su_tag(self):
        cursor = _FakeCursor(fetchone_result=self._ROW)
        pool = _FakePool(cursor)

        found = await outbox.get_by_verp_tag(pool, "tag123")

        assert found is not None
        assert found.id == 1
        _, params = cursor.executed[0]
        assert params["tag"] == "tag123"

    async def test_sin_match_devuelve_none(self):
        cursor = _FakeCursor(fetchone_result=None)
        pool = _FakePool(cursor)
        assert await outbox.get_by_verp_tag(pool, "no-existe") is None


class TestFindOpenedButNotDelivered:
    _ROW = (
        1, "c1", None, "p1", "email", "to@x.com", "asunto", "cuerpo", "tok123",
        "sent", 1, 3, None, "<abc@x>", "tag123",
        datetime(2026, 8, 1, tzinfo=UTC), None, datetime(2026, 8, 1, tzinfo=UTC), None, None, None, None, None,
    )

    async def test_devuelve_los_mensajes_con_apertura_confirmada(self):
        cursor = _FakeCursor(fetchall_result=[self._ROW])
        pool = _FakePool(cursor)

        found = await outbox.find_opened_but_not_delivered(pool)

        assert len(found) == 1
        assert found[0].link_token == "tok123"
        sql, params = cursor.executed[0]
        assert "demo_views" in sql
        assert params["status"] == "sent"

    async def test_sin_aperturas_devuelve_lista_vacia(self):
        cursor = _FakeCursor(fetchall_result=[])
        pool = _FakePool(cursor)
        assert await outbox.find_opened_but_not_delivered(pool) == []


class TestMarkSent:
    async def test_marca_enviado_e_incrementa_intentos(self):
        cursor = _FakeCursor()
        pool = _FakePool(cursor)
        msg = _message(status=MessageStatus.SENDING, attempt_count=0)

        await outbox.mark_sent(pool, msg, provider_message_id="<abc@x>")

        _, rows = cursor.executed[0]
        assert rows[0]["status"] == "sent"
        assert rows[0]["attempt_count"] == 1
        assert rows[0]["provider_message_id"] == "<abc@x>"

    async def test_persiste_el_verp_tag_del_intento(self):
        # Sin esto, un rebote que llegue después nunca podría encontrar este
        # mensaje por outbox.get_by_verp_tag.
        cursor = _FakeCursor()
        pool = _FakePool(cursor)
        msg = _message(status=MessageStatus.SENDING)

        updated = await outbox.mark_sent(pool, msg, provider_message_id="<abc@x>", verp_tag="tag123")

        assert updated.verp_tag == "tag123"
        _, rows = cursor.executed[0]
        assert rows[0]["verp_tag"] == "tag123"


class TestMarkFailed:
    async def test_reencola_si_quedan_intentos(self):
        cursor = _FakeCursor()
        pool = _FakePool(cursor)
        msg = _message(status=MessageStatus.SENDING, attempt_count=0, max_attempts=3)

        updated = await outbox.mark_failed(pool, msg, error="timeout")

        assert updated.status is MessageStatus.QUEUED
        assert updated.attempt_count == 1
        assert updated.next_attempt_at is not None

    async def test_falla_definitivo_al_agotar_intentos(self):
        cursor = _FakeCursor()
        pool = _FakePool(cursor)
        msg = _message(status=MessageStatus.SENDING, attempt_count=2, max_attempts=3)

        updated = await outbox.mark_failed(pool, msg, error="timeout")

        assert updated.status is MessageStatus.FAILED
        assert updated.attempt_count == 3

    async def test_un_error_de_compliance_no_se_reintenta_aunque_queden_intentos(self):
        # Un mensaje no conforme reintentado tres veces es tres infracciones,
        # no una recuperación de un error transitorio.
        cursor = _FakeCursor()
        pool = _FakePool(cursor)
        msg = _message(status=MessageStatus.SENDING, attempt_count=0, max_attempts=3)

        updated = await outbox.mark_failed(pool, msg, error="sin baja", kind=FailureKind.COMPLIANCE)

        assert updated.status is MessageStatus.FAILED


class TestMarkBounced:
    async def test_bounce_duro_es_terminal_y_no_agenda_reintento(self):
        cursor = _FakeCursor()
        pool = _FakePool(cursor)
        msg = _message(status=MessageStatus.SENDING)

        updated = await outbox.mark_bounced(pool, msg, hard=True, detail="550 user unknown")

        assert updated.status is MessageStatus.BOUNCED
        assert updated.next_attempt_at is None
        assert updated.failure_kind == "hard_bounce"

    async def test_bounce_suave_reencola_con_backoff(self):
        cursor = _FakeCursor()
        pool = _FakePool(cursor)
        msg = _message(status=MessageStatus.SENT, attempt_count=1)

        updated = await outbox.mark_bounced(pool, msg, hard=False)

        assert updated.status is MessageStatus.QUEUED
        assert updated.next_attempt_at is not None
        assert updated.failure_kind == "soft_bounce"


class TestMarkDelivered:
    async def test_marca_delivered_con_timestamp(self):
        cursor = _FakeCursor()
        pool = _FakePool(cursor)
        msg = _message(status=MessageStatus.SENT)

        updated = await outbox.mark_delivered(pool, msg)

        assert updated.status is MessageStatus.DELIVERED
        assert updated.delivered_at is not None


class TestRequeue:
    async def test_reencola_un_fallido(self):
        cursor = _FakeCursor()
        pool = _FakePool(cursor)
        msg = _message(status=MessageStatus.FAILED, failure_reason="x", last_error="x")

        updated = await outbox.requeue(pool, msg)

        assert updated.status is MessageStatus.QUEUED
        assert updated.failure_reason is None
        assert updated.last_error is None

    async def test_no_se_puede_reencolar_un_bounce_duro(self):
        pool = _FakePool(_FakeCursor())
        msg = _message(status=MessageStatus.BOUNCED, failure_kind="hard_bounce")

        with pytest.raises(ValueError, match="bounced"):
            await outbox.requeue(pool, msg)

    async def test_no_se_puede_reencolar_algo_ya_entregado(self):
        pool = _FakePool(_FakeCursor())
        msg = _message(status=MessageStatus.DELIVERED)

        with pytest.raises(ValueError):
            await outbox.requeue(pool, msg)
