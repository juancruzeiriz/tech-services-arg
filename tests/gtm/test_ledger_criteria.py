"""El código no puede apartarse del criterio pre-registrado.

Estos tests leen `gtm/decision_criteria.yaml` y verifican que `FunnelReport` implemente
exactamente esos umbrales. Sin ellos el pre-registro sería decorativo: nada impediría
mover el umbral en el código después de ver los datos, que es justamente el sesgo que
el pre-registro existe para bloquear.

Si un test de acá falla, la pregunta correcta no es "cómo lo arreglo" sino "¿por qué
cambió el criterio a mitad del experimento?".
"""

from __future__ import annotations

import pytest
import yaml

from gtm.factory.config import GTM_DIR
from gtm.factory.ledger import FunnelLedger
from gtm.factory.types import FunnelEvent


@pytest.fixture(scope="module")
def umbrales() -> dict[str, int]:
    with open(GTM_DIR / "decision_criteria.yaml", encoding="utf-8") as handle:
        criteria = yaml.safe_load(handle)
    return criteria["umbrales"]


@pytest.fixture
def funnel(tmp_path) -> FunnelLedger:
    return FunnelLedger(tmp_path / "funnel.jsonl")


def _fill(funnel: FunnelLedger, event: FunnelEvent, count: int, prefix: str = "p") -> None:
    for i in range(count):
        funnel.record(f"{prefix}{i}", event)


class TestUmbralGanador:
    def test_ventas_cobradas_coincide_con_el_pre_registro(self, funnel, umbrales):
        objetivo = umbrales["ganador_ventas_cobradas"]

        _fill(funnel, FunnelEvent.PAID, objetivo - 1)
        assert not funnel.report().has_winner, "no debería ganar por debajo del umbral"

        funnel.record("extra", FunnelEvent.PAID, amount_usd=950)
        assert funnel.report().has_winner

    def test_llamadas_agendadas_coincide_con_el_pre_registro(self, funnel, umbrales):
        objetivo = umbrales["ganador_llamadas_agendadas"]

        _fill(funnel, FunnelEvent.CALL_BOOKED, objetivo - 1)
        assert not funnel.report().has_winner

        funnel.record("extra", FunnelEvent.CALL_BOOKED)
        assert funnel.report().has_winner


class TestUmbralKill:
    def test_demos_enviadas_coincide_con_el_pre_registro(self, funnel, umbrales):
        objetivo = umbrales["kill_demos_enviadas"]

        _fill(funnel, FunnelEvent.CONTACTED, objetivo - 1)
        assert not funnel.report().kill_triggered[0], "no debería matar antes del umbral"

        funnel.record("uno_mas", FunnelEvent.CONTACTED)
        assert funnel.report().kill_triggered[0]

    def test_respuestas_minimas_coincide_con_el_pre_registro(self, funnel, umbrales):
        enviadas = umbrales["kill_demos_enviadas"]
        minimas = umbrales["kill_respuestas_minimas"]

        _fill(funnel, FunnelEvent.CONTACTED, enviadas)
        _fill(funnel, FunnelEvent.REPLIED, minimas, prefix="r")

        assert not funnel.report().kill_triggered[0], (
            f"con {minimas} respuestas el criterio no se cumple: exige < {minimas}"
        )

    def test_respuestas_sin_llamada_coincide_con_el_pre_registro(self, funnel, umbrales):
        objetivo = umbrales["kill_respuestas_sin_llamada"]

        _fill(funnel, FunnelEvent.REPLIED, objetivo - 1)
        assert not funnel.report().kill_triggered[0]

        funnel.record("uno_mas", FunnelEvent.REPLIED)
        assert funnel.report().kill_triggered[0]

    def test_una_llamada_desactiva_ese_kill(self, funnel, umbrales):
        _fill(funnel, FunnelEvent.REPLIED, umbrales["kill_respuestas_sin_llamada"])
        funnel.record("p0", FunnelEvent.CALL_BOOKED)
        assert not funnel.report().kill_triggered[0]


class TestIntegridadDelPreRegistro:
    def test_la_regla_dura_sigue_declarada(self):
        with open(GTM_DIR / "decision_criteria.yaml", encoding="utf-8") as handle:
            criteria = yaml.safe_load(handle)
        assert "no se modifica" in criteria["regla_dura"]

    def test_estan_todos_los_umbrales(self, umbrales):
        esperados = {
            "ganador_ventas_cobradas",
            "ganador_llamadas_agendadas",
            "kill_demos_enviadas",
            "kill_respuestas_minimas",
            "kill_respuestas_sin_llamada",
        }
        assert set(umbrales) == esperados

    def test_la_accion_ante_kill_no_es_reescribir(self):
        """Retocar el asunto por décima vez es la forma más común de no aceptar un no."""
        with open(GTM_DIR / "decision_criteria.yaml", encoding="utf-8") as handle:
            criteria = yaml.safe_load(handle)
        assert "no de redacción" in criteria["accion_si_kill"].lower()
