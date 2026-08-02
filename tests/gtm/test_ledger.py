"""Tests de la lista de supresión y del registro del embudo."""

from __future__ import annotations

import json

import pytest

from gtm.factory.ledger import (
    FunnelLedger,
    LedgerError,
    SuppressionList,
    format_report,
    hash_key,
    prospect_keys,
)
from gtm.factory.types import FunnelEvent, Prospect, SuppressionReason

PHONE = "(520) 555-0148"


def _prospect(**kwargs) -> Prospect:
    defaults = {
        "place_id": "ChIJabc123",
        "name": "Sonoran Air Conditioning",
        "vertical": "hvac",
        "metro": "Tucson, AZ",
        "phone": PHONE,
    }
    return Prospect(**{**defaults, **kwargs})


@pytest.fixture
def suppression(tmp_path) -> SuppressionList:
    return SuppressionList(tmp_path / "suppression.jsonl")


@pytest.fixture
def funnel(tmp_path) -> FunnelLedger:
    return FunnelLedger(tmp_path / "funnel.jsonl")


class TestHashKey:
    def test_normaliza_telefonos_equivalentes(self):
        assert hash_key("phone", "(520) 555-0148") == hash_key("phone", "520-555-0148")
        assert hash_key("phone", "+1 520 555 0148") == hash_key("phone", "15205550148")

    def test_normaliza_dominios(self):
        assert hash_key("domain", "https://www.Sonoran.com/contact") == hash_key(
            "domain", "sonoran.com"
        )

    def test_kind_evita_colisiones(self):
        """Un place_id y un teléfono con el mismo texto no son el mismo negocio."""
        assert hash_key("place_id", "5205550148") != hash_key("phone", "5205550148")

    def test_valor_vacio_falla(self):
        with pytest.raises(LedgerError, match="vacío"):
            hash_key("phone", "no-tiene-digitos")

    def test_es_estable_entre_llamadas(self):
        assert hash_key("place_id", "ChIJabc") == hash_key("place_id", "ChIJabc")


class TestPrivacidad:
    """El archivo va a git: no puede contener nada que identifique al negocio."""

    def test_el_archivo_no_guarda_datos_personales(self, tmp_path):
        path = tmp_path / "suppression.jsonl"
        suppression = SuppressionList(path)
        prospect = _prospect()
        suppression.suppress_prospect(prospect, SuppressionReason.OPTED_OUT)

        raw = path.read_text(encoding="utf-8")
        assert prospect.name not in raw
        assert prospect.place_id not in raw
        assert PHONE not in raw
        assert "5205550148" not in raw

    def test_cada_linea_es_json_valido(self, tmp_path):
        path = tmp_path / "suppression.jsonl"
        suppression = SuppressionList(path)
        suppression.add("place_id", "a", SuppressionReason.CONTACTED)
        suppression.add("place_id", "b", SuppressionReason.OPTED_OUT)

        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == 2
        for line in lines:
            assert set(json.loads(line)) >= {"key", "kind", "reason", "at"}


class TestSuppressionList:
    def test_bloquea_por_place_id(self, suppression):
        prospect = _prospect()
        suppression.add("place_id", prospect.place_id, SuppressionReason.OPTED_OUT)
        assert suppression.contains(prospect)
        assert suppression.reason_for(prospect) is SuppressionReason.OPTED_OUT

    def test_bloquea_por_telefono_aunque_cambie_el_place_id(self, suppression):
        """Google reemite place_ids; el teléfono es el identificador que sobrevive."""
        suppression.add("phone", PHONE, SuppressionReason.OPTED_OUT)
        reaparecido = _prospect(place_id="ChIJotroIdCompletamenteDistinto")
        assert suppression.contains(reaparecido)

    def test_bloquea_por_dominio(self, suppression):
        suppression.add("domain", "sonoran.com", SuppressionReason.NOT_INTERESTED)
        prospect = _prospect(place_id="otro", phone=None, website="https://www.sonoran.com")
        assert suppression.contains(prospect)

    def test_no_bloquea_a_un_desconocido(self, suppression):
        suppression.add("place_id", "otro", SuppressionReason.OPTED_OUT)
        assert not suppression.contains(_prospect())

    def test_filter_out_separa_ambos_grupos(self, suppression):
        bloqueado = _prospect(place_id="malo", phone="(520) 555-0100")
        libre = _prospect(place_id="bueno", phone="(520) 555-0200")
        suppression.add("place_id", "malo", SuppressionReason.OPTED_OUT)

        allowed, blocked = suppression.filter_out([bloqueado, libre])

        assert [p.place_id for p in allowed] == ["bueno"]
        assert [p.place_id for p in blocked] == ["malo"]

    def test_persiste_entre_instancias(self, tmp_path):
        path = tmp_path / "suppression.jsonl"
        SuppressionList(path).add("place_id", "ChIJabc123", SuppressionReason.OPTED_OUT)
        # Nueva instancia = nueva corrida, potencialmente en otra máquina.
        assert SuppressionList(path).contains(_prospect())

    def test_linea_corrupta_no_invalida_el_resto(self, tmp_path):
        """Perder la lista entera significaría re-contactar a todo el mundo."""
        path = tmp_path / "suppression.jsonl"
        SuppressionList(path).add("place_id", "ChIJabc123", SuppressionReason.OPTED_OUT)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("{esto no es json\n")

        assert SuppressionList(path).contains(_prospect())

    def test_opted_out_es_permanente(self):
        assert SuppressionReason.OPTED_OUT.is_permanent
        assert SuppressionReason.CUSTOMER.is_permanent
        assert not SuppressionReason.CONTACTED.is_permanent

    def test_prospecto_sin_telefono_ni_sitio_solo_usa_place_id(self):
        keys = prospect_keys(_prospect(phone=None, website=None))
        assert len(keys) == 1


class TestFunnelLedger:
    def test_cuenta_cada_escalon(self, funnel):
        funnel.record("a", FunnelEvent.CONTACTED)
        funnel.record("b", FunnelEvent.CONTACTED)
        funnel.record("a", FunnelEvent.REPLIED)
        funnel.record("a", FunnelEvent.CALL_BOOKED)

        report = funnel.report()

        assert report.contacted == 2
        assert report.replied == 1
        assert report.calls_booked == 1
        assert report.unique_prospects == 2

    def test_no_cuenta_dos_veces_el_mismo_escalon(self, funnel):
        """Dos respuestas del mismo negocio son una sola respuesta."""
        funnel.record("a", FunnelEvent.REPLIED)
        funnel.record("a", FunnelEvent.REPLIED)
        assert funnel.report().replied == 1

    def test_acumula_ingresos(self, funnel):
        funnel.record("a", FunnelEvent.PAID, amount_usd=950)
        funnel.record("b", FunnelEvent.PAID, amount_usd=1200)
        assert funnel.report().revenue_usd == 2150

    def test_filtra_por_vertical(self, funnel):
        funnel.record("a", FunnelEvent.CONTACTED, vertical="hvac")
        funnel.record("b", FunnelEvent.CONTACTED, vertical="plumber")
        assert funnel.report(vertical="hvac").contacted == 1

    def test_reply_rate(self, funnel):
        for i in range(10):
            funnel.record(f"p{i}", FunnelEvent.CONTACTED)
        funnel.record("p0", FunnelEvent.REPLIED)
        funnel.record("p1", FunnelEvent.REPLIED)
        assert funnel.report().reply_rate == pytest.approx(0.2)

    def test_costo_por_llamada(self, funnel):
        funnel.record("a", FunnelEvent.CALL_BOOKED)
        funnel.record("b", FunnelEvent.CALL_BOOKED)
        assert funnel.report(spend_usd=150).cost_per_call == 75

    def test_sin_llamadas_el_costo_es_none(self, funnel):
        """None, no cero ni división por cero: todavía no hay dato."""
        assert funnel.report(spend_usd=150).cost_per_call is None

    def test_niveles_en_orden(self):
        assert FunnelEvent.CONTACTED.level == 1
        assert FunnelEvent.PAID.level == 5

    def test_el_clic_no_es_un_evento(self):
        """Medir clics invitaría a decidir con ellos, que es el error original."""
        assert "click" not in {e.value for e in FunnelEvent}


class TestCriterioPreRegistrado:
    def test_una_venta_es_ganador(self, funnel):
        funnel.record("a", FunnelEvent.PAID, amount_usd=950)
        assert funnel.report().has_winner

    def test_tres_llamadas_es_ganador(self, funnel):
        for pid in ("a", "b", "c"):
            funnel.record(pid, FunnelEvent.CALL_BOOKED)
        assert funnel.report().has_winner

    def test_dos_llamadas_todavia_no(self, funnel):
        for pid in ("a", "b"):
            funnel.record(pid, FunnelEvent.CALL_BOOKED)
        assert not funnel.report().has_winner

    def test_kill_por_falta_de_respuestas(self, funnel):
        for i in range(60):
            funnel.record(f"p{i}", FunnelEvent.CONTACTED)
        funnel.record("p0", FunnelEvent.REPLIED)

        killed, motivo = funnel.report().kill_triggered
        assert killed
        assert "60 contactados" in motivo

    def test_no_mata_antes_del_umbral(self, funnel):
        for i in range(59):
            funnel.record(f"p{i}", FunnelEvent.CONTACTED)
        assert not funnel.report().kill_triggered[0]

    def test_kill_por_interes_que_no_llega_a_llamada(self, funnel):
        for i in range(10):
            funnel.record(f"p{i}", FunnelEvent.CONTACTED)
            funnel.record(f"p{i}", FunnelEvent.REPLIED)

        killed, motivo = funnel.report().kill_triggered
        assert killed
        assert "ninguna llamada" in motivo

    def test_el_reporte_dice_cambiar_vertical_no_redaccion(self, funnel):
        for i in range(60):
            funnel.record(f"p{i}", FunnelEvent.CONTACTED)

        output = format_report(funnel.report())
        assert "KILL" in output
        assert "NO de redacción" in output

    def test_el_reporte_muestra_lo_que_falta_cuando_esta_en_curso(self, funnel):
        for i in range(20):
            funnel.record(f"p{i}", FunnelEvent.CONTACTED)

        output = format_report(funnel.report())
        assert "Faltan 40 contactos" in output

    def test_el_ganador_tiene_prioridad_sobre_el_kill(self, funnel):
        """Con una venta cobrada, que falten respuestas es irrelevante."""
        for i in range(60):
            funnel.record(f"p{i}", FunnelEvent.CONTACTED)
        funnel.record("p0", FunnelEvent.PAID, amount_usd=950)

        output = format_report(funnel.report())
        assert "GANADOR" in output
        assert "KILL" not in output
