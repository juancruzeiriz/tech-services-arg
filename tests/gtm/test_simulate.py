"""Tests de `simulate.py`. No existían antes de que el catálogo reemplazara a los
diccionarios `_NAME_PARTS`/`_REVIEWS` hardcodeados a 4 oficios."""

from __future__ import annotations

from gtm.factory.simulate import simulate


class TestSimulate:
    def test_vertical_desconocido_cae_a_hvac(self):
        """Un oficio de texto libre que no está en el catálogo no debe romper la
        simulación: usa los nombres/reseñas de HVAC como base plausible."""
        prospects, scores = simulate("alpaca-shearer", "Tucson, AZ", count=5, seed=1)
        assert len(prospects) == 5
        assert len(scores) == 5
        assert all(p.vertical == "alpaca-shearer" for p in prospects)

    def test_landscaper_ya_no_usa_nombres_de_hvac(self):
        """Regresión: antes de que el catálogo creciera, cualquier vertical fuera
        de {hvac, plumber, electrician, roofer} —incluido landscaper— heredaba los
        nombres sintéticos de HVAC ("... Air Conditioning", "... Cooling & Heating").
        Ahora landscaper tiene su propio catálogo."""
        _, _ = simulate("hvac", "Tucson, AZ", count=3, seed=1)
        landscaper_prospects, _ = simulate("landscaper", "Tucson, AZ", count=10, seed=1)
        hvac_suffixes = ("Air Conditioning", "Cooling & Heating", "HVAC Services")
        assert not any(
            name.endswith(hvac_suffixes) for name in (p.name for p in landscaper_prospects)
        )

    def test_direccion_usa_la_ciudad_del_metro_real(self):
        """Regresión: la dirección sintética quedaba hardcodeada a ", Tucson, AZ"
        sin importar qué metro se pidiera — ahora que el catálogo cubre 20 metros,
        simular Miami no puede devolver una dirección de Tucson."""
        prospects, _ = simulate("hvac", "Miami, FL", count=5, seed=1)
        for prospect in prospects:
            assert prospect.address is not None
            assert "Miami, FL" in prospect.address
            assert "Tucson" not in prospect.address

    def test_direccion_con_metro_de_catalogo_usa_el_estado_correcto(self):
        prospects, _ = simulate("plumber", "houston-tx", count=3, seed=1)
        for prospect in prospects:
            assert prospect.address is not None
            assert "Houston, TX" in prospect.address

    def test_direccion_con_metro_libre_sin_coma_no_inventa_estado(self):
        prospects, _ = simulate("plumber", "Somewhereville", count=3, seed=1)
        for prospect in prospects:
            assert prospect.address is not None
            assert prospect.address.endswith("Somewhereville")

    def test_es_determinista_por_seed(self):
        a_prospects, a_scores = simulate("hvac", "Tucson, AZ", count=8, seed=7)
        b_prospects, b_scores = simulate("hvac", "Tucson, AZ", count=8, seed=7)
        assert [p.name for p in a_prospects] == [p.name for p in b_prospects]
        assert [s.score for s in a_scores] == [s.score for s in b_scores]

    def test_cuenta_pedida_se_respeta(self):
        prospects, scores = simulate("roofer", "Phoenix, AZ", count=12, seed=3)
        assert len(prospects) == 12
        assert len(scores) == 12
