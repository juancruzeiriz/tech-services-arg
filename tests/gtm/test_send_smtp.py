"""Tests de envío SMTP (gtm/send/smtp.py): VERP, RFC 8058, multipart, y la
re-validación de compliance antes de cada intento."""

from __future__ import annotations

import smtplib

import pytest

from gtm.factory.types import ComplianceError, SenderIdentity
from gtm.send import smtp as smtp_mod
from gtm.send.types import SmtpSettings

_SENDER = SenderIdentity(
    from_name="Juan Cruz",
    from_email="juan@envio.example",
    physical_address="1234 Main St, Tucson, AZ 85701",
    unsubscribe_url="https://envio.example/unsub",
)

_SETTINGS = SmtpSettings(
    host="smtp.example.com", port=465, username="juan@envio.example",
    password="x", bounce_address="bounces@envio.example",
)

_BODY_CONFORME = (
    "Hola.\n\n"
    "This is a commercial message from an independent web developer.\n"
    "1234 Main St, Tucson, AZ 85701\n"
    "https://envio.example/unsub\n"
)


class TestEnvelopeFrom:
    def test_arma_la_direccion_verp(self):
        assert smtp_mod.envelope_from("bounces@envio.example", "abc123") == "bounces+abc123@envio.example"

    def test_tags_distintos_dan_direcciones_distintas(self):
        a = smtp_mod.envelope_from("bounces@envio.example", "aaa")
        b = smtp_mod.envelope_from("bounces@envio.example", "bbb")
        assert a != b


def test_new_verp_tag_es_unico():
    assert smtp_mod.new_verp_tag() != smtp_mod.new_verp_tag()


class TestBuildMime:
    def test_lleva_los_headers_de_baja_en_un_clic(self):
        msg = smtp_mod.build_mime("Asunto", _BODY_CONFORME, "prospecto@negocio.example", _SENDER)
        assert msg["List-Unsubscribe"] == f"<{_SENDER.unsubscribe_url}>"
        assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"

    def test_from_incluye_nombre_y_email(self):
        msg = smtp_mod.build_mime("Asunto", _BODY_CONFORME, "prospecto@negocio.example", _SENDER)
        assert _SENDER.from_name in msg["From"]
        assert _SENDER.from_email in msg["From"]

    def test_asigna_un_message_id(self):
        msg = smtp_mod.build_mime("Asunto", _BODY_CONFORME, "prospecto@negocio.example", _SENDER)
        assert msg["Message-ID"]

    def test_es_texto_plano_no_html(self):
        # El propio cuerpo generado por outreach.py es texto plano -- armar
        # multipart/alternative acá inventaría una parte HTML que no existe
        # en ningún lado del pipeline, y texto plano es ademas mejor señal
        # de entregabilidad para un mensaje 1:1 en frío (ver docs/CHANNELS.md).
        msg = smtp_mod.build_mime("Asunto", _BODY_CONFORME, "prospecto@negocio.example", _SENDER)
        assert msg.get_content_type() == "text/plain"

    def test_no_inserta_pixel_de_rastreo(self):
        msg = smtp_mod.build_mime("Asunto", _BODY_CONFORME, "prospecto@negocio.example", _SENDER)
        assert "<img" not in msg.get_content().lower()

    def test_el_cuerpo_se_preserva_completo(self):
        msg = smtp_mod.build_mime("Asunto", _BODY_CONFORME, "prospecto@negocio.example", _SENDER)
        assert _SENDER.physical_address in msg.get_content()


class TestRevalidacionAntesDeEnviar:
    def test_cuerpo_conforme_no_lanza(self):
        smtp_mod._revalidate_before_send(_BODY_CONFORME, _SENDER)  # no debe lanzar

    def test_sin_direccion_postal_lanza_compliance_error(self):
        cuerpo_sin_direccion = _BODY_CONFORME.replace(_SENDER.physical_address, "")
        with pytest.raises(ComplianceError, match="dirección postal"):
            smtp_mod._revalidate_before_send(cuerpo_sin_direccion, _SENDER)

    def test_sin_unsubscribe_lanza_compliance_error(self):
        cuerpo_sin_baja = _BODY_CONFORME.replace(_SENDER.unsubscribe_url, "")
        with pytest.raises(ComplianceError, match="baja"):
            smtp_mod._revalidate_before_send(cuerpo_sin_baja, _SENDER)

    def test_detecta_drift_si_la_config_actual_no_coincide_con_el_cuerpo(self):
        # El caso real que esto atrapa: el mensaje se redactó con un
        # unsubscribe_url viejo, y el operador cambió la config antes de que
        # el worker llegara a mandarlo -- el cuerpo ya escrito sigue
        # apuntando al link viejo.
        sender_nuevo = SenderIdentity(
            from_name=_SENDER.from_name, from_email=_SENDER.from_email,
            physical_address=_SENDER.physical_address,
            unsubscribe_url="https://envio.example/unsub-nuevo",
        )
        with pytest.raises(ComplianceError):
            smtp_mod._revalidate_before_send(_BODY_CONFORME, sender_nuevo)


class TestSend:
    def test_envio_exitoso(self, monkeypatch):
        calls = {}

        class _FakeSmtp:
            def __init__(self, host, port, timeout=None):
                calls["host"] = host
                calls["port"] = port

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def login(self, user, password):
                calls["login"] = (user, password)

            def send_message(self, msg, from_addr=None, to_addrs=None):
                calls["from_addr"] = from_addr
                calls["to_addrs"] = to_addrs

        monkeypatch.setattr(smtp_mod.smtplib, "SMTP_SSL", _FakeSmtp)

        msg = smtp_mod.build_mime("Asunto", _BODY_CONFORME, "prospecto@negocio.example", _SENDER)
        result = smtp_mod.send(
            msg, settings=_SETTINGS, envelope_sender="bounces+tag@envio.example",
            to_address="prospecto@negocio.example",
        )

        assert result.success
        assert result.provider_message_id == msg["Message-ID"]
        assert calls["from_addr"] == "bounces+tag@envio.example"
        assert calls["to_addrs"] == ["prospecto@negocio.example"]

    def test_un_error_smtp_no_lanza_sino_que_devuelve_send_result_fallido(self, monkeypatch):
        class _FakeSmtpQueFalla:
            def __init__(self, *_a, **_k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def login(self, *_a, **_k):
                raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

        monkeypatch.setattr(smtp_mod.smtplib, "SMTP_SSL", _FakeSmtpQueFalla)

        msg = smtp_mod.build_mime("Asunto", _BODY_CONFORME, "prospecto@negocio.example", _SENDER)
        result = smtp_mod.send(
            msg, settings=_SETTINGS, envelope_sender="bounces+tag@envio.example",
            to_address="prospecto@negocio.example",
        )

        assert not result.success
        assert result.error

    def test_un_error_de_conexion_tampoco_lanza(self, monkeypatch):
        class _FakeSmtpQueNoConecta:
            def __init__(self, *_a, **_k):
                raise OSError("connection refused")

        monkeypatch.setattr(smtp_mod.smtplib, "SMTP_SSL", _FakeSmtpQueNoConecta)

        msg = smtp_mod.build_mime("Asunto", _BODY_CONFORME, "prospecto@negocio.example", _SENDER)
        result = smtp_mod.send(
            msg, settings=_SETTINGS, envelope_sender="bounces+tag@envio.example",
            to_address="prospecto@negocio.example",
        )

        assert not result.success


class TestSendAsync:
    async def test_corre_en_un_hilo_y_devuelve_el_mismo_resultado(self, monkeypatch):
        def _fake_send(_msg, **_kwargs):
            from gtm.send.types import SendResult

            return SendResult(success=True, provider_message_id="<x@y>")

        monkeypatch.setattr(smtp_mod, "send", _fake_send)

        msg = smtp_mod.build_mime("Asunto", _BODY_CONFORME, "prospecto@negocio.example", _SENDER)
        result = await smtp_mod.send_async(
            msg, settings=_SETTINGS, envelope_sender="x@y", to_address="prospecto@negocio.example",
        )
        assert result.success
