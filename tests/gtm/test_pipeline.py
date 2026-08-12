"""Tests del orquestador (`gtm/factory/pipeline.py`).

No reemplaza a `test_pipeline_stages.py`: esos prueban cada etapa en aislamiento,
estos prueban que `run_pipeline` las encadena bien -- mismos archivos que deja la
secuencia de CLI, progreso reportado, aislamiento entre corridas, y que una
corrida sin remitente no explota (outreach es opcional)."""

from __future__ import annotations

import json

import pytest

from gtm.factory.ledger import SuppressionList
from gtm.factory.pipeline import ProgressEvent, RunContext, Stage, run_pipeline
from gtm.factory.types import Language, SenderIdentity


def _sender() -> SenderIdentity:
    return SenderIdentity(
        from_name="Juan Cruz Eiriz",
        from_email="juan@example.com",
        physical_address="Av. Siempre Viva 742, Cordoba, Argentina",
        unsubscribe_url="https://example.com/unsubscribe",
    )


@pytest.fixture
def ctx(tmp_path):
    return RunContext.create(
        "hvac",
        "Tucson, AZ",
        root=tmp_path / "runs",
        simulated=True,
        limit=6,
        seed=1,
        dry_run=True,
        author_name="Test Author",
        author_url="https://example.com/about",
        base_url="https://demos.example.com",
    )


@pytest.fixture
def empty_suppression(tmp_path) -> SuppressionList:
    return SuppressionList(tmp_path / "suppression.jsonl")


class TestRunPipelineSimulado:
    async def test_corre_todas_las_etapas_sin_sender(self, ctx, empty_suppression):
        result = await run_pipeline(ctx, suppression=empty_suppression)

        assert result.ok
        stages_run = [s.stage for s in result.stages]
        assert stages_run == [
            Stage.DISCOVER,
            Stage.SCORE,
            Stage.GENERATE,
            Stage.DEPLOY,
            Stage.CONTACT,
        ]
        assert len(result.prospects) == 6
        assert len(result.scores) == 6
        # outreach nunca corrió: sin sender no hay email conforme que construir.
        assert result.emails == ()

    async def test_deja_los_mismos_artefactos_que_la_cli(self, ctx, empty_suppression):
        await run_pipeline(ctx, suppression=empty_suppression)

        for name in ("prospects.json", "scores.json", "demos.json", "contacts.json"):
            path = ctx.data_dir / name
            assert path.exists(), f"falta {name}"
            payload = json.loads(path.read_text(encoding="utf-8"))
            assert isinstance(payload, list)
            assert len(payload) > 0

        # emails.json no se escribe: no hubo sender.
        assert not (ctx.data_dir / "emails.json").exists()

    async def test_corre_outreach_con_sender(self, tmp_path, empty_suppression):
        ctx = RunContext.create(
            "plumber",
            "Tucson, AZ",
            root=tmp_path / "runs",
            simulated=True,
            limit=5,
            seed=2,
            author_name="Test Author",
            author_url="https://example.com/about",
            base_url="https://demos.example.com",
            sender=_sender(),
        )
        result = await run_pipeline(ctx, suppression=empty_suppression)

        assert result.ok
        assert result.stage_result(Stage.OUTREACH) is not None
        assert len(result.emails) > 0
        assert (ctx.data_dir / "emails.json").exists()

    async def test_idioma_se_propaga_a_la_demo(self, tmp_path, empty_suppression):
        ctx = RunContext.create(
            "hvac",
            "Tucson, AZ",
            root=tmp_path / "runs",
            simulated=True,
            limit=6,
            seed=1,
            language=Language.ES,
            author_name="Test Author",
            author_url="https://example.com/about",
            base_url="https://demos.example.com",
        )
        result = await run_pipeline(ctx, suppression=empty_suppression)

        assert result.demos, "el vertical hvac con seed=1/limit=6 debería calificar al menos una demo"
        demo_html = (ctx.demos_dir / result.demos[0].slug / "index.html").read_text(encoding="utf-8")
        assert '<html lang="es">' in demo_html

    async def test_idioma_detectado_por_prospecto_no_el_de_la_corrida(
        self, tmp_path, empty_suppression, monkeypatch
    ):
        """`ctx.language` es el default, no la imposición: si
        `lang.detect_language` encuentra una señal distinta para un
        prospecto puntual, la demo de ESE prospecto tiene que reflejarla."""
        from gtm.factory import pipeline as pipeline_mod

        ctx = RunContext.create(
            "hvac",
            "Tucson, AZ",
            root=tmp_path / "runs",
            simulated=True,
            limit=6,
            seed=1,
            language=Language.EN,
            author_name="Test",
            author_url="https://example.com",
            base_url="https://demos.example.com",
        )

        # Fuerza a que TODOS los prospectos detecten español, sin importar el
        # nombre sintético real que produzca simulate.py.
        monkeypatch.setattr(
            pipeline_mod, "detect_language", lambda prospect, *, default: Language.ES
        )

        result = await run_pipeline(ctx, suppression=empty_suppression)

        assert result.demos
        assert all(d.language is Language.ES for d in result.demos)

    async def test_ctx_language_es_el_default_pasado_a_detect_language(
        self, tmp_path, empty_suppression, monkeypatch
    ):
        from gtm.factory import pipeline as pipeline_mod

        ctx = RunContext.create(
            "hvac",
            "Tucson, AZ",
            root=tmp_path / "runs",
            simulated=True,
            limit=6,
            seed=1,
            language=Language.ES,
            author_name="Test",
            author_url="https://example.com",
            base_url="https://demos.example.com",
        )

        captured_defaults: list[Language] = []

        def _capture(prospect, *, default):
            captured_defaults.append(default)
            return default

        monkeypatch.setattr(pipeline_mod, "detect_language", _capture)

        result = await run_pipeline(ctx, suppression=empty_suppression)

        assert result.demos
        assert captured_defaults
        assert all(default is Language.ES for default in captured_defaults)

    async def test_reporta_progreso(self, ctx, empty_suppression):
        events: list[ProgressEvent] = []
        await run_pipeline(ctx, emit=events.append, suppression=empty_suppression)

        kinds_by_stage = {(e.stage, e.kind) for e in events}
        assert (Stage.DISCOVER, "stage_start") in kinds_by_stage
        assert (Stage.DISCOVER, "stage_end") in kinds_by_stage
        assert (Stage.SCORE, "stage_end") in kinds_by_stage
        assert (Stage.GENERATE, "stage_end") in kinds_by_stage
        assert (Stage.DEPLOY, "stage_end") in kinds_by_stage
        assert (Stage.CONTACT, "stage_end") in kinds_by_stage
        assert all(e.run_id == ctx.run_id for e in events)

    async def test_deploy_real_escribe_en_el_directorio_de_la_corrida_no_en_el_global(
        self, empty_suppression, tmp_path, monkeypatch
    ):
        """Con `dry_run=False`, las demos publicadas tienen que aparecer en
        `ctx.public_dir` -- nunca en el `PUBLIC_DIR` global que usa la CLI. Sin
        esto, dos corridas de la UI en paralelo se pisarían el mismo directorio."""
        import gtm.factory.deploy as deploy_mod

        fake_global_public = tmp_path / "not_this_one"
        monkeypatch.setattr(deploy_mod, "PUBLIC_DIR", fake_global_public)

        ctx = RunContext.create(
            "hvac", "Tucson, AZ", root=tmp_path / "runs", simulated=True, limit=4, seed=1,
            dry_run=False, author_name="A", author_url="https://a.example",
            base_url="https://demos.example.com",
        )
        result = await run_pipeline(ctx, suppression=empty_suppression)

        assert result.demos
        assert (ctx.public_dir / result.demos[0].slug / "index.html").exists()
        assert not fake_global_public.exists()

    async def test_dos_corridas_no_se_pisan(self, tmp_path, empty_suppression):
        root = tmp_path / "runs"
        ctx_a = RunContext.create(
            "hvac", "Tucson, AZ", root=root, simulated=True, limit=4, seed=10,
            author_name="A", author_url="https://a.example", base_url="https://demos.example.com",
        )
        ctx_b = RunContext.create(
            "plumber", "Phoenix, AZ", root=root, simulated=True, limit=4, seed=20,
            author_name="B", author_url="https://b.example", base_url="https://demos.example.com",
        )
        assert ctx_a.run_id != ctx_b.run_id
        assert ctx_a.data_dir != ctx_b.data_dir

        result_a = await run_pipeline(ctx_a, suppression=empty_suppression)
        result_b = await run_pipeline(ctx_b, suppression=empty_suppression)

        assert result_a.ok and result_b.ok
        prospects_a = json.loads((ctx_a.data_dir / "prospects.json").read_text(encoding="utf-8"))
        prospects_b = json.loads((ctx_b.data_dir / "prospects.json").read_text(encoding="utf-8"))
        assert {p["vertical"] for p in prospects_a} == {"hvac"}
        assert {p["vertical"] for p in prospects_b} == {"plumber"}

    async def test_prospecto_suprimido_no_llega_a_la_cola(self, tmp_path):
        from gtm.factory.types import SuppressionReason

        suppression = SuppressionList(tmp_path / "suppression.jsonl")
        # Simular con seed fijo primero para saber qué place_id suprimir.
        preview_ctx = RunContext.create(
            "hvac", "Tucson, AZ", root=tmp_path / "preview", simulated=True, limit=4, seed=5,
        )
        from gtm.factory.simulate import simulate as simulate_fn

        preview_prospects, _ = simulate_fn(preview_ctx.vertical, preview_ctx.metro, preview_ctx.limit, preview_ctx.seed)
        target = preview_prospects[0]
        suppression.add("place_id", target.place_id, SuppressionReason.OPTED_OUT)

        run_ctx = RunContext.create(
            "hvac", "Tucson, AZ", root=tmp_path / "runs", simulated=True, limit=4, seed=5,
            author_name="A", author_url="https://a.example", base_url="https://demos.example.com",
        )
        result = await run_pipeline(run_ctx, suppression=suppression)

        assert target.place_id not in {p.place_id for p in result.prospects}

    async def test_run_result_ok_es_false_si_una_etapa_falla(self, tmp_path, empty_suppression, monkeypatch):
        import gtm.factory.pipeline as pipeline_mod

        def _explode(*_args, **_kwargs):
            raise RuntimeError("places api caída")

        monkeypatch.setattr(pipeline_mod, "discover", _explode)
        ctx_real = RunContext.create(
            "hvac", "Tucson, AZ", root=tmp_path / "runs", simulated=False,
        )
        result = await run_pipeline(ctx_real, suppression=empty_suppression)

        assert not result.ok
        assert result.stages[0].stage is Stage.DISCOVER
        assert not result.stages[0].ok
        assert "places api caída" in (result.stages[0].error or "")


class TestPipelineMain:
    def test_main_simulado_termina_ok(self, tmp_path, monkeypatch):
        from gtm.factory import config as config_mod
        from gtm.factory import pipeline as pipeline_mod

        monkeypatch.setattr(config_mod, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(config_mod, "DEMOS_DIR", tmp_path / "build" / "demos")
        monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path / "build" / "data")

        exit_code = pipeline_mod.main(
            [
                "--vertical", "hvac",
                "--metro", "Tucson, AZ",
                "--simulate",
                "--seed", "1",
                "--limit", "4",
                "--dry-run",
                "--author-name", "Test",
                "--author-url", "https://example.com",
                "--base-url", "https://demos.example.com",
            ]
        )
        assert exit_code == 0
