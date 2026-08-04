"""Tests del catálogo de oficios y metros.

No prueban valores de negocio (ticket promedio, %hispano) — esos son datos, no
lógica, y viven en el YAML con su fuente en un comentario. Prueban que el catálogo
sea internamente consistente y que `types.indefinite_article` (que sí es lógica, y
tiene su propia suite de regresión) siga funcionando sobre cada etiqueta real.
"""

from __future__ import annotations

import re

from gtm.catalog import get_metro, get_metro_by_display, get_trade, metros, trades
from gtm.factory.types import indefinite_article

_METRO_DISPLAY_RE = re.compile(r"^[^,]+, [A-Z]{2}$")


class TestTrades:
    def test_hay_entre_5_y_20_oficios(self):
        assert 5 <= len(trades()) <= 20

    def test_las_keys_son_unicas(self):
        keys = [t.key for t in trades()]
        assert len(keys) == len(set(keys))

    def test_los_ranks_son_unicos(self):
        ranks = [t.rank for t in trades()]
        assert len(ranks) == len(set(ranks))

    def test_estan_ordenados_por_rank(self):
        ranks = [t.rank for t in trades()]
        assert ranks == sorted(ranks)

    def test_cada_etiqueta_resuelve_articulo(self):
        for trade in trades():
            assert indefinite_article(trade.label_en) in ("a", "an")
            assert trade.article_en in ("a", "an")

    def test_el_articulo_declarado_coincide_con_la_heuristica(self):
        """`article_en` es dato curado a mano; no debe divergir de la lógica que ya
        tiene su propia suite de regresión (`TestIndefiniteArticle`)."""
        for trade in trades():
            assert trade.article_en == indefinite_article(trade.label_en)

    def test_plural_en_es_no_vacio(self):
        for trade in trades():
            assert trade.plural_en.strip()
            assert trade.plural_es.strip()

    def test_urgencia_es_valida(self):
        for trade in trades():
            assert trade.urgency in ("high", "medium", "low")

    def test_ticket_promedio_positivo(self):
        for trade in trades():
            assert trade.avg_ticket_usd > 0

    def test_servicios_en_y_es_tienen_la_misma_cantidad(self):
        for trade in trades():
            assert len(trade.services_en) == len(trade.services_es) >= 1

    def test_tiene_al_menos_un_prefijo_y_un_sufijo_de_nombre(self):
        for trade in trades():
            assert len(trade.name_prefixes) >= 1
            assert len(trade.name_suffixes) >= 1

    def test_tiene_reseñas_de_ejemplo(self):
        for trade in trades():
            assert len(trade.sample_reviews_en) >= 1

    def test_get_trade_es_case_insensitive(self):
        assert get_trade("HVAC") is get_trade("hvac")

    def test_get_trade_desconocido_es_none_no_excepcion(self):
        assert get_trade("alpaca-shearer") is None

    def test_get_trade_string_vacio_es_none(self):
        assert get_trade("") is None


class TestMetros:
    def test_hay_entre_5_y_20_metros(self):
        assert 5 <= len(metros()) <= 20

    def test_las_keys_son_unicas(self):
        keys = [m.key for m in metros()]
        assert len(keys) == len(set(keys))

    def test_los_ranks_son_unicos(self):
        ranks = [m.rank for m in metros()]
        assert len(ranks) == len(set(ranks))

    def test_estan_ordenados_por_rank(self):
        ranks = [m.rank for m in metros()]
        assert ranks == sorted(ranks)

    def test_display_tiene_el_formato_ciudad_coma_estado(self):
        """El formato que ya espera el resto del pipeline: metro.split(',')[0]."""
        for metro in metros():
            assert _METRO_DISPLAY_RE.match(metro.display), metro.display

    def test_display_empieza_con_la_ciudad(self):
        for metro in metros():
            assert metro.display.startswith(metro.city)

    def test_porcentaje_hispano_en_rango(self):
        for metro in metros():
            assert 0.0 <= metro.hispanic_pct <= 100.0

    def test_idioma_default_es_valido(self):
        for metro in metros():
            assert metro.language_default in ("en", "es")

    def test_get_metro_es_case_insensitive(self):
        assert get_metro("TUCSON-AZ") is get_metro("tucson-az")

    def test_get_metro_by_display(self):
        found = get_metro_by_display("Tucson, AZ")
        assert found is not None
        assert found.key == "tucson-az"

    def test_get_metro_desconocido_es_none(self):
        assert get_metro("nowhere-xx") is None
        assert get_metro_by_display("Nowhere, XX") is None
