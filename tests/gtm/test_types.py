"""Tests de los modelos de datos y del scoring de dolor."""

from __future__ import annotations

import pytest

from gtm.factory.types import (
    VERTICAL_LABELS,
    ComplianceError,
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

    def test_sitio_propio(self):
        assert classify_web_presence("https://ramirezplumbing.com") is WebPresence.HAS_SITE

    def test_dominio_que_contiene_social_no_es_falso_positivo(self):
        # "notfacebook.com" no debe clasificarse como red social.
        assert classify_web_presence("https://notfacebook.com") is WebPresence.HAS_SITE


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
