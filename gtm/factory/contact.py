"""Etapa 6: resolver por qué canal se contacta a cada prospecto y armar la cola.

El problema que resuelve: Google Places no devuelve emails. El pipeline producía
mensajes conformes sin destinatario — el sobre faltaba.

Decisión de diseño: **el pipeline no envía nada, prepara.** A 25 prospectos por semana,
mandar a mano cuesta hora y media, convierte más y evita de raíz los dos riesgos legales
serios del envío automatizado (harvesting de direcciones bajo CAN-SPAM, SMS comercial en
frío bajo TCPA). Lo que se automatiza es la preparación: descubrir el canal disponible de
cada negocio y dejar una cola ordenada por dolor, lista para ejecutar.

La asignación de canal sigue al pain score, y no por casualidad: los prospectos de mayor
dolor son los que no tienen sitio, así que no tienen formulario ni email — pero sí
teléfono, y son pocos. Los de dolor medio sí tienen sitio, así que tienen formulario.

Uso:
    python -m gtm.factory.contact
    python -m gtm.factory.contact --queue    # imprime la cola de trabajo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from gtm.factory import config
from gtm.factory.ledger import SuppressionList
from gtm.factory.logs import get_logger
from gtm.factory.net import DEFAULT_CONCURRENCY, async_client, fetch_text_async, gather_limited
from gtm.factory.types import (
    ContactChannel,
    ContactPlan,
    Demo,
    PainScore,
    Prospect,
    WebPresence,
    vertical_plural,
)

_logger = get_logger(__name__)

# Palabras que en un sitio de home services de USA marcan el formulario de contacto,
# ordenadas por intención: "request a quote" convierte mejor que "contact us".
_FORM_HINTS: tuple[str, ...] = (
    "request-a-quote",
    "request-quote",
    "free-estimate",
    "get-a-quote",
    "schedule",
    "book-now",
    "book",
    "appointment",
    "estimate",
    "quote",
    "contact-us",
    "contact",
)

# Límite conservador: muchos formularios truncan sin avisar y el mensaje llega cortado.
FORM_MESSAGE_MAX_CHARS = 600


def _looks_like_contact_form(soup: BeautifulSoup) -> bool:
    """¿Alguno de los `<form>` de la página espera un mensaje, y no una búsqueda?"""
    for form in soup.find_all("form"):
        if form.find("textarea") is not None:
            return True
        for field in form.find_all("input"):
            field_type = str(field.get("type", "")).lower()
            field_name = str(field.get("name", "")).lower()
            if field_type == "email" or "email" in field_name:
                return True
    return False


async def find_contact_form(client: httpx.AsyncClient, website: str) -> str | None:
    """Ubica la URL del formulario de contacto del sitio del prospecto.

    Devuelve None si el sitio no carga o no hay nada parecido a un formulario.
    """
    fetched = await fetch_text_async(client, website)
    if fetched is None:
        return None

    final_url, markup = fetched
    soup = BeautifulSoup(markup, "html.parser")
    base_host = urlparse(final_url).netloc

    candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue

        absolute = urljoin(final_url, href)
        # Un link a Yelp o Facebook no es el formulario del negocio.
        if urlparse(absolute).netloc != base_host:
            continue

        haystack = f"{absolute.lower()} {anchor.get_text(' ', strip=True).lower()}"
        for rank, hint in enumerate(_FORM_HINTS):
            if hint.replace("-", " ") in haystack or hint in haystack:
                candidates.append((rank, absolute))
                break

    if not candidates:
        # Hay sitios de una sola página con el formulario embebido en la home. Pero
        # cualquier `<form>` no sirve: casi todo sitio tiene un buscador, y mandar el
        # pitch por un cuadro de búsqueda no llega a nadie. Exigimos una señal de que
        # el formulario espera un mensaje: un textarea o un campo de email.
        if _looks_like_contact_form(soup):
            return final_url
        return None

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


async def resolve_contact(
    prospect: Prospect,
    score: PainScore | None = None,
    client: httpx.AsyncClient | None = None,
) -> ContactPlan:
    """Decide el canal de contacto de un prospecto.

    Args:
        prospect: el negocio.
        score: su pain score, solo para ordenar la cola.
        client: cliente compartido del lote. Si es None no se descarga nada y los
            que tienen sitio caen a teléfono (corrida seca).
    """
    pain = score.score if score else 0

    # Sin sitio propio no hay formulario que buscar. Son los de mayor dolor y los
    # que más convierten: van por teléfono.
    if prospect.web_presence in (WebPresence.NONE, WebPresence.SOCIAL_ONLY):
        if prospect.phone:
            return ContactPlan(
                place_id=prospect.place_id,
                channel=ContactChannel.PHONE,
                target=prospect.phone,
                rationale="Sin sitio propio: no hay formulario. Es el prospecto de mayor dolor.",
                pain_score=pain,
            )
        return ContactPlan(
            place_id=prospect.place_id,
            channel=ContactChannel.UNREACHABLE,
            target=None,
            rationale="Sin sitio y sin teléfono.",
            pain_score=pain,
        )

    form_url = (
        await find_contact_form(client, prospect.website or "") if client is not None else None
    )
    if form_url:
        return ContactPlan(
            place_id=prospect.place_id,
            channel=ContactChannel.CONTACT_FORM,
            target=form_url,
            rationale="Formulario propio del negocio: llega a la bandeja que sí leen.",
            pain_score=pain,
        )

    if prospect.phone:
        return ContactPlan(
            place_id=prospect.place_id,
            channel=ContactChannel.PHONE,
            target=prospect.phone,
            rationale="Tiene sitio pero no se ubicó formulario; queda el teléfono.",
            pain_score=pain,
        )

    return ContactPlan(
        place_id=prospect.place_id,
        channel=ContactChannel.UNREACHABLE,
        target=None,
        rationale="Sin formulario ubicable y sin teléfono.",
        pain_score=pain,
    )


def build_form_message(prospect: Prospect, demo: Demo, author_name: str) -> str:
    """Mensaje corto para pegar en un formulario de contacto.

    No es el email recortado: un formulario no admite firma, dirección postal ni link
    de baja, y suele truncar. Va directo al link, que es lo único que importa.
    """
    if not demo.is_live:
        raise ValueError(f"La demo de {prospect.name!r} no tiene URL pública")

    message = (
        f"Hi — I build websites for {vertical_plural(prospect.vertical)} and I made one for "
        f"{prospect.name} as a sample. It is already online here:\n\n"
        f"{demo.url}\n\n"
        "It uses your real phone number, your Google reviews and your service area. "
        "It also texts back automatically when you miss a call.\n\n"
        "Free to look at, yours to keep either way. If you want it pointed at your "
        f"domain it is $950 with a 14-day full refund.\n\n{author_name}"
    )

    if len(message) > FORM_MESSAGE_MAX_CHARS:
        raise ValueError(
            f"Mensaje de {len(message)} caracteres supera el límite de "
            f"{FORM_MESSAGE_MAX_CHARS}: muchos formularios truncan sin avisar"
        )
    return message


def build_call_script(prospect: Prospect, demo: Demo) -> str:
    """Guion de la llamada. Corto a propósito: el objetivo es mandar el link, no vender."""
    city = prospect.metro.split(",")[0].strip()
    return (
        f"Hi, is this {prospect.name}? — I am not a customer, this will take 20 seconds.\n"
        f"I build websites for {vertical_plural(prospect.vertical)} in {city} and I "
        f"already built one for you as a sample. It is online right now.\n"
        f"Can I text you the link so you can look at it later? … Great, it is going to "
        f"this number.\n"
        f"[Enviar SMS: {demo.url}]\n"
        f"No obligation — if you like it I can point it at your domain, if not keep it."
    )


async def resolve_all(
    prospects: list[Prospect],
    scores: dict[str, PainScore],
    probe_site: bool = True,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[ContactPlan]:
    """Resuelve el canal de todos los prospectos, ordenados por dolor descendente.

    Los sitios se descargan en paralelo: son N fetches independientes, y en serie
    50 prospectos son varios minutos de espera de red.
    """
    if probe_site:
        async with async_client(concurrency=concurrency) as client:
            plans = await gather_limited(
                [resolve_contact(p, scores.get(p.place_id), client) for p in prospects],
                concurrency,
            )
    else:
        plans = await gather_limited(
            [resolve_contact(p, scores.get(p.place_id), None) for p in prospects],
            concurrency,
        )

    plans.sort(key=lambda plan: -plan.pain_score)

    by_channel: dict[str, int] = {}
    for plan in plans:
        by_channel[plan.channel.value] = by_channel.get(plan.channel.value, 0) + 1

    _logger.info(
        "canales resueltos",
        extra={
            "event": "contacts_resolved",
            "total": len(plans),
            "actionable": sum(1 for p in plans if p.is_actionable),
            "by_channel": by_channel,
        },
    )
    return plans


def render_queue(
    plans: list[ContactPlan],
    prospects: dict[str, Prospect],
    demos: dict[str, Demo],
    author_name: str,
) -> str:
    """Cola de trabajo en Markdown, ordenada por dolor.

    Es el entregable real de esta etapa: la lista que convierte "tengo un pipeline"
    en "tengo hora y media de trabajo concreto esta semana".
    """
    lines: list[str] = [
        "# Cola de contacto",
        "",
        "Ordenada por dolor descendente. Marcá a medida que avanzás.",
        "",
        "> Sin envío automatizado a propósito: a este volumen, mandar a mano convierte",
        "> más y evita el harvesting de direcciones (CAN-SPAM) y el SMS en frío (TCPA).",
        "",
    ]

    actionable = [plan for plan in plans if plan.is_actionable]
    phone = [p for p in actionable if p.channel is ContactChannel.PHONE]
    forms = [p for p in actionable if p.channel is ContactChannel.CONTACT_FORM]
    skipped = [plan for plan in plans if not plan.is_actionable]

    if phone:
        lines += [f"## Llamadas ({len(phone)})", ""]
        for plan in phone:
            prospect = prospects[plan.place_id]
            demo = demos.get(plan.place_id)
            lines += [
                f"### [ ] {prospect.name} — dolor {plan.pain_score}",
                f"- **Marcar:** {plan.target}",
                f"- **Demo:** {demo.url if demo and demo.is_live else '(sin demo publicada)'}",
                f"- **Por qué así:** {plan.rationale}",
                "",
            ]
            if demo and demo.is_live:
                lines += ["```", build_call_script(prospect, demo), "```", ""]

    if forms:
        lines += [f"## Formularios ({len(forms)})", ""]
        for plan in forms:
            prospect = prospects[plan.place_id]
            demo = demos.get(plan.place_id)
            lines += [
                f"### [ ] {prospect.name} — dolor {plan.pain_score}",
                f"- **Formulario:** {plan.target}",
                f"- **Demo:** {demo.url if demo and demo.is_live else '(sin demo publicada)'}",
                "",
            ]
            if demo and demo.is_live:
                lines += ["```", build_form_message(prospect, demo, author_name), "```", ""]

    if skipped:
        lines += [f"## Descartados ({len(skipped)})", ""]
        lines += [
            f"- {prospects[plan.place_id].name}: {plan.rationale}" for plan in skipped
        ]
        lines.append("")

    return "\n".join(lines)


def _load_scores(path: str) -> dict[str, PainScore]:
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return {}

    return {
        item["place_id"]: PainScore(
            place_id=item["place_id"],
            performance=item.get("performance"),
            seo=item.get("seo"),
            accessibility=item.get("accessibility"),
            mobile_friendly=item.get("mobile_friendly"),
            has_web_presence=item.get("has_web_presence", True),
            reachable=item.get("reachable", True),
        )
        for item in payload
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resuelve canales de contacto y arma la cola")
    parser.add_argument("--prospects", default=None, help="default: gtm/build/data/prospects.json")
    parser.add_argument("--scores", default=None, help="default: gtm/build/data/scores.json")
    parser.add_argument("--demos", default=None, help="default: gtm/build/data/demos.json")
    parser.add_argument("--author-name", default=None, help="default: $GTM_FROM_NAME")
    parser.add_argument(
        "--no-probe",
        action="store_true",
        help="no descarga los sitios; asigna teléfono a todos los que tengan",
    )
    parser.add_argument("--queue", action="store_true", help="imprime la cola por stdout")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"sitios descargados en paralelo (default: {DEFAULT_CONCURRENCY})",
    )
    args = parser.parse_args(argv)

    config.ensure_dirs()
    prospects_path = args.prospects or str(config.DATA_DIR / "prospects.json")
    scores_path = args.scores or str(config.DATA_DIR / "scores.json")
    demos_path = args.demos or str(config.DATA_DIR / "demos.json")
    author_name = args.author_name or config.require_env("GTM_FROM_NAME")

    with open(prospects_path, encoding="utf-8") as handle:
        prospects = {p["place_id"]: Prospect.from_dict(p) for p in json.load(handle)}

    demos: dict[str, Demo] = {}
    try:
        with open(demos_path, encoding="utf-8") as handle:
            for item in json.load(handle):
                demos[item["place_id"]] = Demo(
                    place_id=item["place_id"],
                    slug=item["slug"],
                    html_path=item["html_path"],
                    url=item.get("url"),
                )
    except FileNotFoundError:
        _logger.warning("sin demos publicadas", extra={"event": "no_demos"})

    scores = _load_scores(scores_path)

    # Solo resolvemos canal para prospectos que tienen demo: contactar sin artefacto
    # es el pitch genérico que ya descartaron veinte veces.
    targets = [p for pid, p in prospects.items() if pid in demos]

    # Última barrera antes de que un prospecto llegue a la cola de trabajo: si pidió
    # que no lo contacten, no puede aparecer acá por ningún camino.
    targets, suppressed = SuppressionList().filter_out(targets)

    plans = asyncio.run(
        resolve_all(targets, scores, probe_site=not args.no_probe, concurrency=args.concurrency)
    )

    contacts_path = config.DATA_DIR / "contacts.json"
    with open(contacts_path, "w", encoding="utf-8") as handle:
        json.dump([plan.to_dict() for plan in plans], handle, ensure_ascii=False, indent=2)

    queue = render_queue(plans, prospects, demos, author_name)
    queue_path = config.BUILD_DIR / "queue.md"
    queue_path.write_text(queue, encoding="utf-8")

    if args.queue:
        print(queue)
    else:
        actionable = sum(1 for plan in plans if plan.is_actionable)
        by_phone = sum(1 for p in plans if p.channel is ContactChannel.PHONE)
        by_form = sum(1 for p in plans if p.channel is ContactChannel.CONTACT_FORM)
        print(f"{actionable}/{len(plans)} contactables -> {queue_path}")
        print(f"  {by_phone} por teléfono · {by_form} por formulario")
        if suppressed:
            print(f"  {len(suppressed)} excluidos por la lista de supresión")
    return 0


if __name__ == "__main__":
    sys.exit(main())
