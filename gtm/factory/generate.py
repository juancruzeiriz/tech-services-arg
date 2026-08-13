"""Etapa 3: renderizar la demo personalizada de cada prospecto.

Toda la personalización sale de datos públicos reales del negocio (nombre, teléfono,
rating, reseñas, ciudad). Una demo con placeholders genéricos no vende: el prospecto
la reconoce como plantilla en dos segundos y la descarta.

La demo se marca visiblemente como preview de terceros y sale con `noindex` — no debe
poder confundirse con el sitio oficial del negocio ni competirle en buscadores.

Uso:
    python -m gtm.factory.generate --prospect <place_id>
    python -m gtm.factory.generate --all
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from string import Template

from gtm.catalog import city_of, get_trade
from gtm.factory import artifacts, config, icons
from gtm.factory.copy_ai import SLOTS as _AI_COPY_SLOTS
from gtm.factory.copy_ai import generate_variant_copy
from gtm.factory.ledger import SuppressionList
from gtm.factory.logs import get_logger
from gtm.factory.types import (
    Demo,
    GenerationError,
    Language,
    Prospect,
    indefinite_article,
    vertical_label,
    vertical_plural,
)

_logger = get_logger(__name__)

# Fallback cuando el vertical no está en gtm/catalog/trades.yaml — texto libre desde
# la UI, un oficio que todavía no se agregó. Genérico a propósito: nunca es lo mejor
# que se puede decir de un rubro, pero es mejor que una demo vacía.
_DEFAULT_SERVICES_EN: tuple[tuple[str, str], ...] = (
    ("Repairs", "Fast diagnosis and honest pricing."),
    ("Installation", "Done right the first time."),
    ("Maintenance", "Scheduled service that prevents emergencies."),
    ("Emergency service", "When it cannot wait until Monday."),
)
_DEFAULT_SERVICES_ES: tuple[tuple[str, str], ...] = (
    ("Reparaciones", "Diagnóstico rápido y precios honestos."),
    ("Instalación", "Bien hecho la primera vez."),
    ("Mantenimiento", "Servicio programado que evita las emergencias."),
    ("Emergencias", "Cuando no puede esperar hasta el lunes."),
)


# Identidad visual del vertical fuera de catálogo (texto libre desde la UI): el
# naranja que usaba la plantilla antes de tener paleta por oficio -- mismo criterio
# que _DEFAULT_SERVICES_EN/ES, nunca lo mejor que se puede decir de un rubro, pero
# nunca una demo rota.
_DEFAULT_THEME_PRIMARY = "#c2410c"
_DEFAULT_THEME_PRIMARY_DARK = "#8f2f09"
_DEFAULT_THEME_BG_TINT = "#fff7ed"

# Rotación + opacidad del arte del hero. El place_id (estable, ya usado por
# Prospect.slug) elige una de estas -- así dos demos del mismo oficio en la misma
# ciudad no comparten literalmente el mismo píxel. Ataca el 79% de contenido
# visible idéntico entre demos medido el Día 13 (docs/PLAN_DIARIO.md).
_HERO_ART_VARIANTS: tuple[dict[str, float], ...] = (
    {"rotate": 0, "opacity": 0.14},
    {"rotate": 8, "opacity": 0.16},
    {"rotate": -8, "opacity": 0.12},
    {"rotate": 14, "opacity": 0.18},
    {"rotate": -14, "opacity": 0.13},
)

# Ruta pública de los assets compartidos (`deploy._copy_assets` los deja acá).
# Absoluta de raíz a propósito: las demos viven en `/<slug>/`, así que una ruta
# relativa se rompería al cambiar de nivel.
_ASSETS_URL = "/assets"


def _photo_set(vertical: str) -> tuple[list[str], list[str]]:
    """(heroes, galería) del oficio, por nombre de archivo. Vacías si el oficio
    todavía no tiene fotos curadas -- hoy solo `tree_service`, que es el único con
    prospectos reales. Sin fotos la demo no se rompe: cae al arte de ícono SVG.

    Se lee del disco en vez de hardcodear la lista para que sumar un oficio sea
    copiar archivos a `gtm/assets/photos/<oficio>/`, sin tocar código.
    """
    trade_dir = config.PHOTOS_DIR / vertical
    if not trade_dir.is_dir():
        return [], []
    names = sorted(p.name for p in trade_dir.glob("*.webp"))
    # `-sm` es la variante chica del MISMO hero, no un hero más: se excluye de la
    # lista para que `_pick` no la elija como si fuera otra foto (y para que la
    # cuenta de variantes reales no quede inflada al doble).
    heroes = [n for n in names if n.startswith("hero-") and not n.endswith("-sm.webp")]
    gallery = [n for n in names if n.startswith("work-")]
    return heroes, gallery


def _pick(options: list[str], place_id: str, salt: str = "") -> str:
    """Elige de forma estable (mismo prospecto -> misma foto siempre) pero
    distinta entre prospectos. Sin esto, las 22 demos de Albuquerque abrirían con
    la misma imagen y volveríamos al problema de "se nota la plantilla"."""
    digest = hashlib.sha256(f"{place_id}{salt}".encode()).hexdigest()
    return options[int(digest, 16) % len(options)]


def _theme(vertical: str) -> tuple[str, str, str, str]:
    """(primary, primary_dark, bg_tint, icon_key) del oficio, o el default
    naranja neutro si el vertical no está en el catálogo."""
    trade = get_trade(vertical)
    if trade is None:
        return (
            _DEFAULT_THEME_PRIMARY,
            _DEFAULT_THEME_PRIMARY_DARK,
            _DEFAULT_THEME_BG_TINT,
            icons.DEFAULT_ICON,
        )
    return trade.theme_primary, trade.theme_primary_dark, trade.theme_bg_tint, trade.icon


def _initials(name: str) -> str:
    """Hasta 2 iniciales del nombre real del negocio, para el favicon y el logo.

    Filtra a caracteres alfanuméricos antes de tomar la primera letra de cada
    palabra: un nombre hostil (ver `test_escapa_html_del_nombre`) no sobrevive acá
    como markup, solo como las letras que de verdad tiene.
    """
    words = re.findall(r"[A-Za-z0-9]+", name)
    letters = "".join(word[0] for word in words[:2]).upper()
    return letters or "?"


def _favicon_data_uri(name: str, color: str) -> str:
    """SVG del monograma del negocio, en base64 -- `<link rel="icon" href="data:...">`.
    Sin request, sin archivo, y con identidad real (las iniciales del negocio) en vez
    del ícono vacío que había antes."""
    initials = html.escape(_initials(name))
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        f'<rect width="64" height="64" rx="14" fill="{color}"/>'
        '<text x="32" y="43" font-family="system-ui,sans-serif" font-size="30" '
        f'font-weight="700" fill="#fff" text-anchor="middle">{initials}</text></svg>'
    )
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _logo_svg(color: str, icon_key: str) -> str:
    """Isotipo del header: el ícono del oficio, blanco, sobre un círculo del color
    de marca. No hay logo real del negocio que se pueda usar legalmente -- esto se
    lee como una decisión de diseño, no como un espacio vacío."""
    mark = icons.icon_markup(icon_key, size=20, stroke_width=3)
    return f'<span class="logo-badge" style="background:{color}" aria-hidden="true">{mark}</span>'


def _hero_media(prospect: Prospect, color: str, icon_key: str, alt: str) -> str:
    """Fondo del hero: la foto del oficio si existe, si no el arte de ícono.

    Es el LCP de la página. Por eso:
      - `fetchpriority="high"` y SIN `loading="lazy"` (la galería sí es lazy);
      - `srcset` con una variante chica: el celular del prospecto —que es donde se
        abre esto— baja ~90KB en vez de ~240KB. Medido: sin esto Lighthouse daba
        LCP 4,1s y performance 87.
    """
    heroes, _ = _photo_set(prospect.vertical)
    if heroes:
        name = _pick(heroes, prospect.place_id)
        base = f"{_ASSETS_URL}/photos/{prospect.vertical}"
        small = name.replace(".webp", "-sm.webp")
        has_small = (config.PHOTOS_DIR / prospect.vertical / small).exists()
        srcset = f' srcset="{base}/{small} 820w, {base}/{name} 1200w" sizes="100vw"' if has_small else ""
        return (
            f'<img class="hero-photo" src="{base}/{name}"{srcset} alt="{alt}" '
            'width="1200" height="760" fetchpriority="high" decoding="async">'
        )

    # Fallback sin fotos curadas para el oficio: el arte de ícono de siempre.
    digest = hashlib.sha256(prospect.place_id.encode("utf-8")).hexdigest()
    variant = _HERO_ART_VARIANTS[int(digest, 16) % len(_HERO_ART_VARIANTS)]
    mark = icons.icon_markup(icon_key, size=240, stroke_width=1.4)
    return (
        f'<div class="hero-art" style="color:{color};opacity:{variant["opacity"]};'
        f'transform:rotate({variant["rotate"]}deg)" aria-hidden="true">{mark}</div>'
    )


def _gallery_section(prospect: Prospect, heading: str, alt: str) -> str:
    """Sección "nuestro trabajo" completa, o cadena vacía si el oficio todavía no
    tiene fotos curadas.

    Se decide acá y no en CSS (`:has(:empty)`) a propósito: así un oficio sin fotos
    directamente no emite la sección, sin depender del soporte de `:has()` ni dejar
    un encabezado colgando sobre una grilla vacía.
    """
    _, gallery = _photo_set(prospect.vertical)
    if not gallery:
        return ""

    # Rotada por prospecto: el mismo set de fotos, pero cada demo las muestra en
    # un orden distinto -- otra vuelta de tuerca al "se nota que es plantilla".
    digest = hashlib.sha256(prospect.place_id.encode("utf-8")).hexdigest()
    offset = int(digest, 16) % len(gallery)
    ordered = gallery[offset:] + gallery[:offset]

    shots = "\n".join(
        f'<figure class="shot" data-reveal style="--i:{i}">'
        f'<img src="{_ASSETS_URL}/photos/{prospect.vertical}/{name}" alt="{alt}" '
        'width="700" height="500" loading="lazy" decoding="async"></figure>'
        for i, name in enumerate(ordered)
    )
    return (
        '<section class="gallery">\n  <div class="wrap">\n'
        f'    <div class="section-head"><h2 data-reveal>{heading}</h2></div>\n'
        f'    <div class="shots">{shots}</div>\n'
        "  </div>\n</section>"
    )


def _phone_href(phone: str) -> str:
    """Normaliza a formato tel: (solo dígitos y un + inicial opcional)."""
    cleaned = re.sub(r"[^\d+]", "", phone)
    return cleaned or phone


def _city(prospect: Prospect) -> str:
    """Ciudad legible: el metro viene como 'Tucson, AZ' o una clave del catálogo."""
    return city_of(prospect.metro)


def _services_html(vertical: str, language: Language) -> str:
    trade = get_trade(vertical)
    if trade is not None:
        services: tuple[tuple[str, str], ...] = tuple(
            (s.title, s.body) for s in trade.services(language.value)
        )
    else:
        services = _DEFAULT_SERVICES_ES if language is Language.ES else _DEFAULT_SERVICES_EN
    # data-reveal + --i: stagger de la animación de entrada (ver el bloque
    # @supports(animation-timeline: view()) en site.html). Puramente CSS -- sin
    # esa feature el navegador nunca aplica opacity:0, así que degrada a estático,
    # no a roto.
    return "\n".join(
        f'<div class="card" data-reveal style="--i:{i}"><h3>{html.escape(title)}</h3>'
        f"<p>{html.escape(body)}</p></div>"
        for i, (title, body) in enumerate(services)
    )


def _reviews_html(prospect: Prospect, language: Language) -> str:
    """Renderiza reseñas reales. Se truncan para que no dominen la página."""
    if not prospect.top_reviews:
        # Sin texto de reseñas — `discover.py` no lo pide a propósito: las Service
        # Specific Terms de Google prohíben cachear y republicar ese texto fuera de
        # un mapa de Google. Lo que SÍ se puede mostrar (rating y cantidad) se
        # presenta como un bloque diseñado, con las estrellas dibujadas: antes era
        # una línea itálica suelta en una sección enorme y se leía como un hueco.
        rating = prospect.rating if prospect.rating is not None else 5.0
        full = int(rating)
        stars = "★" * full + "☆" * (5 - full)
        if language is Language.ES:
            unit = "reseña" if prospect.review_count == 1 else "reseñas"
            caption = f"{prospect.review_count} {unit} verificadas en Google"
        else:
            unit = "review" if prospect.review_count == 1 else "reviews"
            caption = f"{prospect.review_count} verified {unit} on Google"
        return (
            '<div class="rating-block">'
            f'<span class="rating-num">{rating}</span>'
            f'<span class="rating-stars" aria-hidden="true">{stars}</span>'
            f'<span class="rating-caption">{html.escape(caption)}</span>'
            "</div>"
        )

    blocks: list[str] = []
    for review in prospect.top_reviews[:3]:
        text = review.strip().replace("\n", " ")
        if len(text) > 240:
            text = text[:237].rstrip() + "…"
        blocks.append(f'<p class="quote">“{html.escape(text)}”</p>')
    return "\n".join(blocks)


def _headline(prospect: Prospect, label: str, language: Language) -> str:
    city = _city(prospect)
    if language is Language.ES:
        return f"{label} en {city}, a una llamada"
    return f"{city}'s {label}, one call away"


def _subheadline(prospect: Prospect, language: Language) -> str:
    if language is Language.ES:
        if prospect.review_count:
            return (
                f"{prospect.review_count} vecinos nos calificaron con {prospect.rating}★. "
                "Llamá ahora y hablá con alguien que te puede dar un turno de verdad."
            )
        return "Llamá ahora y hablá con alguien que te puede dar un turno de verdad."
    if prospect.review_count:
        return (
            f"{prospect.review_count} neighbors have rated us {prospect.rating}★. "
            "Call now and speak to someone who can actually schedule you."
        )
    return "Call now and speak to someone who can actually schedule you."


def _cta_heading(vertical: str, label: str, language: Language) -> str:
    """En inglés compone "Need a/an {label} now?" — el artículo depende de cómo
    suena la etiqueta (ver `indefinite_article`, con su propia suite de regresión).
    En español se evita a propósito construir "un/una {label}": el género
    gramatical del sustantivo no está modelado en el catálogo, así que en vez de
    arriesgar una concordancia mal hecha se usa el plural curado
    (`vertical_plural`), que no necesita artículo y es una forma natural de
    titular en español ("¿Necesitás plomeros ahora?")."""
    if language is Language.ES:
        return f"¿Necesitás {vertical_plural(vertical, language)} ahora?"
    article = indefinite_article(label)
    return f"Need {article} {label} now?"


def render(
    prospect: Prospect,
    author_name: str,
    author_url: str,
    language: Language = Language.EN,
    *,
    ai_copy: dict[str, str] | None = None,
) -> str:
    """Renderiza el HTML de la demo para un prospecto.

    `ai_copy`, si se pasa, sobreescribe únicamente los slots 100% genéricos
    del template (ver `gtm/factory/copy_ai.py` -- nunca un hecho del
    negocio). Claves fuera de ese conjunto se ignoran a propósito: este
    renderer no es el lugar para colar un dato inventado por accidente.

    Raises:
        GenerationError: si falta la plantilla o algún placeholder queda sin valor.
    """
    template_path = config.TEMPLATE_DIR / "site.html"
    if not template_path.exists():
        raise GenerationError(f"Falta la plantilla maestra en {template_path}")

    if not prospect.phone:
        raise GenerationError(
            f"{prospect.name!r} no tiene teléfono: sin él no hay oferta que ofrecer"
        )

    label = vertical_label(prospect.vertical, language)
    business_name = html.escape(prospect.name)
    author_name_esc = html.escape(author_name)
    city = html.escape(_city(prospect))
    phone = html.escape(prospect.phone)
    rating = prospect.rating if prospect.rating is not None else 5.0
    review_count = prospect.review_count
    theme_primary, theme_primary_dark, theme_bg_tint, icon_key = _theme(prospect.vertical)

    if language is Language.ES:
        meta_description = f"{business_name}: {html.escape(label)} en {city}. Llamá al {phone}."
        flag_label = "Sitio de muestra"
        flag_text = (
            f"hecho para {business_name} por {author_name_esc}. No tiene afiliación con "
            f"{business_name} ni fue publicado por ese negocio."
        )
        flag_link_text = "Quién hizo esto"
        call_label = "Llamar"
        trust_rating = f"<b>{rating}★</b><span>{review_count} reseñas</span>"
        trust_serving_label = "Atendemos"
        trust_fast_label = "Respuesta rápida"
        services_heading = "Qué hacemos"
        reviews_heading = "Lo que dicen los clientes"
        gallery_heading = "Nuestro trabajo"
        # alt de las fotos: describe el oficio, no afirma que sean trabajos de ESTE
        # negocio -- son fotos de stock (ver gtm/assets/photos/.../CREDITS.md) y el
        # banner de divulgación ya dice que la demo no la publicó el negocio.
        photo_alt = html.escape(f"Trabajo de {label}")
        cta_body = (
            "Llamá y hablá con una persona real. Si no atendemos, te llega un mensaje "
            "de texto en segundos — no mañana."
        )
        footer_note = (
            f"Muestra hecha por {author_name_esc}. La información del negocio que ves "
            "acá es pública, de Google Maps."
        )
    else:
        meta_description = f"{business_name}: {html.escape(label)} serving {city}. Call {phone}."
        flag_label = "Preview site"
        flag_text = (
            f"built for {business_name} by {author_name_esc}. Not affiliated with, "
            f"or published by, {business_name}."
        )
        flag_link_text = "Who made this"
        call_label = "Call"
        trust_rating = f"<b>{rating}★</b><span>{review_count} reviews</span>"
        trust_serving_label = "Serving"
        trust_fast_label = "Fast response"
        services_heading = "What we do"
        reviews_heading = "What customers say"
        gallery_heading = "The work"
        photo_alt = html.escape(f"{label.capitalize()} work")
        cta_body = (
            "Call and talk to a real person. If we miss you, you get a text back in "
            "seconds — not tomorrow."
        )
        footer_note = (
            f"Preview built by {author_name_esc}. The business information shown here "
            "is public data from Google Maps."
        )

    values = {
        "lang": language.value,
        "theme_primary": theme_primary,
        "theme_primary_dark": theme_primary_dark,
        "theme_bg_tint": theme_bg_tint,
        "favicon_data_uri": _favicon_data_uri(prospect.name, theme_primary),
        "logo_svg": _logo_svg(theme_primary, icon_key),
        "hero_media": _hero_media(prospect, theme_primary, icon_key, photo_alt),
        "gallery_section": _gallery_section(prospect, gallery_heading, photo_alt),
        "business_name": business_name,
        "phone": phone,
        "phone_href": html.escape(_phone_href(prospect.phone)),
        "address": html.escape(prospect.address or _city(prospect)),
        "city": city,
        "vertical_label": html.escape(label),
        "meta_description": meta_description,
        "flag_label": flag_label,
        "flag_text": flag_text,
        "flag_link_text": flag_link_text,
        "call_label": call_label,
        "headline": html.escape(_headline(prospect, label, language)),
        "subheadline": html.escape(_subheadline(prospect, language)),
        "trust_rating": trust_rating,
        "trust_serving_label": trust_serving_label,
        "trust_fast_label": trust_fast_label,
        "services_heading": services_heading,
        "services_html": _services_html(prospect.vertical, language),
        "reviews_heading": reviews_heading,
        "reviews_html": _reviews_html(prospect, language),
        "cta_heading": html.escape(_cta_heading(prospect.vertical, label, language)),
        "cta_body": cta_body,
        "footer_note": footer_note,
        "author_url": html.escape(author_url),
    }

    if ai_copy:
        # Filtro explícito a _AI_COPY_SLOTS: aunque el caller pase un dict con
        # más claves, acá nunca se le da la chance de pisar business_name,
        # phone, address ni ningún otro slot con datos reales del negocio.
        for slot in _AI_COPY_SLOTS:
            value = ai_copy.get(slot)
            if value:
                values[slot] = html.escape(value)

    template = Template(template_path.read_text(encoding="utf-8"))
    try:
        # substitute (no safe_substitute) para que un placeholder sin valor
        # explote acá y no llegue como "$foo" a la cara del prospecto.
        return template.substitute(values)
    except KeyError as exc:
        raise GenerationError(f"Placeholder sin valor en la plantilla: {exc}") from exc


def generate(
    prospect: Prospect,
    author_name: str,
    author_url: str,
    language: Language = Language.EN,
    *,
    demos_dir: Path | None = None,
    ai_copy: dict[str, str] | None = None,
) -> Demo:
    """Renderiza y escribe la demo en disco. Idempotente por slug.

    `demos_dir` sobreescribe `config.DEMOS_DIR` — mismo patrón que `deploy()` con
    `public_dir`. Sin esto, dos corridas de la UI en paralelo (o una corrida de
    prueba y una real) se pisarían el mismo directorio global.
    """
    config.ensure_dirs()
    markup = render(prospect, author_name, author_url, language, ai_copy=ai_copy)

    demo_dir = (demos_dir or Path(config.DEMOS_DIR)) / prospect.slug
    demo_dir.mkdir(parents=True, exist_ok=True)
    html_path = demo_dir / "index.html"
    html_path.write_text(markup, encoding="utf-8")

    _logger.info(
        "demo generada",
        extra={
            "event": "demo_generated",
            "place_id": prospect.place_id,
            "slug": prospect.slug,
            "bytes": len(markup.encode("utf-8")),
        },
    )
    return Demo(
        place_id=prospect.place_id, slug=prospect.slug, html_path=str(html_path), language=language
    )


def load_qualified_ids(scores_path: str) -> set[str] | None:
    """place_ids que superan el umbral de dolor, o None si no hay scores.

    Sin este filtro el pipeline genera y publica demos para negocios cuyo sitio ya
    está bien — trabajo tirado y, peor, un email que el prospecto lee como spam
    porque su sitio anda perfecto y se lo estás cuestionando.
    """
    try:
        with open(scores_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return None

    return {item["place_id"] for item in payload if item.get("is_qualified")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera demos personalizadas")
    parser.add_argument("--input", default=None, help="default: gtm/build/data/prospects.json")
    parser.add_argument("--prospect", default=None, help="place_id único a generar")
    parser.add_argument("--all", action="store_true", help="genera todos los prospectos")
    parser.add_argument("--author-name", default=None, help="default: $GTM_FROM_NAME")
    parser.add_argument("--author-url", default=None, help="default: $GTM_UNSUBSCRIBE_URL")
    parser.add_argument("--scores", default=None, help="default: gtm/build/data/scores.json")
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="genera también los prospectos que no califican (por defecto se omiten)",
    )
    parser.add_argument(
        "--ai-copy",
        action="store_true",
        help=(
            "varía con IA los slots 100% genéricos del template (nunca hechos del "
            "negocio, ver gtm/factory/copy_ai.py) -- degrada a los defaults sin "
            "ANTHROPIC_API_KEY o si la llamada falla"
        ),
    )
    args = parser.parse_args(argv)

    if not args.prospect and not args.all:
        parser.error("indicá --prospect <place_id> o --all")

    config.ensure_dirs()
    input_path = args.input or str(config.DATA_DIR / "prospects.json")
    author_name = args.author_name or config.require_env("GTM_FROM_NAME")
    # GTM_AUTHOR_URL, no GTM_UNSUBSCRIBE_URL: el "Quién hizo esto" del banner es la
    # única vía que tiene el prospecto para averiguar quién le armó el sitio, y hasta
    # 2026-08-13 lo mandaba al formulario de baja. Se mantiene el fallback para no
    # romper entornos que todavía no definieron la variable nueva.
    author_url = (
        args.author_url
        or config.optional_env("GTM_AUTHOR_URL")
        or config.require_env("GTM_UNSUBSCRIBE_URL")
    )

    prospects = artifacts.read_prospects(input_path)
    if args.prospect:
        prospects = [p for p in prospects if p.place_id == args.prospect]
        if not prospects:
            print(f"No hay prospecto con place_id={args.prospect}", file=sys.stderr)
            return 1

    # La supresión va primero: no tiene sentido puntuar ni renderizar a alguien
    # que pidió no ser contactado.
    prospects, suppressed = SuppressionList().filter_out(prospects)

    skipped_unqualified = 0
    if args.all and not args.no_filter:
        scores_path = args.scores or str(config.DATA_DIR / "scores.json")
        qualified = load_qualified_ids(scores_path)
        if qualified is None:
            _logger.warning(
                "sin scores: se generan todos los prospectos sin filtrar",
                extra={"event": "no_scores_filter", "scores_path": scores_path},
            )
        else:
            before = len(prospects)
            prospects = [p for p in prospects if p.place_id in qualified]
            skipped_unqualified = before - len(prospects)

    # Un pedido de IA por oficio, no por prospecto: la variedad que importa es
    # entre rubros, no entre dos plomeros de la misma corrida -- y evita pagar
    # una llamada extra por cada demo generada con --all.
    copy_by_vertical: dict[str, dict[str, str] | None] = {}

    demos: list[Demo] = []
    for prospect in prospects:
        try:
            ai_copy = None
            if args.ai_copy:
                if prospect.vertical not in copy_by_vertical:
                    copy_by_vertical[prospect.vertical] = generate_variant_copy(
                        prospect.vertical, Language.EN
                    )
                ai_copy = copy_by_vertical[prospect.vertical]
            demos.append(generate(prospect, author_name, author_url, ai_copy=ai_copy))
        except GenerationError as exc:
            _logger.warning(
                "demo omitida",
                extra={"event": "demo_skipped", "place_id": prospect.place_id, "error": str(exc)},
            )

    manifest = config.DATA_DIR / "demos.json"
    artifacts.write_demos(manifest, demos)

    reasons: list[str] = []
    if skipped_unqualified:
        reasons.append(f"{skipped_unqualified} no califican")
    if suppressed:
        reasons.append(f"{len(suppressed)} suprimidos")
    suffix = f" ({', '.join(reasons)} omitidos)" if reasons else ""
    print(f"{len(demos)} demos generadas{suffix} -> {config.DEMOS_DIR}")
    for demo in demos:
        print(f"  {demo.slug}/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
