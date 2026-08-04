"""Tests de `gtm/factory/stats.py` -- solo el intervalo de Wilson."""

from __future__ import annotations

from gtm.factory.stats import wilson_interval


class TestWilsonInterval:
    def test_n_cero_no_rompe(self):
        assert wilson_interval(0, 0) == (0.0, 0.0)

    def test_intervalo_contiene_la_tasa_puntual(self):
        low, high = wilson_interval(5, 20)
        assert low <= 5 / 20 <= high

    def test_nunca_sale_de_0_1(self):
        low, high = wilson_interval(0, 3)
        assert 0.0 <= low <= high <= 1.0
        low, high = wilson_interval(3, 3)
        assert 0.0 <= low <= high <= 1.0

    def test_muestra_chica_da_intervalo_ancho(self):
        """n=3 con 1 éxito no puede angostarse a algo que se lea como certeza --
        es exactamente el error de potencia que motivó re-registrar
        decision_criteria.yaml."""
        low, high = wilson_interval(1, 3)
        assert high - low > 0.4

    def test_muestra_grande_angosta_el_intervalo(self):
        low, high = wilson_interval(100, 1000)
        assert high - low < 0.05

    def test_sin_exitos_el_piso_es_cero(self):
        low, _ = wilson_interval(0, 50)
        assert low == 0.0

    def test_todos_exitos_el_techo_es_uno(self):
        _, high = wilson_interval(50, 50)
        assert high == 1.0
