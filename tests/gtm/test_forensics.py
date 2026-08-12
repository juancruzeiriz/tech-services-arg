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
    """Evidencia cruda "count|nested" -- findings.py la traduce a prosa en el
    idioma correcto recién al renderizar (ver _formatted_table_count)."""
    hallazgos = {f.code: f for f in analyse_html(_VIEJO, "http://x.com")}
    count, _, nested = hallazgos["table_layout"].evidence.partition("|")
    assert count == "2"
    assert nested == "1"


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


def test_detecta_jquery_viejo_con_version_en_query_string():
    """WordPress sirve jQuery como `.../jquery.js?ver=1.12.4` -- versión en el
    query string, no en el nombre de archivo. Confirmado en vivo el 2026-08-12
    contra miamistumpbrothers.com (jQuery 1.12.4 real, sin detectar antes de
    este fix porque `_JQUERY_RE` sola solo mira el nombre de archivo)."""
    html = _VIEJO.replace(
        "/js/jquery-1.7.2.min.js", "/wp-includes/js/jquery/jquery.js?ver=1.12.4"
    )
    hallazgos = {f.code: f for f in analyse_html(html, "http://x.com")}
    assert "legacy_jquery" in hallazgos
    assert "1.12.4" in hallazgos["legacy_jquery"].evidence


def test_jquery_3_en_query_string_no_dispara_el_hallazgo():
    html = _VIEJO.replace(
        "/js/jquery-1.7.2.min.js", "/wp-includes/js/jquery/jquery.js?ver=3.7.1"
    )
    codes = {f.code for f in analyse_html(html, "http://x.com")}
    assert "legacy_jquery" not in codes


def test_un_ver_query_string_sin_jquery_en_el_src_no_dispara_nada():
    """`?ver=1.2.3` es común en CUALQUIER asset de WordPress (CSS, otros JS),
    no solo jQuery. Sin la gate de "jquery" en el src, cualquier script
    versionado dispararía un falso `legacy_jquery`."""
    html = _VIEJO.replace(
        "/js/jquery-1.7.2.min.js", "/wp-content/themes/x/style.js?ver=1.2.3"
    )
    codes = {f.code for f in analyse_html(html, "http://x.com")}
    assert "legacy_jquery" not in codes


def test_un_plugin_con_jquery_en_el_nombre_no_se_confunde_con_jquery_core():
    """Falso positivo real (2026-08-12, legacytreecompany.com): el sitio corre
    jQuery core 3.7.1 (moderno) pero también carga
    `jquery.mobile.min.js?ver=1.4.5` (jQuery Mobile, una librería DISTINTA con
    su propio versionado, empaquetada por un plugin) y
    `jquery.fullscreen.min.js?ver=0.6.0` (otro plugin). Sin restringir el
    fallback de query-string al basename exacto del bundle de jQuery core,
    "1.4.5" o "0.6.0" se atribuían como si fueran la versión de jQuery core
    del sitio -- afirmación falsa y verificable por cualquiera que abra las
    devtools."""
    html = _VIEJO.replace(
        "/js/jquery-1.7.2.min.js",
        "/wp-includes/js/jquery/jquery.min.js?ver=3.7.1\"></script>"
        '<script src="/plugins/photo-gallery/js/jquery.mobile.min.js?ver=1.4.5"></script>'
        '<script src="/plugins/photo-gallery/js/jquery.fullscreen.min.js?ver=0.6.0',
    )
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


def test_mismo_color_en_mayuscula_y_minuscula_no_duplica():
    """Bug real (2026-08-12, legacytreecompany.com): `_normalise_hex` expandía
    `#abc` pero no bajaba a minúscula, así que "#FFFFFF" y "#ffffff" contaban
    como dos colores distintos e inflaban `distinct_frac` -- 3 pares
    duplicados por caso solo en ese sitio."""
    mixto = ["#FFFFFF", "#ffffff", "#000000", "#000000"]
    todo_lower = ["#ffffff", "#ffffff", "#000000", "#000000"]
    assert palette_age_signal(mixto) == palette_age_signal(todo_lower)


def test_paleta_default_de_wordpress_gutenberg_no_cuenta():
    """WordPress core inyecta la paleta default del editor de bloques como
    `--wp--preset--color--<nombre>: #hex;` en cualquier sitio que use bloques
    -- la use el diseño visible o no. Confirmado en vivo el 2026-08-12 contra
    legacytreecompany.com: 7 de sus 37 colores "detectados" eran, exactos,
    esa paleta. Se borra la declaración, no el color: si el negocio usa el
    mismo hex en otra parte del HTML (fuera de un preset), sigue contando.
    """
    wp_presets = (
        ":root{"
        "--wp--preset--color--vivid-cyan-blue: #0693e3;"
        "--wp--preset--color--vivid-green-cyan: #00d084;"
        "--wp--preset--color--luminous-vivid-orange: #ff6900;"
        "}"
    )
    solo_presets = f"<html><style>{wp_presets}</style><body>x</body></html>"
    codes = {f.code for f in analyse_html(solo_presets, "https://x.com")}
    assert "dated_palette" not in codes

    # pero si el MISMO hex aparece fuera de una declaración de preset (el
    # negocio lo usa de verdad, no es boilerplate de WordPress), sigue contando
    usado_de_verdad = (
        f"<html><style>{wp_presets} .cta{{background:#ff6900}}</style>"
        "<body style='color:#0693e3'>"
        "<div style='color:#00d084'>x</div>"
        "<div style='color:#111111'>x</div>"
        "<div style='color:#222222'>x</div>"
        "</body></html>"
    )
    hallazgos = {f.code: f for f in analyse_html(usado_de_verdad, "https://x.com")}
    if "dated_palette" in hallazgos:
        # el conteo de colores distintos no incluye ninguno que SOLO viniera
        # de una declaración de preset ya eliminada
        assert int(hallazgos["dated_palette"].evidence) <= 5


def test_el_analisis_nunca_lanza_con_html_roto():
    for basura in ("", "<html", "\x00\x01", "<html><body>" * 5000):
        analyse_html(basura, "http://x.com")  # no debe lanzar


def test_el_analisis_nunca_lanza_con_url_invalida():
    analyse_html(_VIEJO, "no-es-una-url")


def test_cada_hallazgo_devuelto_tiene_evidencia_no_vacia():
    for finding in analyse_html(_VIEJO, "http://x.com"):
        assert finding.evidence.strip(), f"{finding.code} sin evidencia"
