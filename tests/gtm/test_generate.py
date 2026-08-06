"""Tests del renderizado de demos."""

from __future__ import annotations

import html
import json

import pytest

from gtm.factory.generate import _phone_href, generate, load_qualified_ids, render
from gtm.factory.types import GenerationError, Language, Prospect

AUTHOR = "Juan Cruz Eiriz"
AUTHOR_URL = "https://example.com/about"


class TestRender:
    def test_usa_datos_reales_del_negocio(self, prospect):
        markup = render(prospect, AUTHOR, AUTHOR_URL)
        # El nombre va escapado: "&" -> "&amp;".
        assert html.escape(prospect.name) in markup
        assert prospect.phone in markup
        assert "214" in markup, "cantidad de reseñas real"
        assert "4.8" in markup
        assert "Tucson" in markup

    def test_no_deja_placeholders_sin_resolver(self, prospect):
        markup = render(prospect, AUTHOR, AUTHOR_URL)
        assert "$business_name" not in markup
        assert "$phone" not in markup
        assert "$services_html" not in markup

    def test_incluye_resenas_reales(self, prospect):
        markup = render(prospect, AUTHOR, AUTHOR_URL)
        assert "Showed up in 40 minutes" in markup

    def test_marca_la_demo_como_preview_de_terceros(self, prospect):
        """No puede confundirse con el sitio oficial del negocio."""
        markup = render(prospect, AUTHOR, AUTHOR_URL)
        assert "Preview site" in markup
        assert "Not affiliated with" in markup
        assert AUTHOR in markup

    def test_lleva_noindex(self, prospect):
        """La demo no debe competirle en buscadores al sitio real del prospecto."""
        markup = render(prospect, AUTHOR, AUTHOR_URL)
        assert 'name="robots" content="noindex,nofollow"' in markup

    def test_no_hace_requests_externas(self, prospect):
        """Cero recursos externos: la velocidad es el argumento de venta."""
        markup = render(prospect, AUTHOR, AUTHOR_URL)
        for pattern in ("<script", "src=\"http", "@import", "<link rel=\"stylesheet\""):
            assert pattern not in markup, f"recurso externo detectado: {pattern}"

    def test_escapa_html_del_nombre(self):
        hostile = Prospect(
            place_id="p1",
            name='Bob <script>alert("xss")</script> Plumbing',
            vertical="plumber",
            metro="Mesa, AZ",
            phone="(480) 555-0100",
        )
        markup = render(hostile, AUTHOR, AUTHOR_URL)
        assert "<script>alert" not in markup
        assert "&lt;script&gt;" in markup

    def test_escapa_html_de_las_resenas(self):
        hostile = Prospect(
            place_id="p1",
            name="Safe Plumbing",
            vertical="plumber",
            metro="Mesa, AZ",
            phone="(480) 555-0100",
            top_reviews=("<img src=x onerror=alert(1)>",),
        )
        markup = render(hostile, AUTHOR, AUTHOR_URL)
        # El payload sobrevive como texto visible, pero no como etiqueta ejecutable.
        assert "<img" not in markup
        assert "&lt;img src=x onerror=alert(1)&gt;" in markup

    def test_sin_telefono_falla(self):
        no_phone = Prospect(place_id="p1", name="X", vertical="plumber", metro="Mesa, AZ")
        with pytest.raises(GenerationError, match="teléfono"):
            render(no_phone, AUTHOR, AUTHOR_URL)

    def test_vertical_desconocido_usa_servicios_por_defecto(self):
        # "alpaca-shearer" a propósito: no puede terminar en el catálogo (a
        # diferencia de "locksmith", que sí está desde que el catálogo creció a 15
        # oficios) y el test dejaría de probar lo que dice probar.
        other = Prospect(
            place_id="p1",
            name="Generic Co",
            vertical="alpaca-shearer",
            metro="Mesa, AZ",
            phone="(480) 555-0100",
        )
        markup = render(other, AUTHOR, AUTHOR_URL)
        assert "Emergency service" in markup

    def test_resena_larga_se_trunca(self):
        long_review = "x" * 500
        wordy = Prospect(
            place_id="p1",
            name="Wordy Plumbing",
            vertical="plumber",
            metro="Mesa, AZ",
            phone="(480) 555-0100",
            top_reviews=(long_review,),
        )
        markup = render(wordy, AUTHOR, AUTHOR_URL)
        assert "…" in markup
        assert long_review not in markup


class TestRenderEnEspanol:
    """La demo en español: mismo template (`gtm/template/site.html`), mismos datos
    reales, mismas garantías de seguridad — solo cambia el idioma inyectado en el
    `values` dict de `render()`, nunca el archivo HTML."""

    def test_usa_datos_reales_del_negocio(self, prospect):
        markup = render(prospect, AUTHOR, AUTHOR_URL, Language.ES)
        assert html.escape(prospect.name) in markup
        assert prospect.phone in markup
        assert "214" in markup
        assert "4.8" in markup
        assert "Tucson" in markup

    def test_no_deja_placeholders_sin_resolver(self, prospect):
        markup = render(prospect, AUTHOR, AUTHOR_URL, Language.ES)
        assert "$business_name" not in markup
        assert "$cta_heading" not in markup
        assert "$flag_text" not in markup

    def test_lang_del_html_es_es(self, prospect):
        markup = render(prospect, AUTHOR, AUTHOR_URL, Language.ES)
        assert '<html lang="es">' in markup

    def test_lang_por_defecto_es_en(self, prospect):
        """El default sin especificar idioma no puede cambiar: es el comportamiento
        que ya usan todos los tests de TestRender."""
        markup = render(prospect, AUTHOR, AUTHOR_URL)
        assert '<html lang="en">' in markup

    def test_no_hace_requests_externas(self, prospect):
        """La velocidad es el argumento de venta en cualquier idioma."""
        markup = render(prospect, AUTHOR, AUTHOR_URL, Language.ES)
        for pattern in ("<script", "src=\"http", "@import", "<link rel=\"stylesheet\""):
            assert pattern not in markup

    def test_no_mezcla_idiomas(self, prospect):
        """Ninguna de las cadenas fijas en inglés debe sobrevivir en la versión
        en español -- señal de que algún placeholder quedó sin traducir."""
        markup = render(prospect, AUTHOR, AUTHOR_URL, Language.ES)
        for english_only in ("Preview site", "Not affiliated", "Who made this", "Call ", "Serving"):
            assert english_only not in markup

    def test_cta_heading_usa_el_plural_sin_articulo(self, prospect):
        """Evita a propósito modelar género gramatical (un/una): usa el plural
        curado del catálogo, que no lo necesita."""
        markup = render(prospect, AUTHOR, AUTHOR_URL, Language.ES)
        assert "¿Necesitás plumbers ahora?" not in markup  # no debe colarse la etiqueta cruda
        assert "¿Necesitás plomeros ahora?" in markup

    def test_vertical_desconocido_usa_servicios_por_defecto_en_espanol(self):
        other = Prospect(
            place_id="p1",
            name="Generic Co",
            vertical="alpaca-shearer",
            metro="Mesa, AZ",
            phone="(480) 555-0100",
        )
        markup = render(other, AUTHOR, AUTHOR_URL, Language.ES)
        assert "Emergencias" in markup

    def test_generate_acepta_idioma(self, prospect, tmp_path, monkeypatch):
        from gtm.factory import config

        monkeypatch.setattr(config, "DEMOS_DIR", tmp_path / "demos")
        monkeypatch.setattr(config, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")

        demo = generate(prospect, AUTHOR, AUTHOR_URL, Language.ES)
        written = (tmp_path / "demos" / prospect.slug / "index.html").read_text(encoding="utf-8")
        assert '<html lang="es">' in written
        assert demo.slug == prospect.slug


class TestPhoneHref:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("(520) 555-0142", "5205550142"),
            ("+1 520-555-0142", "+15205550142"),
            ("520.555.0142", "5205550142"),
        ],
    )
    def test_normaliza_a_tel(self, raw, expected):
        assert _phone_href(raw) == expected


class TestGenerate:
    def test_escribe_el_html_en_disco(self, prospect, tmp_path, monkeypatch):
        from gtm.factory import config

        monkeypatch.setattr(config, "DEMOS_DIR", tmp_path / "demos")
        monkeypatch.setattr(config, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")

        demo = generate(prospect, AUTHOR, AUTHOR_URL)

        assert demo.slug == prospect.slug
        assert demo.place_id == prospect.place_id
        written = (tmp_path / "demos" / prospect.slug / "index.html").read_text(encoding="utf-8")
        assert html.escape(prospect.name) in written

    def test_es_idempotente(self, prospect, tmp_path, monkeypatch):
        from gtm.factory import config

        monkeypatch.setattr(config, "DEMOS_DIR", tmp_path / "demos")
        monkeypatch.setattr(config, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")

        first = generate(prospect, AUTHOR, AUTHOR_URL)
        second = generate(prospect, AUTHOR, AUTHOR_URL)

        assert first.html_path == second.html_path
        assert first.slug == second.slug


class TestFiltroDeCalificados:
    """Regresión: `generate --all` producía demos para prospectos cuyo sitio ya
    estaba bien, gastando trabajo y mandando un email que se lee como spam."""

    def test_devuelve_solo_los_calificados(self, tmp_path):
        scores = tmp_path / "scores.json"
        scores.write_text(
            json.dumps(
                [
                    {"place_id": "duele", "is_qualified": True},
                    {"place_id": "esta_bien", "is_qualified": False},
                ]
            ),
            encoding="utf-8",
        )
        assert load_qualified_ids(str(scores)) == {"duele"}

    def test_sin_archivo_de_scores_devuelve_none(self, tmp_path):
        """None significa "no filtrar", distinto de "ninguno califica"."""
        assert load_qualified_ids(str(tmp_path / "no-existe.json")) is None

    def test_ninguno_calificado_es_set_vacio_no_none(self, tmp_path):
        scores = tmp_path / "scores.json"
        scores.write_text(json.dumps([{"place_id": "x", "is_qualified": False}]), encoding="utf-8")
        assert load_qualified_ids(str(scores)) == set()


class TestAiCopy:
    """`ai_copy` (gtm/factory/copy_ai.py) solo puede tocar los 5 slots 100%
    genéricos -- nunca un hecho del negocio. Ver la regla dura en pipeline.md."""

    def test_sobreescribe_los_slots_permitidos(self, prospect):
        ai_copy = {
            "cta_body": "Texto generado por IA.",
            "trust_serving_label": "Cobertura",
            "trust_fast_label": "Al toque",
            "services_heading": "Lo que hacemos",
            "reviews_heading": "Nos eligen",
        }
        markup = render(prospect, AUTHOR, AUTHOR_URL, ai_copy=ai_copy)
        assert "Texto generado por IA." in markup
        assert "Cobertura" in markup
        assert "Al toque" in markup

    def test_ignora_claves_fuera_de_los_slots_permitidos(self, prospect):
        """Un dict de ai_copy con 'business_name' u otro hecho no puede
        pisar el dato real del prospecto -- ni por bug, ni por un modelo
        que decida devolver más claves de las pedidas."""
        hostile = {"business_name": "Nombre Inventado", "phone": "000-0000"}
        markup = render(prospect, AUTHOR, AUTHOR_URL, ai_copy=hostile)
        assert html.escape(prospect.name) in markup
        assert "Nombre Inventado" not in markup
        assert prospect.phone in markup

    def test_ai_copy_none_usa_los_defaults(self, prospect):
        with_none = render(prospect, AUTHOR, AUTHOR_URL, ai_copy=None)
        without_arg = render(prospect, AUTHOR, AUTHOR_URL)
        assert with_none == without_arg

    def test_slot_vacio_en_ai_copy_no_pisa_el_default(self, prospect):
        default_markup = render(prospect, AUTHOR, AUTHOR_URL)
        markup = render(prospect, AUTHOR, AUTHOR_URL, ai_copy={"cta_body": ""})
        assert markup == default_markup

    def test_escapa_html_del_copy_generado(self, prospect):
        markup = render(
            prospect, AUTHOR, AUTHOR_URL, ai_copy={"cta_body": '<script>alert(1)</script>'}
        )
        assert "<script>alert" not in markup
        assert "&lt;script&gt;" in markup

    def test_generate_acepta_ai_copy(self, prospect, tmp_path, monkeypatch):
        from gtm.factory import config

        monkeypatch.setattr(config, "DEMOS_DIR", tmp_path / "demos")
        monkeypatch.setattr(config, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")

        demo = generate(
            prospect, AUTHOR, AUTHOR_URL, ai_copy={"cta_body": "Copy custom."}
        )
        written = (tmp_path / "demos" / prospect.slug / "index.html").read_text(encoding="utf-8")
        assert "Copy custom." in written
        assert demo.slug == prospect.slug


class TestArticuloEnLaDemo:
    def test_hvac_usa_an(self):
        hvac = Prospect(
            place_id="p1",
            name="Sonoran Air Conditioning",
            vertical="hvac",
            metro="Tucson, AZ",
            phone="(520) 555-0148",
        )
        markup = render(hvac, AUTHOR, AUTHOR_URL)
        assert "Need an HVAC contractor now?" in markup
        assert "Need a HVAC" not in markup

    def test_plumber_usa_a(self, prospect):
        markup = render(prospect, AUTHOR, AUTHOR_URL)
        assert "Need a plumber now?" in markup
