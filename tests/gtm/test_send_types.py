"""Tests de la máquina de estados de envío (gtm/send/types.py)."""

from __future__ import annotations

from gtm.send.types import FailureKind, MessageStatus, OutreachMessage, SendResult


class TestTransicionesValidas:
    def test_draft_puede_pasar_a_queued(self):
        assert MessageStatus.DRAFT.can_transition_to(MessageStatus.QUEUED)

    def test_queued_puede_pasar_a_sending(self):
        assert MessageStatus.QUEUED.can_transition_to(MessageStatus.SENDING)

    def test_sending_puede_pasar_a_sent(self):
        assert MessageStatus.SENDING.can_transition_to(MessageStatus.SENT)

    def test_sending_puede_pasar_a_failed_o_bounced(self):
        assert MessageStatus.SENDING.can_transition_to(MessageStatus.FAILED)
        assert MessageStatus.SENDING.can_transition_to(MessageStatus.BOUNCED)

    def test_sent_no_puede_volver_a_queued_directo(self):
        # Un reenvío pasa por failed/bounced: reencolar algo que ya salió
        # duplicaría el mensaje al prospecto, que es el peor error posible acá.
        assert not MessageStatus.SENT.can_transition_to(MessageStatus.QUEUED)

    def test_failed_puede_reencolarse(self):
        assert MessageStatus.FAILED.can_transition_to(MessageStatus.QUEUED)

    def test_rebote_suave_puede_reencolarse(self):
        assert MessageStatus.BOUNCED.can_transition_to(MessageStatus.QUEUED)

    def test_delivered_no_transiciona_a_nada(self):
        assert not MessageStatus.DELIVERED.can_transition_to(MessageStatus.QUEUED)
        assert not MessageStatus.DELIVERED.can_transition_to(MessageStatus.SENDING)

    def test_draft_puede_ir_a_manual_pending(self):
        assert MessageStatus.DRAFT.can_transition_to(MessageStatus.MANUAL_PENDING)

    def test_manual_pending_puede_completarse(self):
        assert MessageStatus.MANUAL_PENDING.can_transition_to(MessageStatus.MANUAL_DONE)


class TestEstadosTerminales:
    def test_un_bounce_duro_es_terminal(self):
        assert MessageStatus.BOUNCED.is_terminal(hard=True)

    def test_un_bounce_suave_no_es_terminal(self):
        assert not MessageStatus.BOUNCED.is_terminal(hard=False)

    def test_delivered_manual_done_y_cancelled_son_siempre_terminales(self):
        assert MessageStatus.DELIVERED.is_terminal()
        assert MessageStatus.MANUAL_DONE.is_terminal()
        assert MessageStatus.CANCELLED.is_terminal()

    def test_queued_no_es_terminal(self):
        assert not MessageStatus.QUEUED.is_terminal()
        assert not MessageStatus.QUEUED.is_terminal(hard=True)


class TestOutreachMessage:
    def test_valores_por_defecto(self):
        msg = OutreachMessage(client_id="abc", place_id="p1", channel="email", body="hola")
        assert msg.status is MessageStatus.DRAFT
        assert msg.attempt_count == 0
        assert msg.max_attempts == 3
        assert msg.id is None


class TestSendResult:
    def test_exito_no_requiere_error(self):
        result = SendResult(success=True, provider_message_id="<abc@x>")
        assert result.error is None

    def test_fallo_lleva_el_motivo(self):
        result = SendResult(success=False, error="550 mailbox not found")
        assert not result.success


def test_failure_kind_tiene_los_cuatro_valores_esperados():
    assert {k.value for k in FailureKind} == {
        "hard_bounce", "soft_bounce", "smtp_error", "compliance",
    }
