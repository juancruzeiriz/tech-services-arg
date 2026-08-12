"""Tests de la lista de supresión y del registro del embudo."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from gtm.factory.ledger import (
    FollowupStage,
    FunnelLedger,
    LedgerError,
    SuppressionList,
    format_report,
    hash_key,
    prospect_keys,
)
from gtm.factory.types import ContactChannel, FunnelEvent, Language, Prospect, SuppressionReason

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

    def test_filtra_por_metro(self, funnel):
        funnel.record("a", FunnelEvent.CONTACTED, metro="Tucson, AZ")
        funnel.record("b", FunnelEvent.CONTACTED, metro="Houston, TX")
        assert funnel.report(metro="Tucson, AZ").contacted == 1

    def test_filtra_por_canal(self, funnel):
        """`decision_criteria.yaml` exige poder segmentar por canal: "nadie atiende
        el teléfono" y "nadie llena el formulario" son diagnósticos distintos."""
        funnel.record("a", FunnelEvent.CONTACTED, channel=ContactChannel.PHONE)
        funnel.record("b", FunnelEvent.CONTACTED, channel=ContactChannel.CONTACT_FORM)
        assert funnel.report(channel="phone").contacted == 1
        assert funnel.report(channel="contact_form").contacted == 1

    def test_filtra_por_idioma(self, funnel):
        funnel.record("a", FunnelEvent.CONTACTED, language=Language.EN)
        funnel.record("b", FunnelEvent.CONTACTED, language=Language.ES)
        assert funnel.report(language="en").contacted == 1
        assert funnel.report(language="es").contacted == 1

    def test_acepta_enum_o_string_para_canal_e_idioma(self, funnel, tmp_path):
        """El enum y el string equivalente producen el mismo valor persistido."""
        by_enum = FunnelLedger(tmp_path / "a.jsonl")
        by_enum.record("a", FunnelEvent.CONTACTED, channel=ContactChannel.PHONE, language=Language.ES)

        by_str = FunnelLedger(tmp_path / "b.jsonl")
        by_str.record("a", FunnelEvent.CONTACTED, channel="phone", language="es")

        record_enum = json.loads((tmp_path / "a.jsonl").read_text().strip())
        record_str = json.loads((tmp_path / "b.jsonl").read_text().strip())
        assert record_enum["channel"] == record_str["channel"] == "phone"
        assert record_enum["language"] == record_str["language"] == "es"

    def test_run_id_se_persiste(self, funnel):
        funnel.record("a", FunnelEvent.CONTACTED, run_id="run-123")
        records = json.loads(funnel.path.read_text().strip())
        assert records["run_id"] == "run-123"

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

    def test_costo_por_contacto(self, funnel):
        funnel.record("a", FunnelEvent.CONTACTED)
        funnel.record("b", FunnelEvent.CONTACTED)
        funnel.record("c", FunnelEvent.CONTACTED)
        assert funnel.report(spend_usd=90).cost_per_contact == 30

    def test_sin_contactos_el_costo_por_contacto_es_none(self, funnel):
        assert funnel.report(spend_usd=90).cost_per_contact is None

    def test_niveles_en_orden(self):
        assert FunnelEvent.CONTACTED.level == 1
        assert FunnelEvent.PAID.level == 5

    def test_el_clic_no_es_un_evento(self):
        """Medir clics invitaría a decidir con ellos, que es el error original."""
        assert "click" not in {e.value for e in FunnelEvent}


class TestDueFollowups:
    """Cadencia Día 0/3/7: `due_followups` no agrega un evento de embudo nuevo
    (los cinco escalones son el compromiso pre-registrado de
    decision_criteria.yaml) -- se DERIVA de un 'contacted' sin 'replied'
    posterior de la misma clave."""

    def test_sin_contactos_no_hay_pendientes(self, funnel):
        assert funnel.due_followups() == []

    def test_contacto_reciente_no_esta_pendiente(self, funnel):
        now = datetime(2026, 8, 11, tzinfo=UTC)
        funnel.record("a", FunnelEvent.CONTACTED, at=now)
        assert funnel.due_followups(now) == []

    def test_contacto_de_3_dias_es_nudge(self, funnel):
        contacted_at = datetime(2026, 8, 1, tzinfo=UTC)
        funnel.record("a", FunnelEvent.CONTACTED, at=contacted_at)

        due = funnel.due_followups(contacted_at + timedelta(days=3))

        assert len(due) == 1
        assert due[0].stage is FollowupStage.NUDGE

    def test_contacto_de_7_dias_es_close(self, funnel):
        contacted_at = datetime(2026, 8, 1, tzinfo=UTC)
        funnel.record("a", FunnelEvent.CONTACTED, at=contacted_at)

        due = funnel.due_followups(contacted_at + timedelta(days=7))

        assert len(due) == 1
        assert due[0].stage is FollowupStage.CLOSE

    def test_contacto_de_1_dia_no_esta_pendiente(self, funnel):
        contacted_at = datetime(2026, 8, 1, tzinfo=UTC)
        funnel.record("a", FunnelEvent.CONTACTED, at=contacted_at)

        assert funnel.due_followups(contacted_at + timedelta(days=1)) == []

    def test_prospecto_que_respondio_no_aparece(self, funnel):
        contacted_at = datetime(2026, 8, 1, tzinfo=UTC)
        funnel.record("a", FunnelEvent.CONTACTED, at=contacted_at)
        funnel.record("a", FunnelEvent.REPLIED, at=contacted_at + timedelta(hours=2))

        due = funnel.due_followups(contacted_at + timedelta(days=10))

        assert due == []

    def test_devuelve_la_clave_hasheada_no_el_place_id(self, funnel):
        contacted_at = datetime(2026, 8, 1, tzinfo=UTC)
        funnel.record("some-place-id", FunnelEvent.CONTACTED, at=contacted_at)

        due = funnel.due_followups(contacted_at + timedelta(days=3))

        assert due[0].key == hash_key("place_id", "some-place-id")

    def test_un_nuevo_contacted_reabre_la_ventana(self, funnel):
        """Reintentar un prospecto (CONTACTED es válido de nuevo, a
        diferencia de OPTED_OUT) tiene que resetear el conteo de días."""
        first_contact = datetime(2026, 8, 1, tzinfo=UTC)
        funnel.record("a", FunnelEvent.CONTACTED, at=first_contact)

        second_contact = datetime(2026, 8, 10, tzinfo=UTC)
        funnel.record("a", FunnelEvent.CONTACTED, at=second_contact)

        assert funnel.due_followups(second_contact + timedelta(days=1)) == []

    def test_umbrales_configurables(self, funnel):
        contacted_at = datetime(2026, 8, 1, tzinfo=UTC)
        funnel.record("a", FunnelEvent.CONTACTED, at=contacted_at)

        due = funnel.due_followups(
            contacted_at + timedelta(days=2), nudge_after_days=1, close_after_days=5
        )

        assert due[0].stage is FollowupStage.NUDGE


class TestCriterioPreRegistrado:
    """Umbrales v2 (ver el comentario inicial de decision_criteria.yaml para el porqué
    del re-registro): kill a 200 contactados sin ventas y con pocas respuestas; la vía
    de "ganador por llamadas agendadas" de v1 se retiró por ser estadísticamente
    inalcanzable al volumen del experimento."""

    def test_una_venta_es_ganador(self, funnel):
        funnel.record("a", FunnelEvent.PAID, amount_usd=950)
        assert funnel.report().has_winner

    def test_llamadas_agendadas_solas_no_son_ganador(self, funnel):
        """Vía retirada en v2: ninguna cantidad de llamadas agendadas, sin una venta
        cobrada, alcanza para `has_winner`."""
        for pid in ("a", "b", "c", "d", "e"):
            funnel.record(pid, FunnelEvent.CALL_BOOKED)
        assert not funnel.report().has_winner

    def test_kill_por_volumen_sin_ventas_ni_respuestas(self, funnel):
        for i in range(200):
            funnel.record(f"p{i}", FunnelEvent.CONTACTED)
        funnel.record("p0", FunnelEvent.REPLIED)

        killed, motivo = funnel.report().kill_triggered
        assert killed
        assert "200 contactados" in motivo

    def test_no_mata_antes_del_umbral(self, funnel):
        for i in range(199):
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
        for i in range(200):
            funnel.record(f"p{i}", FunnelEvent.CONTACTED)

        output = format_report(funnel.report())
        assert "KILL" in output
        assert "NO de redacción" in output

    def test_el_reporte_muestra_lo_que_falta_cuando_esta_en_curso(self, funnel):
        for i in range(20):
            funnel.record(f"p{i}", FunnelEvent.CONTACTED)

        output = format_report(funnel.report())
        assert "Faltan 180 contactos" in output

    def test_el_ganador_tiene_prioridad_sobre_el_kill(self, funnel):
        """Con una venta cobrada, que falten respuestas es irrelevante: la venta
        también desactiva la rama de kill por volumen (exige `ventas_cobradas == 0`)."""
        for i in range(200):
            funnel.record(f"p{i}", FunnelEvent.CONTACTED)
        funnel.record("p0", FunnelEvent.PAID, amount_usd=950)

        report = funnel.report()
        assert not report.kill_triggered[0]
        output = format_report(report)
        assert "GANADOR" in output
        assert "KILL" not in output
