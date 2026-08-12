"""Tests de los modelos de datos y del scoring de dolor."""

from __future__ import annotations

import pytest

from gtm.factory.findings import FINDINGS, Finding
from gtm.factory.types import (
    VERTICAL_LABELS,
    ComplianceError,
    ContactChannel,
    ContactPlan,
    Demo,
    DigitalTrace,
    Language,
    OutreachEmail,
    PainScore,
    Prospect,
    SenderIdentity,
    WebPresence,
    classify_web_presence,
    indefinite_article,
)


class TestWebPresence:
    @pytest.mark.parametrize("website", [None, "", "   "])
    def test_sin_sitio_es_none(self, website):
        assert classify_web_presence(website) is WebPresence.NONE

    @pytest.mark.parametrize(
        "website",
        [
            "https://www.facebook.com/plomeria",
            "http://instagram.com/plomeria",
            "https://linktr.ee/plomeria",
            "https://plomeria.business.site",
            "https://plomeria.wixsite.com/home",
        ],
    )
    def test_redes_sociales_no_son_sitio_propio(self, website):
        assert classify_web_presence(website) is WebPresence.SOCIAL_ONLY

    @pytest.mark.parametrize(
        "website",
        [
            "https://www.angi.com/companylist/us/az/tucson/ramirez-plumbing-reviews-1234.htm",
            "https://www.homeadvisor.com/rated.RamirezPlumbing.12345.html",
            "https://www.thumbtack.com/az/tucson/plumbing/ramirez-plumbing",
            "https://www.porch.com/ramirez-plumbing-tucson-az/pp",
            "https://www.houzz.com/pro/ramirezplumbing",
            "https://www.bbb.org/us/az/tucson/profile/plumber/ramirez-plumbing",
            "https://www.yellowpages.com/tucson-az/ramirez-plumbing",
            "https://ramirezplumbing.weebly.com",
            "https://ramirezplumbing.godaddysites.com",
            "https://ramirezplumbing.squarespace.com",
            "https://ramirezplumbing.wordpress.com",
            "https://sites.google.com/view/ramirezplumbing",
        ],
    )
    def test_directorios_de_terceros_no_son_sitio_propio(self, website):
        assert classify_web_presence(website) is WebPresence.SOCIAL_ONLY

    def test_sitio_propio(self):
        assert classify_web_presence("https://ramirezplumbing.com") is WebPresence.HAS_SITE

    def test_dominio_que_contiene_social_no_es_falso_positivo(self):
        # "notfacebook.com" no debe clasificarse como red social.
        assert classify_web_presence("https://notfacebook.com") is WebPresence.HAS_SITE

    def test_dominio_que_contiene_directorio_no_es_falso_positivo(self):
        # Mismo chequeo que arriba, pero para los directorios nuevos: un dominio
        # propio que contiene "houzz" como substring no es Houzz.
        assert classify_web_presence("https://myhouzzstyle.com") is WebPresence.HAS_SITE


class TestProspectSlug:
    def test_slug_es_estable(self, prospect):
        assert prospect.slug == prospect.slug

    def test_slug_es_url_safe(self, prospect):
        assert prospect.slug.replace("-", "").isalnum()
        assert prospect.slug.islower()

    def test_negocios_homonimos_no_colisionan(self):
        a = Prospect(place_id="place_a", name="Joe's Plumbing", vertical="plumber", metro="Mesa, AZ")
        b = Prospect(place_id="place_b", name="Joe's Plumbing", vertical="plumber", metro="Mesa, AZ")
        assert a.slug != b.slug

    def test_nombre_sin_alfanumericos_no_rompe(self):
        weird = Prospect(place_id="p1", name="!!!", vertical="plumber", metro="Mesa, AZ")
        assert weird.slug.startswith("business-")

    def test_roundtrip_dict(self, prospect):
        assert Prospect.from_dict(prospect.to_dict()) == prospect


class TestPainScore:
    def test_sin_web_es_dolor_maximo(self):
        assert PainScore(place_id="x", has_web_presence=False).score == 100

    def test_sitio_caido_es_casi_maximo(self):
        score = PainScore(place_id="x", reachable=False)
        assert score.score == 95
        assert score.is_qualified

    def test_sitio_lento_puntua_alto(self, slow_site_score):
        # Promedio ponderado: perf 77 (peso 1), seo 39 (peso 1), a11y 30 (peso 0.5).
        assert slow_site_score.score == round((77 * 1 + 39 * 1 + 30 * 0.5) / 2.5)
        assert slow_site_score.is_qualified

    def test_accesibilidad_no_diluye_el_score_global(self):
        """Bajarle el peso a a11y no debe hundir el score de un sitio malo."""
        sin_a11y = PainScore(place_id="x", performance=23, seo=61)
        con_a11y_buena = PainScore(place_id="x", performance=23, seo=61, accessibility=100)
        assert con_a11y_buena.score < sin_a11y.score
        assert con_a11y_buena.is_qualified, "el sitio sigue siendo lento y mal rankeado"

    def test_sitio_impecable_no_califica(self):
        score = PainScore(
            place_id="x", performance=98, seo=100, accessibility=96, mobile_friendly=True
        )
        assert score.score < 45
        assert not score.is_qualified

    def test_no_mobile_friendly_domina_el_score(self):
        score = PainScore(place_id="x", performance=90, seo=90, mobile_friendly=False)
        assert score.is_qualified, "en home services el tráfico es móvil: esto debe calificar"

    def test_sin_senales_es_cero(self):
        assert PainScore(place_id="x").score == 0

    def test_score_siempre_en_rango(self):
        score = PainScore(place_id="x", performance=0, seo=0, accessibility=0, mobile_friendly=False)
        assert 0 <= score.score <= 100


class TestPainScoreSubScores:
    """`findings` es puramente aditivo: sin hallazgos, el score tiene que
    seguir dando exactamente los mismos números que antes de esta clase
    existir -- por eso TestPainScore de arriba no cambió ni un assert."""

    def test_expone_las_cinco_dimensiones(self):
        s = PainScore(place_id="x", performance=20, seo=40, accessibility=60)
        assert set(s.sub_scores) == {"speed", "mobile", "seo", "modernity", "conversion"}

    def test_dimension_sin_senal_se_muestra_en_cero(self):
        s = PainScore(place_id="x", performance=20)
        assert s.sub_scores["modernity"] == 0
        assert s.sub_scores["conversion"] == 0

    def test_un_hallazgo_critico_de_conversion_empuja_el_score_global(self):
        base = PainScore(place_id="x", performance=90, seo=95, accessibility=95, mobile_friendly=True)
        con_hallazgo = PainScore(
            place_id="x", performance=90, seo=95, accessibility=95, mobile_friendly=True,
            findings=(Finding(code="no_tel_link", evidence="teléfono en texto plano", weight=FINDINGS["no_tel_link"].weight),),
        )
        assert con_hallazgo.score > base.score

    def test_un_hallazgo_se_refleja_en_su_propia_dimension(self):
        s = PainScore(
            place_id="x",
            findings=(Finding(code="table_layout", evidence="3 tablas", weight=FINDINGS["table_layout"].weight),),
        )
        assert s.sub_scores["modernity"] > 0
        assert s.sub_scores["conversion"] == 0

    def test_mas_hallazgos_en_la_misma_dimension_suben_mas_el_dolor(self):
        uno = PainScore(
            place_id="x",
            findings=(Finding(code="table_layout", evidence="x", weight=FINDINGS["table_layout"].weight),),
        )
        dos = PainScore(
            place_id="x",
            findings=(
                Finding(code="table_layout", evidence="x", weight=FINDINGS["table_layout"].weight),
                Finding(code="dead_analytics", evidence="x", weight=FINDINGS["dead_analytics"].weight),
            ),
        )
        assert dos.sub_scores["modernity"] > uno.sub_scores["modernity"]

    def test_findings_vacio_no_cambia_el_score_de_antes(self, slow_site_score):
        # Regresión directa: mismos campos que el fixture ya usado en
        # TestPainScore, sin findings -- tiene que dar exactamente 52.
        assert slow_site_score.score == 52
        assert slow_site_score.sub_scores["modernity"] == 0
        assert slow_site_score.sub_scores["conversion"] == 0

    def test_las_lineas_de_venta_salen_ordenadas_por_severidad(self):
        s = PainScore(
            place_id="x",
            findings=(
                Finding(code="stale_copyright", evidence="© 2014", weight=FINDINGS["stale_copyright"].weight),
                Finding(code="no_tel_link", evidence="teléfono en texto plano", weight=FINDINGS["no_tel_link"].weight),
            ),
        )
        lineas = s.sales_lines(Language.ES)
        assert len(lineas) == 2
        assert "teléfono" in lineas[0]  # CRITICAL antes que MEDIUM

    def test_sales_lines_vacio_sin_hallazgos(self):
        assert PainScore(place_id="x").sales_lines(Language.ES) == []

    def test_sales_lines_por_default_salta_hallazgos_no_citables(self):
        """dated_palette (quotable=False) no debe aparecer en el gancho del
        email/mensaje por default -- es lo que usa outreach.py sin pasar
        quotable_only explícito."""
        s = PainScore(
            place_id="x",
            findings=(
                Finding(code="no_tel_link", evidence="555-0142", weight=FINDINGS["no_tel_link"].weight),
                Finding(code="dated_palette", evidence="9", weight=FINDINGS["dated_palette"].weight),
            ),
        )
        lineas = s.sales_lines(Language.ES)
        assert len(lineas) == 1
        assert "555-0142" in lineas[0]

    def test_sales_lines_quotable_only_false_muestra_todo(self):
        """audit.py pasa quotable_only=False a propósito: es material interno
        de apoyo para la llamada, no algo que se le manda al prospecto."""
        s = PainScore(
            place_id="x",
            findings=(
                Finding(code="no_tel_link", evidence="555-0142", weight=FINDINGS["no_tel_link"].weight),
                Finding(code="dated_palette", evidence="9", weight=FINDINGS["dated_palette"].weight),
            ),
        )
        lineas = s.sales_lines(Language.ES, quotable_only=False)
        assert len(lineas) == 2

    def test_el_score_siempre_queda_en_rango_con_muchos_hallazgos(self):
        s = PainScore(
            place_id="x",
            findings=tuple(Finding(code=c, evidence="x", weight=spec.weight) for c, spec in FINDINGS.items()),
        )
        assert 0 <= s.score <= 100
        assert all(0 <= v <= 100 for v in s.sub_scores.values())


class TestPainScoreDigitalTrace:
    """`digital_trace`/`verified_domain` son el resultado de la Capa 2 de
    verificación (`gtm/factory/verify.py`) -- no cambian la fórmula de
    `score`, solo documentan qué tan seguros estamos de la ausencia digital."""

    def test_default_es_unverified(self):
        assert PainScore(place_id="x").digital_trace is DigitalTrace.UNVERIFIED
        assert PainScore(place_id="x").verified_domain is None

    def test_no_afecta_el_score(self):
        """Dos PainScore idénticos salvo digital_trace deben dar el mismo score:
        el campo es informativo, no una señal de dolor."""
        sin_trace = PainScore(place_id="x", has_web_presence=False)
        con_trace = PainScore(
            place_id="x", has_web_presence=False, digital_trace=DigitalTrace.NO_TRACE
        )
        assert sin_trace.score == con_trace.score == 100

    def test_roundtrip(self):
        original = PainScore(
            place_id="x",
            has_web_presence=True,
            performance=40,
            digital_trace=DigitalTrace.OWN_DOMAIN,
            verified_domain="https://legacytree.com",
        )
        restored = PainScore.from_dict(original.to_dict())
        assert restored == original

    def test_roundtrip_sin_digital_trace_cae_a_unverified(self):
        assert PainScore.from_dict({"place_id": "x"}).digital_trace is DigitalTrace.UNVERIFIED


class TestPainScoreRoundtripConHallazgos:
    def test_from_dict_reconstruye_los_findings(self):
        original = PainScore(
            place_id="x",
            findings=(Finding(code="no_https", evidence="http://x.com", weight=FINDINGS["no_https"].weight),),
        )
        restored = PainScore.from_dict(original.to_dict())
        assert restored == original

    def test_from_dict_reconstruye_last_changed(self):
        from datetime import date

        original = PainScore(place_id="x", last_changed=date(2016, 3, 12), has_field_data=True)
        restored = PainScore.from_dict(original.to_dict())
        assert restored == original

    def test_from_dict_sin_findings_ni_last_changed_no_rompe(self):
        assert PainScore.from_dict({"place_id": "x"}) == PainScore(place_id="x")


class TestSenderIdentity:
    def test_identidad_valida_pasa(self, sender):
        sender.validate()

    def test_nombre_vacio_falla(self, sender):
        bad = SenderIdentity("  ", sender.from_email, sender.physical_address, sender.unsubscribe_url)
        with pytest.raises(ComplianceError, match="from_name"):
            bad.validate()

    def test_email_invalido_falla(self, sender):
        bad = SenderIdentity(sender.from_name, "no-arroba", sender.physical_address, sender.unsubscribe_url)
        with pytest.raises(ComplianceError, match="from_email"):
            bad.validate()

    def test_direccion_postal_corta_falla(self, sender):
        bad = SenderIdentity(sender.from_name, sender.from_email, "Calle 1", sender.unsubscribe_url)
        with pytest.raises(ComplianceError, match="physical_address"):
            bad.validate()

    def test_unsubscribe_no_url_falla(self, sender):
        bad = SenderIdentity(sender.from_name, sender.from_email, sender.physical_address, "escribime")
        with pytest.raises(ComplianceError, match="unsubscribe_url"):
            bad.validate()

    def test_unsubscribe_mailto_es_valido(self, sender):
        ok = SenderIdentity(
            sender.from_name, sender.from_email, sender.physical_address, "mailto:baja@example.com"
        )
        ok.validate()


class TestIndefiniteArticle:
    """Regresión: el artículo aparecía hardcodeado como "a" en la plantilla, y
    salía "Need a HVAC contractor now?" en la cara del cliente."""

    @pytest.mark.parametrize(
        ("phrase", "expected"),
        [
            ("HVAC contractor", "an"),  # se deletrea "aitch", suena a vocal
            ("electrician", "an"),
            ("plumber", "a"),
            ("roofing contractor", "a"),
            ("landscaper", "a"),
            ("AC technician", "an"),
            ("locksmith", "a"),
            ("SEO consultant", "an"),
            ("PVC specialist", "a"),
            ("", "a"),
            ("   ", "a"),
        ],
    )
    def test_articulo_correcto(self, phrase, expected):
        assert indefinite_article(phrase) == expected

    def test_todas_las_etiquetas_del_catalogo_resuelven(self):
        for label in VERTICAL_LABELS.values():
            assert indefinite_article(label) in ("a", "an")


class TestRoundtripDict:
    """`from_dict(to_dict(x)) == x` para los modelos que antes se reconstruían a mano
    en 5 lugares distintos, con cobertura de campos inconsistente entre ellos (p. ej.
    `contact._load_scores` perdía `notes`; `deploy` perdía `url`/`deployed_at`). Un
    único `from_dict` por tipo, verificado acá, es lo que hace seguro colapsarlos."""

    def test_pain_score(self, slow_site_score):
        assert PainScore.from_dict(slow_site_score.to_dict()) == slow_site_score

    def test_pain_score_sin_web_presence(self):
        original = PainScore(place_id="x", has_web_presence=False, notes=("sin sitio",))
        assert PainScore.from_dict(original.to_dict()) == original

    def test_demo(self, live_demo):
        assert Demo.from_dict(live_demo.to_dict()) == live_demo

    def test_demo_con_deployed_at(self):
        from datetime import UTC, datetime

        original = Demo(
            place_id="p1",
            slug="joes-plumbing-abc123",
            html_path="/tmp/demo/index.html",
            url="https://demos.example.com/joes-plumbing-abc123/",
            deployed_at=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
        )
        assert Demo.from_dict(original.to_dict()) == original

    def test_demo_sin_publicar(self):
        original = Demo(place_id="p1", slug="joes-plumbing-abc123", html_path="/tmp/index.html")
        assert Demo.from_dict(original.to_dict()) == original

    def test_demo_con_idioma_detectado(self):
        original = Demo(
            place_id="p1",
            slug="jardineria-lopez-abc123",
            html_path="/tmp/index.html",
            language=Language.ES,
        )
        assert Demo.from_dict(original.to_dict()) == original

    def test_demo_idioma_default_es_ingles(self):
        assert Demo(place_id="p1", slug="x", html_path="/tmp/index.html").language is Language.EN

    def test_demo_roundtrip_sin_idioma_cae_a_ingles(self):
        assert Demo.from_dict({"place_id": "p1", "slug": "x", "html_path": "/tmp/index.html"}).language is Language.EN

    def test_contact_plan_telefono(self):
        original = ContactPlan(
            place_id="p1",
            channel=ContactChannel.PHONE,
            target="(520) 555-0142",
            rationale="dolor máximo, teléfono disponible",
            pain_score=95,
        )
        assert ContactPlan.from_dict(original.to_dict()) == original

    def test_contact_plan_no_accionable(self):
        original = ContactPlan(
            place_id="p1", channel=ContactChannel.UNREACHABLE, target=None, rationale="sin canal"
        )
        assert ContactPlan.from_dict(original.to_dict()) == original

    def test_outreach_email(self, prospect, live_demo, sender):
        from gtm.factory.outreach import build_email

        original = build_email(prospect, live_demo, sender)
        restored = OutreachEmail.from_dict(original.to_dict())
        assert restored == original
