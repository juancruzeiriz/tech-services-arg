"""Tests del email de prospección.

El bloque `canspam` es el que importa: se corre aislado en CI antes de cualquier envío
(`pytest tests/gtm/test_outreach.py -k canspam`). Las multas se cuentan por mensaje.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gtm.factory.outreach import (
    _AD_DISCLOSURE,
    build_body,
    build_email,
    build_subject,
    validate_compliance,
)
from gtm.factory.types import ComplianceError, Demo, OutreachEmail, PainScore


class TestCanspamCompliance:
    """Requisitos obligatorios de CAN-SPAM en cada mensaje."""

    def test_canspam_incluye_direccion_postal(self, prospect, live_demo, sender):
        email = build_email(prospect, live_demo, sender)
        assert sender.physical_address in email.body

    def test_canspam_incluye_mecanismo_de_baja(self, prospect, live_demo, sender):
        email = build_email(prospect, live_demo, sender)
        assert sender.unsubscribe_url in email.body

    def test_canspam_se_identifica_como_comercial(self, prospect, live_demo, sender):
        email = build_email(prospect, live_demo, sender)
        assert _AD_DISCLOSURE in email.body

    def test_canspam_declara_plazo_de_baja(self, prospect, live_demo, sender):
        email = build_email(prospect, live_demo, sender)
        assert "10 business days" in email.body

    def test_canspam_asunto_no_enganoso(self, prospect, live_demo, sender):
        email = build_email(prospect, live_demo, sender)
        assert email.subject.strip()
        assert not email.subject.lower().startswith(("re:", "fwd:", "fw:"))

    @pytest.mark.parametrize("fake", ["Re: our call", "FWD: invoice", "fw: your account"])
    def test_canspam_rechaza_asunto_que_finge_hilo_previo(self, fake, prospect, live_demo, sender):
        email = OutreachEmail(
            place_id=prospect.place_id,
            to_email=None,
            subject=fake,
            body=build_body(prospect, live_demo, sender),
            sender=sender,
            demo_url=live_demo.url,
        )
        with pytest.raises(ComplianceError, match="engañoso"):
            validate_compliance(email)

    def test_canspam_rechaza_cuerpo_sin_direccion_postal(self, prospect, live_demo, sender):
        body = build_body(prospect, live_demo, sender).replace(sender.physical_address, "")
        email = OutreachEmail(
            place_id=prospect.place_id,
            to_email=None,
            subject=build_subject(prospect),
            body=body,
            sender=sender,
            demo_url=live_demo.url,
        )
        with pytest.raises(ComplianceError, match="dirección postal"):
            validate_compliance(email)

    def test_canspam_rechaza_cuerpo_sin_baja(self, prospect, live_demo, sender):
        body = build_body(prospect, live_demo, sender).replace(sender.unsubscribe_url, "")
        email = OutreachEmail(
            place_id=prospect.place_id,
            to_email=None,
            subject=build_subject(prospect),
            body=body,
            sender=sender,
            demo_url=live_demo.url,
        )
        with pytest.raises(ComplianceError, match="baja"):
            validate_compliance(email)

    def test_canspam_rechaza_remitente_invalido(self, prospect, live_demo, sender):
        email = build_email(prospect, live_demo, sender)
        broken = OutreachEmail(
            place_id=email.place_id,
            to_email=None,
            subject=email.subject,
            body=email.body,
            sender=type(sender)("", sender.from_email, sender.physical_address, sender.unsubscribe_url),
            demo_url=email.demo_url,
        )
        with pytest.raises(ComplianceError):
            validate_compliance(broken)


class TestHonestidadDelMensaje:
    """El pipeline no inventa hechos sobre el negocio del prospecto."""

    def test_sin_observacion_no_afirma_haber_llamado(self, prospect, live_demo, sender):
        body = build_body(prospect, live_demo, sender, score=PainScore(place_id="x", performance=30))
        assert "I called" not in body

    def test_con_observacion_real_si_menciona_la_llamada(self, prospect, live_demo, sender):
        observed = datetime(2026, 8, 4, 19, 40, tzinfo=UTC)
        body = build_body(prospect, live_demo, sender, missed_call_at=observed)
        assert "I called" in body

    def test_cita_una_metrica_verificable_por_el_prospecto(self, prospect, live_demo, sender):
        score = PainScore(place_id=prospect.place_id, performance=23, seo=61)
        body = build_body(prospect, live_demo, sender, score)
        assert "23/100" in body
        assert "pagespeed.web.dev" in body, "el prospecto tiene que poder verificarlo solo"

    def test_sin_sitio_usa_el_angulo_correcto(self, prospect, live_demo, sender):
        score = PainScore(place_id=prospect.place_id, has_web_presence=False)
        body = build_body(prospect, live_demo, sender, score)
        assert "do not have a website" in body

    def test_sitio_caido_usa_el_angulo_correcto(self, prospect, live_demo, sender):
        score = PainScore(place_id=prospect.place_id, reachable=False)
        body = build_body(prospect, live_demo, sender, score)
        assert "did not load" in body


class TestDemoViva:
    def test_demo_sin_url_es_rechazada(self, prospect, sender):
        mockup = Demo(place_id=prospect.place_id, slug="x", html_path="/tmp/x/index.html")
        with pytest.raises(ComplianceError, match="URL pública"):
            build_body(prospect, mockup, sender)

    def test_el_cuerpo_incluye_el_link_de_la_demo(self, prospect, live_demo, sender):
        email = build_email(prospect, live_demo, sender)
        assert live_demo.url in email.body

    def test_incluye_precio_y_garantia(self, prospect, live_demo, sender):
        body = build_body(prospect, live_demo, sender)
        assert "$950" in body, "el precio visible es el filtro más barato que existe"
        assert "refund" in body.lower()
