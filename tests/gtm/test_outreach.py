"""Tests del email de prospección.

El bloque `canspam` es el que importa: se corre aislado en CI antes de cualquier envío
(`pytest tests/gtm/test_outreach.py -k canspam`). Las multas se cuentan por mensaje.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gtm.factory.findings import FINDINGS, Finding
from gtm.factory.outreach import (
    _AD_DISCLOSURE,
    _AD_DISCLOSURE_ES,
    build_body,
    build_email,
    build_subject,
    validate_compliance,
)
from gtm.factory.types import ComplianceError, Demo, Language, OutreachEmail, PainScore


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


class TestCanspamComplianceES:
    """Los mismos cinco requisitos de CAN-SPAM, en la versión en español.

    CAN-SPAM aplica al email comercial dirigido a destinatarios de EE.UU. sin
    importar el idioma del mensaje — un email en español a un negocio de Arizona
    necesita los cinco elementos exactamente igual que uno en inglés. Nombrados
    `test_canspam_es_*` a propósito: el gate de CI (`pytest tests/gtm/test_outreach.py
    -k canspam`) selecciona por substring en el nombre del test, no por clase, así
    que estos quedan cubiertos sin tocar `.github/workflows/ci.yml`.
    """

    def test_canspam_es_incluye_direccion_postal(self, prospect, live_demo, sender):
        email = build_email(prospect, live_demo, sender, language=Language.ES)
        assert sender.physical_address in email.body

    def test_canspam_es_incluye_mecanismo_de_baja(self, prospect, live_demo, sender):
        email = build_email(prospect, live_demo, sender, language=Language.ES)
        assert sender.unsubscribe_url in email.body

    def test_canspam_es_se_identifica_como_comercial(self, prospect, live_demo, sender):
        email = build_email(prospect, live_demo, sender, language=Language.ES)
        assert _AD_DISCLOSURE_ES in email.body
        # La constante en inglés NO debe aparecer: sería la señal de que el
        # mensaje se armó con el disclosure equivocado pegado sobre otro idioma.
        assert _AD_DISCLOSURE not in email.body

    def test_canspam_es_declara_plazo_de_baja(self, prospect, live_demo, sender):
        email = build_email(prospect, live_demo, sender, language=Language.ES)
        assert "10 días hábiles" in email.body

    def test_canspam_es_asunto_no_enganoso(self, prospect, live_demo, sender):
        email = build_email(prospect, live_demo, sender, language=Language.ES)
        assert email.subject.strip()
        assert not email.subject.lower().startswith(("re:", "fwd:", "fw:"))

    def test_canspam_es_rechaza_cuerpo_sin_direccion_postal(self, prospect, live_demo, sender):
        body = build_body(prospect, live_demo, sender, language=Language.ES).replace(
            sender.physical_address, ""
        )
        email = OutreachEmail(
            place_id=prospect.place_id,
            to_email=None,
            subject=build_subject(prospect, language=Language.ES),
            body=body,
            sender=sender,
            demo_url=live_demo.url,
            language=Language.ES,
        )
        with pytest.raises(ComplianceError, match="dirección postal"):
            validate_compliance(email)

    def test_canspam_es_rechaza_cuerpo_sin_disclosure_en_ingles(self, prospect, live_demo, sender):
        """El disclosure en inglés no debe validar un email marcado como español:
        si `validate_compliance` mirara la constante equivocada, esto pasaría en
        silencio en vez de fallar."""
        body = build_body(prospect, live_demo, sender, language=Language.EN)
        email = OutreachEmail(
            place_id=prospect.place_id,
            to_email=None,
            subject=build_subject(prospect, language=Language.ES),
            body=body,
            sender=sender,
            demo_url=live_demo.url,
            language=Language.ES,
        )
        with pytest.raises(ComplianceError, match="comunicación comercial"):
            validate_compliance(email)

    @pytest.mark.parametrize("language", list(Language))
    def test_canspam_todo_idioma_tiene_disclosure_propio(self, language, prospect, live_demo, sender):
        """Agregar un idioma nuevo sin su disclosure correspondiente debe ser
        imposible de que pase este test — es la red que atrapa el error antes de
        que se mande el primer mensaje en ese idioma."""
        email = build_email(prospect, live_demo, sender, language=language)
        validate_compliance(email)  # no debe lanzar
        assert email.language is language


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


class TestGanchoConHallazgos:
    """Con hallazgos forenses/de campo, el gancho cita el más grave con su
    propia evidencia en vez de las cuatro frases fijas de Lighthouse."""

    def test_el_gancho_cita_el_hallazgo_mas_severo_en_espanol(self, prospect, live_demo, sender):
        score = PainScore(
            place_id=prospect.place_id,
            findings=(
                Finding(code="stale_copyright", evidence="© 2014", weight=FINDINGS["stale_copyright"].weight),
                Finding(code="no_tel_link", evidence="teléfono en texto plano", weight=FINDINGS["no_tel_link"].weight),
            ),
        )
        body = build_body(prospect, live_demo, sender, score, language=Language.ES)
        assert "teléfono en texto plano" in body  # CRITICAL, no el © 2014 (MEDIUM)

    def test_el_gancho_cita_el_hallazgo_mas_severo_en_ingles(self, prospect, live_demo, sender):
        score = PainScore(
            place_id=prospect.place_id,
            findings=(Finding(code="no_https", evidence="http://x.com", weight=FINDINGS["no_https"].weight),),
        )
        body = build_body(prospect, live_demo, sender, score, language=Language.EN)
        assert "http://x.com" in body

    def test_sin_hallazgos_cae_al_gancho_de_lighthouse_de_siempre(self, prospect, live_demo, sender):
        score = PainScore(place_id=prospect.place_id, performance=34)
        body = build_body(prospect, live_demo, sender, score, language=Language.EN)
        assert "34/100" in body

    def test_hallazgos_no_rompen_el_gate_de_canspam(self, prospect, live_demo, sender):
        # El gancho cambia; los requisitos legales del cuerpo, no.
        score = PainScore(
            place_id=prospect.place_id,
            findings=(Finding(code="no_https", evidence="http://x.com", weight=FINDINGS["no_https"].weight),),
        )
        email = build_email(prospect, live_demo, sender, score)
        validate_compliance(email)  # no debe lanzar


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

    def test_precio_es_configurable(self, prospect, live_demo, sender):
        """El precio define el experimento (decision_criteria.yaml) -- tiene que
        poder variar sin tocar código, para poder probar distintos puntos."""
        body = build_body(prospect, live_demo, sender, price_usd=1450)
        assert "$1450" in body
        assert "$950" not in body

    def test_precio_en_espanol_tambien_es_configurable(self, prospect, live_demo, sender):
        from gtm.factory.types import Language

        body = build_body(prospect, live_demo, sender, language=Language.ES, price_usd=690)
        assert "USD 690" in body
        assert "USD 950" not in body
