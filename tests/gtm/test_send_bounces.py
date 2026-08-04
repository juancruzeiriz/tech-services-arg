"""Tests del parser de rebotes RFC 3464 (gtm/send/bounces.py)."""

from __future__ import annotations

from gtm.send import bounces
from gtm.send.types import FailureKind

_DSN_DURO = """From: MAILER-DAEMON@mx.example.com
To: bounces+abc123@envio.example
Content-Type: multipart/report; report-type=delivery-status; boundary="b"

--b
Content-Type: text/plain

Tu mensaje no pudo ser entregado.
--b
Content-Type: message/delivery-status

Reporting-MTA: dns; mx.example.com

Final-Recipient: rfc822; info@plomeria.com
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown
--b--
"""

_RESPUESTA_HUMANA = """From: dueno@plomeria.example
To: bounces+abc123@envio.example
Subject: Re: Hice un sitio de muestra
Content-Type: text/plain

Hola, me interesa. Llamame.
"""


class TestParseDsn:
    def test_reconoce_un_rebote_duro_por_el_status_5xx(self):
        report = bounces.parse_dsn(_DSN_DURO)
        assert report is not None
        assert report.kind is FailureKind.HARD_BOUNCE
        assert report.recipient == "info@plomeria.com"

    def test_un_4xx_es_rebote_suave(self):
        dsn_suave = _DSN_DURO.replace("Status: 5.1.1", "Status: 4.2.2").replace(
            "550 5.1.1 User unknown", "452 4.2.2 Mailbox full"
        )
        report = bounces.parse_dsn(dsn_suave)
        assert report is not None
        assert report.kind is FailureKind.SOFT_BOUNCE

    def test_extrae_el_smtp_code_del_diagnostic_code(self):
        report = bounces.parse_dsn(_DSN_DURO)
        assert report is not None
        assert report.smtp_code == 550

    def test_un_mail_que_no_es_un_dsn_devuelve_none(self):
        # La casilla de rebotes va a recibir respuestas humanas reales.
        # Tratarlas como rebotes suprimiría justo a los prospectos que SÍ
        # contestaron -- el evento más valioso del embudo entero.
        assert bounces.parse_dsn(_RESPUESTA_HUMANA) is None

    def test_un_texto_cualquiera_no_lanza(self):
        assert bounces.parse_dsn("esto no es ni siquiera un email") is None

    def test_dsn_sin_status_reconocible_se_trata_como_transitorio(self):
        dsn_sin_status = _DSN_DURO.replace("Status: 5.1.1\n", "").replace(
            "Diagnostic-Code: smtp; 550 5.1.1 User unknown", "Diagnostic-Code: smtp; unknown error"
        )
        report = bounces.parse_dsn(dsn_sin_status)
        assert report is not None
        assert report.kind is FailureKind.SOFT_BOUNCE  # nunca se asume terminal sin evidencia


class TestVerpTagFrom:
    def test_extrae_el_tag(self):
        assert bounces.verp_tag_from("bounces+abc123@envio.example") == "abc123"

    def test_direccion_sin_tag_devuelve_none(self):
        assert bounces.verp_tag_from("bounces@envio.example") is None

    def test_ignora_el_nombre_para_mostrar(self):
        assert bounces.verp_tag_from("MAILER-DAEMON <bounces+xyz@envio.example>") == "xyz"


class TestClassifyInbound:
    def test_un_dsn_se_clasifica_como_tal_no_como_respuesta(self):
        result = bounces.classify_inbound(_DSN_DURO)
        assert result.is_dsn
        assert not result.is_human_reply
        assert result.bounce is not None

    def test_una_respuesta_humana_se_marca_como_posible_reply(self):
        result = bounces.classify_inbound(_RESPUESTA_HUMANA)
        assert result.is_human_reply
        assert not result.is_dsn
        assert result.bounce is None

    def test_extrae_el_verp_tag_del_destinatario_del_rebote(self):
        result = bounces.classify_inbound(_DSN_DURO)
        assert result.verp_tag == "abc123"


class TestFetchUnseen:
    def test_trae_el_texto_crudo_de_cada_mensaje_no_leido(self, monkeypatch):
        class _FakeImap:
            def __init__(self, host, port, timeout=None):
                pass

            def login(self, user, password):
                pass

            def select(self, mailbox):
                pass

            def search(self, charset, criteria):
                return ("OK", [b"1 2"])

            def fetch(self, msg_id, parts):
                body = _DSN_DURO if msg_id == b"1" else _RESPUESTA_HUMANA
                return ("OK", [(b"1 (RFC822 {n})", body.encode("utf-8"))])

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(bounces.imaplib, "IMAP4_SSL", _FakeImap)

        messages = bounces.fetch_unseen(host="imap.example.com", port=993, username="u", password="p")

        assert len(messages) == 2
        assert "MAILER-DAEMON" in messages[0]

    def test_busqueda_fallida_devuelve_lista_vacia(self, monkeypatch):
        class _FakeImapSinResultados:
            def __init__(self, *_a, **_k):
                pass

            def login(self, *_a, **_k):
                pass

            def select(self, *_a, **_k):
                pass

            def search(self, *_a, **_k):
                return ("NO", [])

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(bounces.imaplib, "IMAP4_SSL", _FakeImapSinResultados)

        assert bounces.fetch_unseen(host="imap.example.com", port=993, username="u", password="p") == []
