"""Tests del worker de envío (gtm/send/worker.py). Todas las piezas de más
abajo (outbox, smtp, bounces, config) ya están probadas por su cuenta; acá
solo se prueba la orquestación: qué llama a qué, en qué orden, y que un
fallo puntual no tumbe el loop."""

from __future__ import annotations

import asyncio
import json

import pytest

from gtm.factory.types import ComplianceError, SenderIdentity
from gtm.send import worker as worker_mod
from gtm.send.bounces import BounceReport, InboundClassification
from gtm.send.types import FailureKind, OutreachMessage, SendResult, SmtpSettings


@pytest.fixture(autouse=True)
def _isolate_ledger(tmp_path, monkeypatch):
    """`_send_one`/`_process_inbound` escriben en el ledger local de verdad
    (`FunnelLedger`/`SuppressionList` sin `path` explícito) -- sin esto, correr
    estos tests escribiría en `gtm/funnel.jsonl`/`gtm/suppression.jsonl`, el
    mismo ledger que se commitea a git y del que depende el criterio
    pre-registrado en `gtm/decision_criteria.yaml`."""
    from gtm.factory import ledger as ledger_mod

    monkeypatch.setattr(ledger_mod, "FUNNEL_PATH", tmp_path / "funnel.jsonl")
    monkeypatch.setattr(ledger_mod, "SUPPRESSION_PATH", tmp_path / "suppression.jsonl")
    return tmp_path

_SENDER = SenderIdentity(
    from_name="Juan Cruz", from_email="juan@envio.example",
    physical_address="1234 Main St, Tucson, AZ 85701", unsubscribe_url="https://envio.example/unsub",
)
_SETTINGS = SmtpSettings(
    host="smtp.example.com", port=465, username="juan@envio.example",
    password="x", bounce_address="bounces@envio.example",
)


def _message(**overrides) -> OutreachMessage:
    defaults = {
        "client_id": "c1", "place_id": "p1", "channel": "email", "body": "cuerpo",
        "to_address": "prospecto@negocio.example", "subject": "asunto",
    }
    defaults.update(overrides)
    return OutreachMessage(**defaults)


class TestStartWorker:
    def test_sin_pool_devuelve_none(self):
        assert worker_mod.start_worker(None) is None

    def test_con_pool_devuelve_un_worker_arrancado(self, monkeypatch):
        started = {}
        monkeypatch.setattr(worker_mod.Worker, "start", lambda self: started.setdefault("ok", True))

        result = worker_mod.start_worker(object())

        assert result is not None
        assert started.get("ok")


class TestWorkerStop:
    async def test_cancela_las_tareas_sin_lanzar(self):
        w = worker_mod.Worker(pool=object())

        async def _never_ending():
            await asyncio.sleep(3600)

        w._tasks = [asyncio.create_task(_never_ending()), asyncio.create_task(_never_ending())]
        await w.stop()

        assert w._tasks == []


class TestLoop:
    async def test_un_fallo_no_detiene_el_loop(self):
        # interval=0: cada vuelta hace un asyncio.sleep(0) real, que no
        # bloquea pero sí le da un turno al scheduler -- no hace falta
        # parchear asyncio.sleep (mutaría el módulo global compartido, que
        # es el mismo objeto que usa este propio test para ceder turnos).
        calls = {"n": 0}

        async def _fails_once():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")

        w = worker_mod.Worker(pool=object())
        task = asyncio.create_task(w._loop(_fails_once, 0))
        for _ in range(20):
            await asyncio.sleep(0)
            if calls["n"] >= 2:
                break
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert calls["n"] >= 2  # sobrevivió al primer fallo y siguió iterando


class TestRunSendBatch:
    async def test_sin_mensajes_no_llama_a_config(self, monkeypatch):
        called = []
        monkeypatch.setattr(worker_mod.outbox, "claim_due", _async_return([]))
        monkeypatch.setattr(worker_mod.config, "load_smtp_settings", lambda: called.append("smtp"))

        w = worker_mod.Worker(pool=object())
        await w.run_send_batch()

        assert called == []

    async def test_manda_cada_mensaje_y_espera_jitter_entre_ellos(self, monkeypatch):
        messages = [_message(client_id="a"), _message(client_id="b")]
        sleeps = []

        monkeypatch.setattr(worker_mod.outbox, "claim_due", _async_return(messages))
        monkeypatch.setattr(worker_mod.config, "load_smtp_settings", lambda: _SETTINGS)
        monkeypatch.setattr(worker_mod.config, "load_sender_identity", lambda: _SENDER)
        monkeypatch.setattr(worker_mod, "asyncio", _FakeAsyncioModule(sleeps))

        w = worker_mod.Worker(pool=object())
        sent = []
        w._send_one = _record_send(sent)  # type: ignore[method-assign]

        await w.run_send_batch()

        assert [m.client_id for m in sent] == ["a", "b"]
        assert len(sleeps) == 1  # jitter solo ENTRE mensajes, no después del último


def _record_send(sink):
    async def _inner(message, _settings, _sender):
        sink.append(message)

    return _inner


class _FakeAsyncioModule:
    """Envuelve el `asyncio` real pero registra los `sleep()` en vez de
    esperar de verdad -- el jitter real es de 60-180s por diseño."""

    def __init__(self, sleeps: list[float]) -> None:
        self._sleeps = sleeps
        self._real = asyncio

    async def sleep(self, seconds):
        self._sleeps.append(seconds)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _async_return(value):
    async def _inner(*_a, **_k):
        return value

    return _inner


class TestSendOne:
    async def test_canal_no_email_se_ignora(self, monkeypatch):
        marked = []
        monkeypatch.setattr(worker_mod.outbox, "mark_sent", _record(marked, "sent"))
        monkeypatch.setattr(worker_mod.outbox, "mark_failed", _record(marked, "failed"))

        w = worker_mod.Worker(pool=object())
        await w._send_one(_message(channel="phone"), _SETTINGS, _SENDER)

        assert marked == []

    async def test_sin_direccion_marca_fallido(self, monkeypatch):
        marked = []
        monkeypatch.setattr(worker_mod.outbox, "mark_failed", _record(marked, "failed"))

        w = worker_mod.Worker(pool=object())
        await w._send_one(_message(to_address=None), _SETTINGS, _SENDER)

        assert marked == [("failed", "c1")]

    async def test_compliance_fallido_marca_failure_kind_compliance(self, monkeypatch):
        marked = []

        def _raise(*_a, **_k):
            raise ComplianceError("sin baja")

        monkeypatch.setattr(worker_mod.smtp, "revalidate_before_send", _raise)
        monkeypatch.setattr(worker_mod.outbox, "mark_failed", _record_kwargs(marked))

        w = worker_mod.Worker(pool=object())
        await w._send_one(_message(), _SETTINGS, _SENDER)

        assert marked[0]["kind"] is FailureKind.COMPLIANCE

    async def test_envio_exitoso_marca_sent_con_el_verp_tag(self, monkeypatch):
        marked = []
        monkeypatch.setattr(worker_mod.smtp, "revalidate_before_send", lambda *_a, **_k: None)
        monkeypatch.setattr(worker_mod.smtp, "send_async", _async_return(SendResult(success=True, provider_message_id="<x@y>")))
        monkeypatch.setattr(worker_mod.outbox, "mark_sent", _record_kwargs(marked))

        w = worker_mod.Worker(pool=object())
        await w._send_one(_message(), _SETTINGS, _SENDER)

        assert marked[0]["provider_message_id"] == "<x@y>"
        assert marked[0]["verp_tag"]

    async def test_envio_fallido_marca_failed(self, monkeypatch):
        marked = []
        monkeypatch.setattr(worker_mod.smtp, "revalidate_before_send", lambda *_a, **_k: None)
        monkeypatch.setattr(worker_mod.smtp, "send_async", _async_return(SendResult(success=False, error="timeout")))
        monkeypatch.setattr(worker_mod.outbox, "mark_failed", _record_kwargs(marked))

        w = worker_mod.Worker(pool=object())
        await w._send_one(_message(), _SETTINGS, _SENDER)

        assert marked[0]["error"] == "timeout"

    async def test_envio_exitoso_registra_contactado_en_el_embudo(self, monkeypatch, _isolate_ledger):
        # Con envío automático el clic manual de "Contactado" en /queue sobra
        # -- sin este registro automático, el embudo subregistraría cada
        # mensaje que salió por el worker en vez de por la cola manual.
        monkeypatch.setattr(worker_mod.smtp, "revalidate_before_send", lambda *_a, **_k: None)
        monkeypatch.setattr(worker_mod.smtp, "send_async", _async_return(SendResult(success=True, provider_message_id="<x@y>")))
        monkeypatch.setattr(worker_mod.outbox, "mark_sent", _async_return(None))

        w = worker_mod.Worker(pool=object())
        await w._send_one(_message(place_id="p1", channel="email", run_id="r1"), _SETTINGS, _SENDER)

        funnel_path = _isolate_ledger / "funnel.jsonl"
        assert funnel_path.exists()
        record = json.loads(funnel_path.read_text(encoding="utf-8").strip())
        assert record["event"] == "contacted"
        assert record["run_id"] == "r1"
        assert record["channel"] == "email"

    async def test_envio_fallido_no_registra_contactado(self, monkeypatch, _isolate_ledger):
        monkeypatch.setattr(worker_mod.smtp, "revalidate_before_send", lambda *_a, **_k: None)
        monkeypatch.setattr(worker_mod.smtp, "send_async", _async_return(SendResult(success=False, error="timeout")))
        monkeypatch.setattr(worker_mod.outbox, "mark_failed", _async_return(None))

        w = worker_mod.Worker(pool=object())
        await w._send_one(_message(), _SETTINGS, _SENDER)

        assert not (_isolate_ledger / "funnel.jsonl").exists()


def _record(sink, label):
    async def _inner(_pool, message, **kwargs):
        sink.append((label, getattr(message, "client_id", None)))

    return _inner


def _record_kwargs(sink):
    async def _inner(_pool, _message, **kwargs):
        sink.append(kwargs)

    return _inner


class TestRunBounceCheck:
    async def test_una_respuesta_humana_no_toca_el_outbox(self, monkeypatch):
        touched = []
        monkeypatch.setattr(worker_mod.config, "load_imap_settings", lambda: _imap_settings())
        monkeypatch.setattr(worker_mod.asyncio, "to_thread", _async_return(["mensaje crudo"]))
        monkeypatch.setattr(
            worker_mod.bounces, "classify_inbound",
            lambda _raw: InboundClassification(is_dsn=False, is_human_reply=True, bounce=None, verp_tag=None, in_reply_to=None),
        )
        monkeypatch.setattr(worker_mod.outbox, "get_by_verp_tag", _record(touched, "lookup"))

        w = worker_mod.Worker(pool=object())
        await w.run_bounce_check()

        assert touched == []

    async def test_un_rebote_duro_marca_bounced_hard(self, monkeypatch):
        marked = []
        message = _message()
        classification = InboundClassification(
            is_dsn=True, is_human_reply=False,
            bounce=BounceReport(kind=FailureKind.HARD_BOUNCE, recipient="x@y.com", detail="550", smtp_code=550),
            verp_tag="tag123", in_reply_to=None,
        )
        monkeypatch.setattr(worker_mod.config, "load_imap_settings", lambda: _imap_settings())
        monkeypatch.setattr(worker_mod.asyncio, "to_thread", _async_return(["mensaje crudo"]))
        monkeypatch.setattr(worker_mod.bounces, "classify_inbound", lambda _raw: classification)
        monkeypatch.setattr(worker_mod.outbox, "get_by_verp_tag", _async_return(message))
        monkeypatch.setattr(worker_mod.outbox, "mark_bounced", _record_bounced(marked))

        w = worker_mod.Worker(pool=object())
        await w.run_bounce_check()

        assert marked[0]["hard"] is True

    async def test_un_rebote_duro_suprime_al_prospecto(self, monkeypatch, _isolate_ledger):
        # Reintentar contra una dirección muerta sube la tasa de rebote, que
        # es lo que más rápido quema la reputación del dominio de envío.
        from gtm.factory.ledger import hash_key

        message = _message(place_id="p-bounced")
        classification = InboundClassification(
            is_dsn=True, is_human_reply=False,
            bounce=BounceReport(kind=FailureKind.HARD_BOUNCE, recipient="x@y.com", detail="550", smtp_code=550),
            verp_tag="tag123", in_reply_to=None,
        )
        monkeypatch.setattr(worker_mod.config, "load_imap_settings", lambda: _imap_settings())
        monkeypatch.setattr(worker_mod.asyncio, "to_thread", _async_return(["mensaje crudo"]))
        monkeypatch.setattr(worker_mod.bounces, "classify_inbound", lambda _raw: classification)
        monkeypatch.setattr(worker_mod.outbox, "get_by_verp_tag", _async_return(message))
        monkeypatch.setattr(worker_mod.outbox, "mark_bounced", _async_return(message))

        w = worker_mod.Worker(pool=object())
        await w.run_bounce_check()

        suppression_path = _isolate_ledger / "suppression.jsonl"
        assert suppression_path.exists()
        record = json.loads(suppression_path.read_text(encoding="utf-8").strip())
        assert record["key"] == hash_key("place_id", "p-bounced")
        assert record["reason"] == "bounced"

    async def test_un_rebote_suave_no_suprime(self, monkeypatch, _isolate_ledger):
        message = _message(place_id="p-soft")
        classification = InboundClassification(
            is_dsn=True, is_human_reply=False,
            bounce=BounceReport(kind=FailureKind.SOFT_BOUNCE, recipient="x@y.com", detail="450", smtp_code=450),
            verp_tag="tag123", in_reply_to=None,
        )
        monkeypatch.setattr(worker_mod.config, "load_imap_settings", lambda: _imap_settings())
        monkeypatch.setattr(worker_mod.asyncio, "to_thread", _async_return(["mensaje crudo"]))
        monkeypatch.setattr(worker_mod.bounces, "classify_inbound", lambda _raw: classification)
        monkeypatch.setattr(worker_mod.outbox, "get_by_verp_tag", _async_return(message))
        monkeypatch.setattr(worker_mod.outbox, "mark_bounced", _async_return(message))

        w = worker_mod.Worker(pool=object())
        await w.run_bounce_check()

        assert not (_isolate_ledger / "suppression.jsonl").exists()


def _record_bounced(sink):
    async def _inner(_pool, _message, **kwargs):
        sink.append(kwargs)

    return _inner


def _imap_settings():
    from gtm.send.types import ImapSettings

    return ImapSettings(host="imap.example.com", port=993, username="u", password="p")


class TestRunDeliveryCheck:
    async def test_marca_delivered_cada_mensaje_abierto(self, monkeypatch):
        opened = [_message(client_id="a"), _message(client_id="b")]
        marked = []
        monkeypatch.setattr(worker_mod.outbox, "find_opened_but_not_delivered", _async_return(opened))
        monkeypatch.setattr(worker_mod.outbox, "mark_delivered", _record(marked, "delivered"))

        w = worker_mod.Worker(pool=object())
        await w.run_delivery_check()

        assert [c[1] for c in marked] == ["a", "b"]
