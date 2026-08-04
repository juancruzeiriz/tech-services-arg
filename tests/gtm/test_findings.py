"""Tests del catálogo de hallazgos (gtm/factory/findings.py)."""

from __future__ import annotations

from gtm.factory.findings import FINDINGS, Dimension, Finding, Severity
from gtm.factory.types import Language


def test_todo_hallazgo_tiene_copy_en_los_dos_idiomas():
    for code, spec in FINDINGS.items():
        assert spec.sales_line_en.strip(), f"{code} sin copy EN"
        assert spec.sales_line_es.strip(), f"{code} sin copy ES"


def test_la_linea_de_venta_interpola_la_evidencia():
    finding = Finding(code="no_tel_link", evidence="teléfono en texto plano")
    linea = finding.sales_line(Language.ES)
    assert "teléfono en texto plano" in linea


def test_la_linea_en_ingles_tambien_interpola():
    finding = Finding(code="stale_since", evidence="March 2016")
    linea = finding.sales_line(Language.EN)
    assert "March 2016" in linea


def test_no_hay_hallazgo_sin_severidad_declarada():
    for code, spec in FINDINGS.items():
        assert isinstance(spec.severity, Severity), f"{code} sin severidad"


def test_no_hay_hallazgo_sin_dimension_declarada():
    for code, spec in FINDINGS.items():
        assert isinstance(spec.dimension, Dimension), f"{code} sin dimensión"


def test_todo_hallazgo_tiene_peso_positivo():
    for code, spec in FINDINGS.items():
        assert spec.weight > 0, f"{code} con peso no positivo"


def test_finding_expone_su_spec_por_codigo():
    finding = Finding(code="no_https", evidence="http://ejemplo.com")
    assert finding.spec is FINDINGS["no_https"]
    assert finding.spec.dimension is Dimension.SEO


def test_finding_default_de_weight_es_uno():
    finding = Finding(code="no_https", evidence="x")
    assert finding.weight == 1.0


def test_severity_tiene_los_cuatro_niveles_esperados():
    assert {s.value for s in Severity} == {"critical", "high", "medium", "low"}


def test_dimension_tiene_las_cinco_esperadas():
    assert {d.value for d in Dimension} == {
        "speed",
        "mobile",
        "seo",
        "modernity",
        "conversion",
    }


def test_codigos_de_hallazgo_esperados_estan_presentes():
    # Los códigos que score.py y forensics.py van a emitir en las próximas
    # tareas. Si alguno falta acá, esas tareas van a fallar en import.
    esperados = {
        "no_tel_link",
        "no_contact_method",
        "stale_since",
        "crux_lcp_poor",
        "crux_inp_poor",
        "no_viewport",
        "table_layout",
        "dead_analytics",
        "stale_copyright",
        "legacy_jquery",
        "dated_palette",
        "no_https",
        "no_local_schema",
        "tap_targets",
        "tiny_font",
    }
    assert esperados <= FINDINGS.keys()
