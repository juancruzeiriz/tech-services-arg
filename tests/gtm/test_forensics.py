"""Tests del detector forense de obsolescencia (gtm/factory/forensics.py)."""

from __future__ import annotations

from gtm.factory.forensics import analyse_html, palette_age_signal

_VIEJO = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html><head><meta name="generator" content="Microsoft FrontPage 5.0">
<script src="/js/jquery-1.7.2.min.js"></script>
<script src="https://www.google-analytics.com/ga.js"></script></head>
<body bgcolor="#FFFFFF"><table width="800" bgcolor="#000080"><tr><td align="center">
<font size="2">Llamanos al 555-0100</font></td></tr>
<tr><td><table width="100%"><tr><td>anidada</td></tr></table></td></tr></table>
<p>&copy; 2014 Plomer&iacute;a Acme</p></body></html>"""

_MODERNO = """<!doctype html><html><head><meta name="viewport" content="width=device-width">
<style>:root{--brand:#1f2937}main{display:grid;gap:clamp(1rem,3vw,2rem)}</style>
<script type="application/ld+json">{"@type":"LocalBusiness"}</script>
<meta property="og:title" content="x"></head>
<body><a href="tel:+15555550100">Llamar</a>
<a href="https://facebook.com/plomeriaacme">Facebook</a>
<img src="/h.webp" srcset="/h.webp 800w" loading="lazy" alt="x"></body></html>"""


def test_detecta_maquetacion_con_tablas():
    codes = {f.code for f in analyse_html(_VIEJO, "http://x.com")}
    assert "table_layout" in codes


def test_la_evidencia_de_tablas_cuenta_las_anidadas():
    hallazgos = {f.code: f for f in analyse_html(_VIEJO, "http://x.com")}
    assert "2" in hallazgos["table_layout"].evidence


def test_detecta_universal_analytics_apagado():
    hallazgos = {f.code: f for f in analyse_html(_VIEJO, "http://x.com")}
    assert "dead_analytics" in hallazgos
    assert "ga.js" in hallazgos["dead_analytics"].evidence


def test_no_confunde_gtag_moderno_con_analytics_muerto():
    html = _VIEJO.replace(
        '<script src="https://www.google-analytics.com/ga.js"></script>',
        '<script src="https://www.googletagmanager.com/gtag/js?id=G-ABC123"></script>',
    )
    codes = {f.code for f in analyse_html(html, "http://x.com")}
    assert "dead_analytics" not in codes


def test_detecta_copyright_congelado_y_cita_el_anio():
    hallazgos = {f.code: f for f in analyse_html(_VIEJO, "http://x.com")}
    assert "stale_copyright" in hallazgos
    assert "2014" in hallazgos["stale_copyright"].evidence


def test_un_copyright_reciente_no_dispara_el_hallazgo():
    html = _VIEJO.replace("2014", "2025")
    codes = {f.code for f in analyse_html(html, "http://x.com")}
    assert "stale_copyright" not in codes


def test_detecta_jquery_viejo_con_la_version_exacta():
    hallazgos = {f.code: f for f in analyse_html(_VIEJO, "http://x.com")}
    assert "legacy_jquery" in hallazgos
    assert "1.7.2" in hallazgos["legacy_jquery"].evidence


def test_jquery_3_no_dispara_el_hallazgo():
    html = _VIEJO.replace("jquery-1.7.2.min.js", "jquery-3.7.1.min.js")
    codes = {f.code for f in analyse_html(html, "http://x.com")}
    assert "legacy_jquery" not in codes


def test_detecta_falta_de_viewport():
    assert "no_viewport" in {f.code for f in analyse_html(_VIEJO, "http://x.com")}


def test_con_viewport_no_dispara_el_hallazgo():
    codes = {f.code for f in analyse_html(_MODERNO, "https://x.com")}
    assert "no_viewport" not in codes


def test_detecta_telefono_no_tocable():
    # Hay un número visible pero cero <a href="tel:">: en un celular no se
    # puede llamar tocando. Es el hallazgo que más plata mueve.
    assert "no_tel_link" in {f.code for f in analyse_html(_VIEJO, "http://x.com")}


def test_un_tel_href_real_no_dispara_el_hallazgo():
    codes = {f.code for f in analyse_html(_MODERNO, "https://x.com")}
    assert "no_tel_link" not in codes


def test_http_sin_s_es_hallazgo_critico():
    assert "no_https" in {f.code for f in analyse_html(_VIEJO, "http://x.com")}


def test_https_no_dispara_el_hallazgo():
    codes = {f.code for f in analyse_html(_MODERNO, "https://x.com")}
    assert "no_https" not in codes


def test_detecta_falta_de_schema_local():
    assert "no_local_schema" in {f.code for f in analyse_html(_VIEJO, "http://x.com")}


def test_con_local_business_schema_no_dispara_el_hallazgo():
    codes = {f.code for f in analyse_html(_MODERNO, "https://x.com")}
    assert "no_local_schema" not in codes


def test_detecta_falta_de_presencia_social():
    assert "no_social_presence" in {f.code for f in analyse_html(_VIEJO, "http://x.com")}


def test_un_link_a_facebook_no_dispara_el_hallazgo():
    codes = {f.code for f in analyse_html(_MODERNO, "https://x.com")}
    assert "no_social_presence" not in codes


def test_un_link_a_instagram_tambien_cuenta():
    html = _MODERNO.replace("https://facebook.com/plomeriaacme", "https://instagram.com/plomeriaacme")
    codes = {f.code for f in analyse_html(html, "https://x.com")}
    assert "no_social_presence" not in codes


def test_un_sitio_moderno_no_dispara_hallazgos_de_obsolescencia():
    codes = {f.code for f in analyse_html(_MODERNO, "https://x.com")}
    assert codes.isdisjoint({
        "table_layout",
        "no_viewport",
        "dead_analytics",
        "legacy_jquery",
        "no_tel_link",
        "no_https",
        "no_local_schema",
        "stale_copyright",
        "no_social_presence",
    })


def test_la_paleta_vieja_se_detecta_por_saturacion_y_cantidad():
    vieja = ["#FF0000", "#0000FF", "#000080", "#FFFF00", "#00FF00", "#FF00FF", "#008000", "#800080"]
    moderna = ["#0f172a", "#1f2937", "#64748b", "#f8fafc", "#ff4d18"]
    assert palette_age_signal(vieja) > palette_age_signal(moderna)


def test_palette_age_signal_queda_en_0_1():
    assert 0.0 <= palette_age_signal([]) <= 1.0
    assert 0.0 <= palette_age_signal(["#FF0000"] * 50) <= 1.0


def test_el_analisis_nunca_lanza_con_html_roto():
    for basura in ("", "<html", "\x00\x01", "<html><body>" * 5000):
        analyse_html(basura, "http://x.com")  # no debe lanzar


def test_el_analisis_nunca_lanza_con_url_invalida():
    analyse_html(_VIEJO, "no-es-una-url")


def test_cada_hallazgo_devuelto_tiene_evidencia_no_vacia():
    for finding in analyse_html(_VIEJO, "http://x.com"):
        assert finding.evidence.strip(), f"{finding.code} sin evidencia"
