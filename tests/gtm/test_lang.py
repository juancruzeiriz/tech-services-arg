"""Tests de la detección de idioma por prospecto (`gtm/factory/lang.py`).

`RunContext.language` es un parámetro de la corrida entera, pero el par
elegido (tree_service × Albuquerque, NM) tiene una población de negocios
genuinamente mixta -- esta heurística deriva un idioma por negocio a partir
de datos que ya existen (nombre, y opcionalmente HTML si el llamador lo
tiene a mano), sin agregar ningún request nuevo.
"""

from __future__ import annotations

from gtm.factory import lang
from gtm.factory.types import Language, Prospect


def _prospect(name: str) -> Prospect:
    return Prospect(place_id="p1", name=name, vertical="tree_service", metro="Albuquerque, NM")


class TestSenalDelNombre:
    def test_nombre_en_ingles_usa_el_default(self):
        assert lang.detect_language(_prospect("Legacy Tree Company")) is Language.EN

    def test_nombre_con_acento_devuelve_es(self):
        assert lang.detect_language(_prospect("Jardinería López")) is Language.ES

    def test_nombre_con_tokens_espanoles_sin_acentos_devuelve_es(self):
        assert lang.detect_language(_prospect("Poda de Arboles Hermanos Garcia")) is Language.ES

    def test_un_solo_token_comun_no_alcanza(self):
        """"La" sola aparece en nombres en inglés también ("La Casa Bar") --
        hace falta más de una coincidencia para no disparar falsos positivos."""
        assert lang.detect_language(_prospect("La Casa Bar")) is Language.EN

    def test_apellido_hispano_con_tilde_alcanza_solo(self):
        assert lang.detect_language(_prospect("Núñez Landscaping")) is Language.ES


class TestDefault:
    def test_sin_senales_usa_el_default_configurado(self):
        assert lang.detect_language(_prospect("Acme Co"), default=Language.ES) is Language.ES

    def test_default_es_ingles_si_no_se_especifica(self):
        assert lang.detect_language(_prospect("Acme Co")) is Language.EN

    def test_el_nombre_manda_sobre_el_default(self):
        """Una señal fuerte del nombre no debe ser tapada por el default de
        la corrida -- ver el docstring del módulo."""
        assert lang.detect_language(_prospect("Jardinería López"), default=Language.EN) is Language.ES


class TestSenalDelHtml:
    def test_html_lang_es_detecta_espanol(self):
        html = '<html lang="es"><head></head><body>Contact us</body></html>'
        assert lang.detect_language(_prospect("Legacy Tree Company"), html=html) is Language.ES

    def test_stopwords_en_espanol_detectan_idioma(self):
        html = (
            "<html><body>Presupuesto gratis. Contacto: llámenos. "
            "Servicios de poda.</body></html>"
        )
        assert lang.detect_language(_prospect("Legacy Tree Company"), html=html) is Language.ES

    def test_html_en_ingles_no_dispara(self):
        html = '<html lang="en"><body>Contact us for a free quote today</body></html>'
        assert lang.detect_language(_prospect("Legacy Tree Company"), html=html) is Language.EN

    def test_sin_html_no_rompe(self):
        assert lang.detect_language(_prospect("Legacy Tree Company"), html=None) is Language.EN
