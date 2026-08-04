"""Tests de `gtm/store/links.py`: tokens de redirección para medir aperturas.

`mint_links_for_run` se prueba contra una corrida simulada real
(`run_pipeline`), no contra fixtures armados a mano -- así el test detecta si
algún campo nuevo de `ContactPlan`/`Demo` deja de encajar."""

from __future__ import annotations

import pytest

from gtm.factory.ledger import SuppressionList
from gtm.factory.pipeline import RunContext, run_pipeline
from gtm.store import links, repo


class TestMintToken:
    def test_tokens_son_unicos(self):
        tokens = {links.mint_token() for _ in range(200)}
        assert len(tokens) == 200

    def test_token_no_tiene_caracteres_raros_para_una_url(self):
        token = links.mint_token()
        # token_urlsafe usa base64 URL-safe: letras, dígitos, "-", "_".
        assert all(c.isalnum() or c in "-_" for c in token)

    def test_token_tiene_largo_razonable(self):
        """Ni tan corto que sea adivinable, ni tan largo que rompa un SMS."""
        token = links.mint_token()
        assert 8 <= len(token) <= 20


class TestTrackedUrl:
    def test_arma_la_url_de_redireccion(self):
        assert links.tracked_url("https://demos.example.com", "abc123") == "https://demos.example.com/v/abc123"

    def test_no_duplica_la_barra_final(self):
        assert links.tracked_url("https://demos.example.com/", "abc123") == "https://demos.example.com/v/abc123"


class TestDemoLinkRow:
    def test_forma_coincide_con_table_specs(self):
        row = links.demo_link_row("tok1", "slug-abc123", "p1", "phone", run_id="run-1")
        columns, _conflict = repo.TABLE_SPECS["demo_links"]
        assert set(row) == set(columns)

    def test_run_id_es_opcional(self):
        row = links.demo_link_row("tok1", "slug-abc123", "p1", "phone")
        assert row["run_id"] is None


class TestMintLinksForRun:
    @pytest.fixture
    async def simulated_result(self, tmp_path):
        ctx = RunContext.create(
            "hvac", "Tucson, AZ", root=tmp_path / "runs", simulated=True, limit=6, seed=1,
            author_name="Test", author_url="https://example.com", base_url="https://demos.example.com",
        )
        result = await run_pipeline(
            ctx, suppression=SuppressionList(tmp_path / "suppression.jsonl")
        )
        return ctx, result

    async def test_un_token_por_plan_accionable_con_demo(self, simulated_result):
        ctx, result = simulated_result
        tokens = links.mint_links_for_run(ctx, result)

        demo_place_ids = {d.place_id for d in result.demos}
        expected = {p.place_id for p in result.contacts if p.is_actionable and p.place_id in demo_place_ids}
        assert set(tokens) == expected
        assert expected, "la corrida de prueba debería tener al menos un plan accionable"

    async def test_no_hay_token_para_planes_no_accionables(self, simulated_result):
        ctx, result = simulated_result
        tokens = links.mint_links_for_run(ctx, result)

        no_accionables = {p.place_id for p in result.contacts if not p.is_actionable}
        assert not (set(tokens) & no_accionables)

    async def test_demo_link_rows_tiene_una_fila_por_token(self, simulated_result):
        ctx, result = simulated_result
        tokens = links.mint_links_for_run(ctx, result)

        rows = links.demo_link_rows(ctx, result, tokens)

        assert len(rows) == len(tokens)
        assert {r["token"] for r in rows} == set(tokens.values())
        assert all(r["run_id"] == ctx.run_id for r in rows)

    async def test_el_canal_de_la_fila_coincide_con_el_del_plan(self, simulated_result):
        ctx, result = simulated_result
        tokens = links.mint_links_for_run(ctx, result)
        rows = links.demo_link_rows(ctx, result, tokens)

        plan_by_place_id = {p.place_id: p for p in result.contacts}
        row_by_place_id = {r["place_id"]: r for r in rows}
        for place_id, row in row_by_place_id.items():
            assert row["channel"] == plan_by_place_id[place_id].channel.value
