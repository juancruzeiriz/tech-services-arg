"""Tests del informe de auditoría privado (gtm/factory/audit.py)."""

from __future__ import annotations

import html

from gtm.factory.audit import generate, render
from gtm.factory.findings import Finding
from gtm.factory.types import Language, PainScore

AUTHOR = "Juan Cruz Eiriz"


def _score(**overrides: object) -> PainScore:
    defaults: dict[str, object] = {
        "place_id": "ChIJtest123",
        "performance": 32,
        "seo": 55,
        "accessibility": 80,
        "mobile_friendly": False,
        "findings": (
            Finding(code="no_tel_link", evidence="555-0142", weight=3.0),
            Finding(code="dated_palette", evidence="9", weight=1.0),
        ),
    }
    defaults.update(overrides)
    return PainScore(**defaults)  # type: ignore[arg-type]


class TestRender:
    def test_usa_datos_reales_del_negocio(self, prospect):
        markup = render(prospect, _score(), AUTHOR)
        assert html.escape(prospect.name) in markup
        assert "Tucson" in markup

    def test_no_deja_placeholders_sin_resolver(self, prospect):
        markup = render(prospect, _score(), AUTHOR)
        assert "$business_name" not in markup
        assert "$report_title" not in markup
        assert "$findings_html" not in markup

    def test_incluye_el_puntaje(self, prospect):
        score = _score()
        markup = render(prospect, score, AUTHOR)
        assert f'<span class="score-value">{score.score}</span>' in markup

    def test_incluye_las_sales_lines_del_mas_grave_al_menos_grave(self, prospect):
        score = _score()
        markup = render(prospect, score, AUTHOR)
        # quotable_only=False: el informe interno (_findings_html en audit.py) usa
        # ese mismo argumento a propósito -- es material de apoyo para la llamada,
        # no algo que se le manda al prospecto, así que también muestra hallazgos
        # como dated_palette que el gancho del email omite (ver PainScore.sales_lines).
        lines = score.sales_lines(Language.EN, quotable_only=False)
        assert len(lines) == 2
        assert markup.index(html.escape(lines[0])) < markup.index(html.escape(lines[1]))

    def test_marca_el_documento_como_interno(self, prospect):
        markup = render(prospect, _score(), AUTHOR)
        assert "Internal document" in markup
        assert "not meant to be sent to the prospect as-is" in markup

    def test_lleva_noindex(self, prospect):
        markup = render(prospect, _score(), AUTHOR)
        assert 'name="robots" content="noindex,nofollow"' in markup

    def test_no_hace_requests_externas(self, prospect):
        markup = render(prospect, _score(), AUTHOR)
        for pattern in ("<script", "src=\"http", "@import", "<link rel=\"stylesheet\""):
            assert pattern not in markup

    def test_escapa_html_del_nombre(self, prospect):
        from gtm.factory.types import Prospect

        hostile = Prospect(
            place_id="p1",
            name='Bob <script>alert("xss")</script> Plumbing',
            vertical="plumber",
            metro="Mesa, AZ",
        )
        markup = render(hostile, _score(place_id="p1"), AUTHOR)
        assert "<script>alert" not in markup
        assert "&lt;script&gt;" in markup

    def test_sin_findings_muestra_texto_alternativo(self, prospect):
        markup = render(prospect, _score(findings=()), AUTHOR)
        assert "No automated, citable findings" in markup

    def test_sin_telefono_no_falla(self):
        """A diferencia de generate.render, acá el teléfono no es obligatorio:
        el informe se puede generar para un prospecto sin sitio (score=100)."""
        from gtm.factory.types import Prospect

        no_phone = Prospect(place_id="p1", name="X", vertical="plumber", metro="Mesa, AZ")
        markup = render(no_phone, _score(place_id="p1"), AUTHOR)
        assert "X" in markup

    def test_notas_se_muestran_sin_importar_el_idioma(self, prospect):
        score = _score(notes=("Rendimiento móvil 32/100: pierde tráfico.",))
        markup_en = render(prospect, score, AUTHOR, Language.EN)
        markup_es = render(prospect, score, AUTHOR, Language.ES)
        assert "Rendimiento móvil 32/100" in markup_en
        assert "Rendimiento móvil 32/100" in markup_es


class TestRenderEnEspanol:
    def test_lang_del_html_es_es(self, prospect):
        markup = render(prospect, _score(), AUTHOR, Language.ES)
        assert '<html lang="es">' in markup

    def test_lang_por_defecto_es_en(self, prospect):
        markup = render(prospect, _score(), AUTHOR)
        assert '<html lang="en">' in markup

    def test_no_mezcla_idiomas(self, prospect):
        markup = render(prospect, _score(), AUTHOR, Language.ES)
        for english_only in ("Internal document", "Findings, most severe first", "Additional notes"):
            assert english_only not in markup

    def test_incluye_las_sales_lines_en_espanol(self, prospect):
        score = _score()
        markup = render(prospect, score, AUTHOR, Language.ES)
        for line in score.sales_lines(Language.ES):
            assert html.escape(line) in markup


class TestCaption:
    def test_prospecto_calificado_dice_que_justifica_la_llamada(self, prospect):
        score = _score()  # findings suficientes para calificar
        assert score.is_qualified
        markup = render(prospect, score, AUTHOR)
        assert "Qualifies as a prospect" in markup

    def test_prospecto_no_calificado_dice_que_esta_por_debajo_del_umbral(self, prospect):
        score = _score(performance=95, seo=95, accessibility=95, mobile_friendly=True, findings=())
        assert not score.is_qualified
        markup = render(prospect, score, AUTHOR)
        assert "Below the qualification threshold" in markup


class TestGenerate:
    def test_escribe_el_html_en_disco(self, prospect, tmp_path):
        path = generate(prospect, _score(), AUTHOR, audits_dir=tmp_path)
        written = (tmp_path / prospect.slug / "index.html").read_text(encoding="utf-8")
        assert str(tmp_path / prospect.slug / "index.html") == path
        assert html.escape(prospect.name) in written

    def test_es_idempotente(self, prospect, tmp_path):
        first = generate(prospect, _score(), AUTHOR, audits_dir=tmp_path)
        second = generate(prospect, _score(), AUTHOR, audits_dir=tmp_path)
        assert first == second

    def test_nunca_escribe_en_el_directorio_publico(self, prospect, tmp_path, monkeypatch):
        """Regresión de diseño: un informe interno no puede terminar en el
        camino que `deploy.py` sube al hosting público."""
        from gtm.factory import config

        monkeypatch.setattr(config, "AUDITS_DIR", tmp_path / "audits")
        monkeypatch.setattr(config, "BUILD_DIR", tmp_path / "build")
        monkeypatch.setattr(config, "DEMOS_DIR", tmp_path / "demos")
        monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")

        path = generate(prospect, _score(), AUTHOR)
        assert "public" not in path
        assert str(tmp_path / "audits") in path
