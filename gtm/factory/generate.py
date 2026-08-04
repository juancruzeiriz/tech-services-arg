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
import html
import json
import re
import sys
from pathlib import Path
from string import Template

from gtm.catalog import city_of, get_trade
from gtm.factory import artifacts, config
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
    return "\n".join(
        f'<div class="card"><h3>{html.escape(title)}</h3>'
        f"<p>{html.escape(body)}</p></div>"
        for title, body in services
    )


def _reviews_html(prospect: Prospect, language: Language) -> str:
    """Renderiza reseñas reales. Se truncan para que no dominen la página."""
    if not prospect.top_reviews:
        rating = prospect.rating
        if language is Language.ES:
            return f'<p class="quote">{rating}★ según {prospect.review_count} clientes en Google.</p>'
        return (
            f'<p class="quote">Rated {rating}★ by {prospect.review_count} '
            "customers on Google.</p>"
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
    prospect: Prospect, author_name: str, author_url: str, language: Language = Language.EN
) -> str:
    """Renderiza el HTML de la demo para un prospecto.

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

    if language is Language.ES:
        meta_description = f"{business_name}: {html.escape(label)} en {city}. Llamá al {phone}."
        flag_label = "Sitio de muestra"
        flag_text = (
            f"hecho para {business_name} por {author_name_esc}. No tiene afiliación con "
            f"{business_name} ni fue publicado por ese negocio."
        )
        flag_link_text = "Quién hizo esto"
        call_label = "Llamar"
        trust_rating = f"<b>{rating}★</b> según {review_count} reseñas"
        trust_serving_label = "Atendemos"
        trust_fast_label = "Respuesta rápida"
        services_heading = "Qué hacemos"
        reviews_heading = "Lo que dicen los clientes"
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
        trust_rating = f"<b>{rating}★</b> from {review_count} reviews"
        trust_serving_label = "Serving"
        trust_fast_label = "Fast response"
        services_heading = "What we do"
        reviews_heading = "What customers say"
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
) -> Demo:
    """Renderiza y escribe la demo en disco. Idempotente por slug.

    `demos_dir` sobreescribe `config.DEMOS_DIR` — mismo patrón que `deploy()` con
    `public_dir`. Sin esto, dos corridas de la UI en paralelo (o una corrida de
    prueba y una real) se pisarían el mismo directorio global.
    """
    config.ensure_dirs()
    markup = render(prospect, author_name, author_url, language)

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
    return Demo(place_id=prospect.place_id, slug=prospect.slug, html_path=str(html_path))


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
    args = parser.parse_args(argv)

    if not args.prospect and not args.all:
        parser.error("indicá --prospect <place_id> o --all")

    config.ensure_dirs()
    input_path = args.input or str(config.DATA_DIR / "prospects.json")
    author_name = args.author_name or config.require_env("GTM_FROM_NAME")
    author_url = args.author_url or config.require_env("GTM_UNSUBSCRIBE_URL")

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

    demos: list[Demo] = []
    for prospect in prospects:
        try:
            demos.append(generate(prospect, author_name, author_url))
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
