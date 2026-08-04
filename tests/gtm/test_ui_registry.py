"""Tests de `gtm/ui/registry.py`: estado de corridas y fan-out de progreso."""

from __future__ import annotations

import asyncio

from gtm.factory.pipeline import ProgressEvent, RunContext, Stage
from gtm.ui.registry import ProgressBus, RunRegistry


def _ctx(run_id: str) -> RunContext:
    return RunContext.create("hvac", "Tucson, AZ", run_id=run_id, simulated=True)


class TestRunHandleStatus:
    def test_pending_sin_tarea_ni_resultado(self):
        from gtm.ui.registry import RunHandle

        handle = RunHandle(ctx=_ctx("r1"))
        assert handle.status == "pending"

    def test_running_con_tarea_no_terminada(self):
        from gtm.ui.registry import RunHandle

        class _FakeTask:
            def done(self):
                return False

        handle = RunHandle(ctx=_ctx("r1"), task=_FakeTask())
        assert handle.status == "running"

    def test_ok_con_resultado_exitoso(self):
        from gtm.ui.registry import RunHandle

        class _FakeResult:
            ok = True

        handle = RunHandle(ctx=_ctx("r1"), result=_FakeResult())
        assert handle.status == "ok"

    def test_failed_con_resultado_no_exitoso(self):
        from gtm.ui.registry import RunHandle

        class _FakeResult:
            ok = False

        handle = RunHandle(ctx=_ctx("r1"), result=_FakeResult())
        assert handle.status == "failed"

    def test_failed_con_error_explicito(self):
        from gtm.ui.registry import RunHandle

        handle = RunHandle(ctx=_ctx("r1"), error="places api caída")
        assert handle.status == "failed"


class TestRunRegistry:
    def test_register_y_get(self):
        registry = RunRegistry()
        ctx = _ctx("r1")
        registry.register(ctx)
        assert registry.get("r1").ctx is ctx

    def test_get_desconocido_es_none(self):
        assert RunRegistry().get("no-existe") is None

    def test_all_ordena_mas_reciente_primero(self):
        registry = RunRegistry()
        registry.register(_ctx("r1"))
        registry.register(_ctx("r2"))
        registry.register(_ctx("r3"))
        assert [h.ctx.run_id for h in registry.all()] == ["r3", "r2", "r1"]

    def test_is_busy_falso_sin_corridas(self):
        assert not RunRegistry().is_busy()

    def test_is_busy_verdadero_con_una_corriendo(self):
        class _FakeTask:
            def done(self):
                return False

        registry = RunRegistry()
        handle = registry.register(_ctx("r1"))
        handle.task = _FakeTask()
        assert registry.is_busy()

    def test_is_busy_falso_si_ya_termino(self):
        class _FakeResult:
            ok = True

        registry = RunRegistry()
        handle = registry.register(_ctx("r1"))
        handle.result = _FakeResult()
        assert not registry.is_busy()


class TestRehydrate:
    async def test_la_cola_se_rehidrata_despues_de_reiniciar(self, tmp_path):
        from gtm.factory.ledger import SuppressionList
        from gtm.factory.pipeline import run_pipeline
        from gtm.ui.routes.queue import _queue_items

        suppression = SuppressionList(tmp_path / "suppression.jsonl")
        ctx = RunContext.create(
            "plumber", "Tucson, AZ", root=tmp_path / "runs", simulated=True, limit=5, seed=42
        )
        result = await run_pipeline(ctx, suppression=suppression)

        original = RunRegistry()
        handle = original.register(ctx)
        handle.result = result
        esperado = _queue_items(original, None, suppression)
        assert esperado, "el fixture simulado tiene que producir al menos un item accionable"

        rehidratado = RunRegistry()
        rehidratado.rehydrate(tmp_path)

        obtenido = _queue_items(rehidratado, None, suppression)
        assert [item["place_id"] for item in obtenido] == [item["place_id"] for item in esperado]

    def test_no_pisa_una_corrida_ya_registrada_en_memoria(self, tmp_path):
        ctx = _ctx("r1")
        registry = RunRegistry()
        handle = registry.register(ctx)

        (tmp_path / "runs" / "r1" / "data").mkdir(parents=True)
        registry.rehydrate(tmp_path)

        assert registry.get("r1") is handle

    def test_corridas_sin_meta_json_se_saltean(self, tmp_path):
        data_dir = tmp_path / "runs" / "sin-meta" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "prospects.json").write_text("[]", encoding="utf-8")

        registry = RunRegistry()
        registry.rehydrate(tmp_path)

        assert registry.get("sin-meta") is None

    def test_rehydrate_sin_directorio_de_runs_no_lanza(self, tmp_path):
        registry = RunRegistry()
        registry.rehydrate(tmp_path / "no-existe")
        assert registry.all() == []


class TestProgressBus:
    async def test_un_suscriptor_recibe_el_evento(self):
        bus = ProgressBus()
        queue = bus.subscribe("r1")
        event = ProgressEvent(run_id="r1", stage=Stage.DISCOVER, kind="stage_start")

        bus.publish(event)

        received = await asyncio.wait_for(queue.get(), timeout=1)
        assert received is event

    async def test_no_llega_a_otro_run_id(self):
        bus = ProgressBus()
        queue = bus.subscribe("r1")
        bus.publish(ProgressEvent(run_id="r2", stage=None, kind="stage_start"))

        assert queue.empty()

    async def test_multiples_suscriptores_reciben_todos(self):
        bus = ProgressBus()
        q1 = bus.subscribe("r1")
        q2 = bus.subscribe("r1")
        event = ProgressEvent(run_id="r1", stage=None, kind="log", message="hola")

        bus.publish(event)

        assert (await asyncio.wait_for(q1.get(), timeout=1)) is event
        assert (await asyncio.wait_for(q2.get(), timeout=1)) is event

    async def test_unsubscribe_deja_de_recibir(self):
        bus = ProgressBus()
        queue = bus.subscribe("r1")
        bus.unsubscribe("r1", queue)

        bus.publish(ProgressEvent(run_id="r1", stage=None, kind="log"))

        assert queue.empty()

    def test_publish_nunca_bloquea_sin_suscriptores(self):
        """`publish` no debe levantar ni esperar si nadie está escuchando."""
        bus = ProgressBus()
        bus.publish(ProgressEvent(run_id="nadie-escucha", stage=None, kind="log"))
