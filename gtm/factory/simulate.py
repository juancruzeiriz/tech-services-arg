"""Generador de prospectos sintéticos con distribución realista del vertical.

Sirve para ejercitar el pipeline completo sin gastar cuota de Places ni de PageSpeed,
y para tener fixtures deterministas en los tests.

La distribución no es uniforme a propósito: reproduce lo que se encuentra de verdad al
escanear un vertical de home services en un metro secundario de USA — una quinta parte
sin sitio, otro tanto viviendo en Facebook, y la mayoría del resto con un sitio lento.
Un simulador con datos parejos daría una lectura optimista del embudo.

Uso:
    python -m gtm.factory.simulate --vertical hvac --metro "Tucson, AZ" --count 18
"""

from __future__ import annotations

import argparse
import random
import sys

from gtm.catalog import city_of, get_metro, get_metro_by_display, get_trade
from gtm.factory import artifacts, config
from gtm.factory.logs import get_logger
from gtm.factory.types import PainScore, Prospect, WebPresence

_logger = get_logger(__name__)

# Distribución de presencia web observada en home services de metros secundarios.
_PRESENCE_WEIGHTS: dict[WebPresence, float] = {
    WebPresence.NONE: 0.20,
    WebPresence.SOCIAL_ONLY: 0.15,
    WebPresence.HAS_SITE: 0.65,
}

# De los que tienen sitio, qué fracción está directamente caída o inaccesible.
_UNREACHABLE_RATE = 0.08

# Nombres de calle de relleno para direcciones sintéticas. Con sabor a Tucson porque
# es donde arrancó el pipeline; con 20 metros en el catálogo ya no son geográficamente
# realistas para todos, pero el dato real (dirección real) sale de Places, no de
# `simulate` — esto solo tiene que parecer una dirección, no serlo.
_STREETS = (
    "E Speedway Blvd", "N Oracle Rd", "E Broadway Blvd", "N Campbell Ave",
    "E Grant Rd", "S Kolb Rd", "W Ina Rd", "E 22nd St", "N Swan Rd", "E Golf Links Rd",
)


def _synth_website(rng: random.Random, presence: WebPresence, slug_base: str) -> str | None:
    if presence is WebPresence.NONE:
        return None
    if presence is WebPresence.SOCIAL_ONLY:
        return f"https://facebook.com/{slug_base}"
    return f"https://{slug_base}.example"


def _synth_score(rng: random.Random, place_id: str, presence: WebPresence) -> PainScore:
    """Puntaje coherente con la presencia web del negocio."""
    if presence in (WebPresence.NONE, WebPresence.SOCIAL_ONLY):
        note = (
            "Sin sitio web: el negocio es invisible fuera de Google Maps."
            if presence is WebPresence.NONE
            else "Solo presencia en redes: no controla su canal ni aparece en búsquedas."
        )
        return PainScore(place_id=place_id, has_web_presence=False, notes=(note,))

    if rng.random() < _UNREACHABLE_RATE:
        return PainScore(
            place_id=place_id,
            reachable=False,
            notes=("El sitio declarado no responde.",),
        )

    # Los sitios de home services se agrupan en el rango malo: builders viejos,
    # imágenes sin comprimir y plantillas cargadas de scripts de terceros.
    performance = max(3, min(100, round(rng.gauss(32, 18))))
    seo = max(20, min(100, round(rng.gauss(68, 15))))
    accessibility = max(25, min(100, round(rng.gauss(74, 12))))
    mobile_friendly = rng.random() > 0.18

    notes: list[str] = []
    if performance < 50:
        notes.append(
            f"Rendimiento móvil {performance}/100: el sitio tarda tanto que una parte "
            "del tráfico se va antes de verlo."
        )
    if seo < 70:
        notes.append(f"SEO {seo}/100: pierde búsquedas locales.")

    return PainScore(
        place_id=place_id,
        performance=performance,
        seo=seo,
        accessibility=accessibility,
        mobile_friendly=mobile_friendly,
        notes=tuple(notes),
    )


def simulate(
    vertical: str, metro: str, count: int = 18, seed: int = 42
) -> tuple[list[Prospect], list[PainScore]]:
    """Genera prospectos y sus scores. Determinista por `seed`."""
    rng = random.Random(seed)
    # "hvac" es el fallback para un vertical de texto libre que no está en el
    # catálogo (garantizado presente: es el primer oficio agregado, ver test_catalog).
    trade = get_trade(vertical) or get_trade("hvac")
    assert trade is not None
    prefixes, suffixes = trade.name_prefixes, trade.name_suffixes
    reviews_pool = trade.sample_reviews_en
    city = city_of(metro)
    # Preferí el catálogo para el estado; si el metro es texto libre sin catálogo
    # ("Chandler, AZ" no está en gtm/catalog/metros.yaml) se toma lo que venga
    # después de la coma, y si no hay coma no se inventa un estado.
    metro_entry = get_metro_by_display(metro) or get_metro(metro)
    if metro_entry is not None:
        address_locality = f"{city}, {metro_entry.state}"
    elif "," in metro:
        address_locality = f"{city}, {metro.split(',', 1)[1].strip()}"
    else:
        address_locality = city

    presences = list(_PRESENCE_WEIGHTS)
    weights = [_PRESENCE_WEIGHTS[p] for p in presences]

    used_names: set[str] = set()
    prospects: list[Prospect] = []
    scores: list[PainScore] = []

    while len(prospects) < count:
        name = f"{rng.choice(prefixes)} {rng.choice(suffixes)}"
        if name in used_names:
            continue
        used_names.add(name)

        index = len(prospects)
        place_id = f"ChIJsim{vertical[:4]}{index:03d}"
        presence = rng.choices(presences, weights=weights, k=1)[0]
        slug_base = name.lower().replace(" ", "").replace("&", "")

        prospect = Prospect(
            place_id=place_id,
            name=name,
            vertical=vertical,
            metro=metro,
            phone=f"(520) 555-{rng.randint(100, 199):04d}",
            website=_synth_website(rng, presence, slug_base),
            rating=round(rng.uniform(4.0, 5.0), 1),
            review_count=rng.randint(50, 620),
            address=f"{rng.randint(100, 9999)} {rng.choice(_STREETS)}, {address_locality}",
            top_reviews=tuple(rng.sample(reviews_pool, k=min(2, len(reviews_pool)))),
        )
        prospects.append(prospect)
        scores.append(_synth_score(rng, place_id, presence))

    # Mismo orden que produce el pipeline real: primero el mayor dolor.
    order = {s.place_id: s.score for s in scores}
    prospects.sort(key=lambda p: -order[p.place_id])
    scores.sort(key=lambda s: -s.score)

    _logger.info(
        "simulación generada",
        extra={
            "event": "simulated",
            "vertical": vertical,
            "metro": metro,
            "count": len(prospects),
            "qualified": sum(1 for s in scores if s.is_qualified),
            "seed": seed,
        },
    )
    return prospects, scores


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera prospectos sintéticos realistas")
    parser.add_argument("--vertical", default="hvac")
    parser.add_argument("--metro", default="Tucson, AZ")
    parser.add_argument("--count", type=int, default=18)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    config.ensure_dirs()
    prospects, scores = simulate(args.vertical, args.metro, args.count, args.seed)

    artifacts.write_prospects(config.DATA_DIR / "prospects.json", prospects)
    artifacts.write_scores(config.DATA_DIR / "scores.json", scores)

    qualified = [s for s in scores if s.is_qualified]
    print(f"{len(prospects)} prospectos simulados, {len(qualified)} calificados\n")
    by_id = {p.place_id: p for p in prospects}
    for score in scores:
        prospect = by_id[score.place_id]
        mark = "✓" if score.is_qualified else " "
        print(
            f"  {mark} {score.score:>3}  {prospect.name:<34} "
            f"{prospect.web_presence.value:<12} {prospect.review_count:>3} reseñas"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
