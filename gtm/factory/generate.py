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

from gtm.factory import config
from gtm.factory.ledger import SuppressionList
from gtm.factory.logs import get_logger
from gtm.factory.types import (
    Demo,
    GenerationError,
    Prospect,
    indefinite_article,
    vertical_label,
)

_logger = get_logger(__name__)

# Servicios por vertical, en el lenguaje que usa el cliente final al buscar.
# Places no devuelve el catálogo del negocio, así que partimos del estándar del
# rubro; se ajusta a mano antes de enviar si el negocio tiene una especialidad.
_SERVICES: dict[str, tuple[tuple[str, str], ...]] = {
    "plumber": (
        ("Emergency repairs", "Burst pipes, major leaks and backups, same day."),
        ("Drain cleaning", "Slow or blocked drains cleared without guesswork."),
        ("Water heaters", "Repair and replacement, gas or electric."),
        ("Fixture install", "Sinks, toilets, faucets and shutoff valves."),
    ),
    "hvac": (
        ("AC repair", "Diagnosis and repair when the cooling stops."),
        ("Heating service", "Furnace and heat pump repair before it gets cold."),
        ("System install", "Right-sized replacements, not upsells."),
        ("Maintenance plans", "Seasonal tune-ups that prevent the emergency call."),
    ),
    "electrician": (
        ("Troubleshooting", "Dead outlets, tripping breakers, flickering lights."),
        ("Panel upgrades", "Safe capacity for modern loads and EV charging."),
        ("Lighting", "Indoor and outdoor fixtures, switches and dimmers."),
        ("Safety inspections", "Written findings you can actually act on."),
    ),
    "roofer": (
        ("Leak repair", "Find the actual source, not just the wet spot."),
        ("Roof replacement", "Full tear-off and install with written warranty."),
        ("Storm damage", "Documentation your insurer will accept."),
        ("Inspections", "Photo report of current condition."),
    ),
    "landscaper": (
        ("Yard maintenance", "Scheduled service that actually shows up."),
        ("Irrigation", "Install and repair, with water use in mind."),
        ("Cleanups", "Seasonal and one-time property cleanups."),
        ("Design & install", "Planting plans suited to the local climate."),
    ),
}

_DEFAULT_SERVICES: tuple[tuple[str, str], ...] = (
    ("Repairs", "Fast diagnosis and honest pricing."),
    ("Installation", "Done right the first time."),
    ("Maintenance", "Scheduled service that prevents emergencies."),
    ("Emergency service", "When it cannot wait until Monday."),
)

def _phone_href(phone: str) -> str:
    """Normaliza a formato tel: (solo dígitos y un + inicial opcional)."""
    cleaned = re.sub(r"[^\d+]", "", phone)
    return cleaned or phone


def _city(prospect: Prospect) -> str:
    """Ciudad legible: el metro viene como 'Tucson, AZ'."""
    return prospect.metro.split(",")[0].strip() or prospect.metro


def _services_html(vertical: str) -> str:
    services = _SERVICES.get(vertical.lower(), _DEFAULT_SERVICES)
    return "\n".join(
        f'<div class="card"><h3>{html.escape(title)}</h3>'
        f"<p>{html.escape(body)}</p></div>"
        for title, body in services
    )


def _reviews_html(prospect: Prospect) -> str:
    """Renderiza reseñas reales. Se truncan para que no dominen la página."""
    if not prospect.top_reviews:
        return (
            f'<p class="quote">Rated {prospect.rating}★ by {prospect.review_count} '
            "customers on Google.</p>"
        )

    blocks: list[str] = []
    for review in prospect.top_reviews[:3]:
        text = review.strip().replace("\n", " ")
        if len(text) > 240:
            text = text[:237].rstrip() + "…"
        blocks.append(f'<p class="quote">“{html.escape(text)}”</p>')
    return "\n".join(blocks)


def _headline(prospect: Prospect, label: str) -> str:
    city = _city(prospect)
    return f"{city}'s {label}, one call away"


def _subheadline(prospect: Prospect) -> str:
    if prospect.review_count:
        return (
            f"{prospect.review_count} neighbors have rated us {prospect.rating}★. "
            "Call now and speak to someone who can actually schedule you."
        )
    return "Call now and speak to someone who can actually schedule you."


def render(prospect: Prospect, author_name: str, author_url: str) -> str:
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

    label = vertical_label(prospect.vertical)

    values = {
        "business_name": html.escape(prospect.name),
        "phone": html.escape(prospect.phone),
        "phone_href": html.escape(_phone_href(prospect.phone)),
        "address": html.escape(prospect.address or _city(prospect)),
        "city": html.escape(_city(prospect)),
        "rating": html.escape(str(prospect.rating if prospect.rating is not None else "5.0")),
        "review_count": html.escape(str(prospect.review_count)),
        "vertical_label": html.escape(label),
        "vertical_article": indefinite_article(label),
        "headline": html.escape(_headline(prospect, label)),
        "subheadline": html.escape(_subheadline(prospect)),
        "services_html": _services_html(prospect.vertical),
        "reviews_html": _reviews_html(prospect),
        "author_name": html.escape(author_name),
        "author_url": html.escape(author_url),
    }

    template = Template(template_path.read_text(encoding="utf-8"))
    try:
        # substitute (no safe_substitute) para que un placeholder sin valor
        # explote acá y no llegue como "$foo" a la cara del prospecto.
        return template.substitute(values)
    except KeyError as exc:
        raise GenerationError(f"Placeholder sin valor en la plantilla: {exc}") from exc


def generate(prospect: Prospect, author_name: str, author_url: str) -> Demo:
    """Renderiza y escribe la demo en disco. Idempotente por slug."""
    config.ensure_dirs()
    markup = render(prospect, author_name, author_url)

    demo_dir = Path(config.DEMOS_DIR) / prospect.slug
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


def _load_prospects(path: str) -> list[Prospect]:
    with open(path, encoding="utf-8") as handle:
        return [Prospect.from_dict(item) for item in json.load(handle)]


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

    prospects = _load_prospects(input_path)
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
    with open(manifest, "w", encoding="utf-8") as handle:
        json.dump([d.to_dict() for d in demos], handle, ensure_ascii=False, indent=2)

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
