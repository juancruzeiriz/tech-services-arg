"""Tests de `gtm/ui/presets.py` -- lectura/escritura directa contra un path
explícito (`tmp_path`), sin pasar por la app ni por `PRESETS_PATH`."""

from __future__ import annotations

from gtm.ui import presets


class TestSaveAndGet:
    def test_guarda_solo_los_campos_conocidos(self, tmp_path):
        path = tmp_path / "presets.json"
        presets.save_preset(
            "hvac-az-es",
            {
                "vertical": "hvac",
                "metro": "tucson-az",
                "language": "es",
                "token_csrf_que_no_deberia_guardarse": "x",
            },
            path=path,
        )
        loaded = presets.get_preset("hvac-az-es", path=path)
        assert loaded == {"vertical": "hvac", "metro": "tucson-az", "language": "es"}

    def test_nombre_vacio_no_guarda_nada(self, tmp_path):
        path = tmp_path / "presets.json"
        presets.save_preset("   ", {"vertical": "hvac"}, path=path)
        assert presets.list_presets(path=path) == []

    def test_preset_inexistente_devuelve_none(self, tmp_path):
        path = tmp_path / "presets.json"
        assert presets.get_preset("no-existe", path=path) is None

    def test_guardar_dos_veces_el_mismo_nombre_sobreescribe(self, tmp_path):
        path = tmp_path / "presets.json"
        presets.save_preset("x", {"vertical": "hvac"}, path=path)
        presets.save_preset("x", {"vertical": "plumbing"}, path=path)
        assert presets.get_preset("x", path=path) == {"vertical": "plumbing"}


class TestListPresets:
    def test_lista_vacia_sin_archivo(self, tmp_path):
        path = tmp_path / "no-existe.json"
        assert presets.list_presets(path=path) == []

    def test_lista_ordenada_alfabeticamente(self, tmp_path):
        path = tmp_path / "presets.json"
        presets.save_preset("zeta", {"vertical": "hvac"}, path=path)
        presets.save_preset("alfa", {"vertical": "plumbing"}, path=path)
        assert presets.list_presets(path=path) == ["alfa", "zeta"]

    def test_json_corrupto_no_rompe(self, tmp_path):
        path = tmp_path / "presets.json"
        path.write_text("{not valid json", encoding="utf-8")
        assert presets.list_presets(path=path) == []


class TestDeletePreset:
    def test_borra_un_preset_existente(self, tmp_path):
        path = tmp_path / "presets.json"
        presets.save_preset("x", {"vertical": "hvac"}, path=path)
        presets.delete_preset("x", path=path)
        assert presets.get_preset("x", path=path) is None

    def test_borrar_uno_inexistente_no_rompe(self, tmp_path):
        path = tmp_path / "presets.json"
        presets.delete_preset("no-existe", path=path)
        assert presets.list_presets(path=path) == []
