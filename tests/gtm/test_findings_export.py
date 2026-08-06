"""Tests del export de copy público (gtm/factory/findings_export.py)."""

from __future__ import annotations

import json

from gtm.factory.findings import FINDINGS
from gtm.factory.findings_export import PUBLIC_CODES, build_export, main


class TestBuildExport:
    def test_solo_incluye_los_codigos_publicos(self):
        export = build_export()
        assert set(export.keys()) == set(PUBLIC_CODES)

    def test_todos_los_codigos_publicos_existen_en_findings(self):
        """Regresión: un typo en PUBLIC_CODES tiene que fallar acá, no en
        producción con un KeyError silencioso."""
        for code in PUBLIC_CODES:
            assert code in FINDINGS

    def test_no_incluye_hallazgos_forenses(self):
        """Los que exigen parsear HTML (jQuery, paleta, copyright, tablas,
        redes sociales) quedan fuera de la versión pública a propósito."""
        export = build_export()
        for forensic_only in ("legacy_jquery", "dated_palette", "stale_copyright", "table_layout", "no_social_presence"):
            assert forensic_only not in export

    def test_cada_entrada_trae_las_dos_lineas_de_venta(self):
        export = build_export()
        for code, spec in export.items():
            assert spec["sales_line_en"], code
            assert spec["sales_line_es"], code

    def test_el_peso_coincide_con_findings_py(self):
        export = build_export()
        for code, spec in export.items():
            assert spec["weight"] == FINDINGS[code].weight


class TestMain:
    def test_escribe_json_valido_en_disco(self, tmp_path):
        output = tmp_path / "audit-findings.json"
        exit_code = main(["--output", str(output)])
        assert exit_code == 0
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert set(payload.keys()) == set(PUBLIC_CODES)

    def test_crea_directorios_intermedios(self, tmp_path):
        output = tmp_path / "nested" / "dir" / "audit-findings.json"
        main(["--output", str(output)])
        assert output.exists()
