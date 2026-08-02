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
import json
import random
import sys

from gtm.factory import config
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

_NAME_PARTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "hvac": (
        (
            "Sonoran", "Desert Sky", "Catalina", "Saguaro", "Old Pueblo", "Tanque Verde",
            "Rincon", "Santa Cruz", "Mission", "Copper State", "Agave", "Ocotillo",
            "Pima", "Sabino", "Gates Pass", "Silverbell", "Ironwood", "Mesquite",
        ),
        ("Air Conditioning", "Cooling & Heating", "HVAC Services", "Air & Heat", "Climate Control"),
    ),
    "plumber": (
        (
            "Sonoran", "Desert", "Catalina", "Saguaro", "Old Pueblo", "Rincon",
            "Santa Cruz", "Copper State", "Agave", "Pima", "Sabino", "Ironwood",
        ),
        ("Plumbing", "Plumbing & Drain", "Rooter & Plumbing", "Pipe Works"),
    ),
    "electrician": (
        ("Sonoran", "Desert", "Catalina", "Old Pueblo", "Copper State", "Pima", "Sabino"),
        ("Electric", "Electrical Services", "Electric & Solar", "Power Solutions"),
    ),
    "roofer": (
        ("Sonoran", "Desert", "Catalina", "Old Pueblo", "Copper State", "Ironwood"),
        ("Roofing", "Roofing & Coatings", "Roof Systems", "Exteriors"),
    ),
}

_REVIEWS: dict[str, tuple[str, ...]] = {
    "hvac": (
        "AC died Saturday at 108 degrees. They had someone here in two hours and "
        "running by dinner. Did not gouge us on the emergency call.",
        "Honest about what needed fixing versus what could wait. Previous company "
        "quoted me a whole new system for what turned out to be a capacitor.",
        "Been servicing our unit for six years. Always on time, always explains what "
        "they did. Wish every trade worked like this.",
        "Called three places. They were the only one who picked up.",
    ),
    "plumber": (
        "Showed up in 40 minutes on a Sunday and fixed the leak. Fair price, no upsell.",
        "Found the actual source of the leak instead of just patching the drywall.",
        "Clean, fast, and they put down mats. Small thing but it says a lot.",
    ),
    "electrician": (
        "Traced a dead circuit that two other electricians gave up on.",
        "Upgraded our panel for the EV charger. Permitted, inspected, done in a day.",
        "Explained the safety issue without trying to scare me into a bigger job.",
    ),
    "roofer": (
        "Hail damage after the August storm. Their photo report is what got the "
        "insurance claim approved.",
        "Full tear-off in two days, cleaned up every nail. Warranty in writing.",
        "Came out for a leak inspection and told me I did not need a new roof yet.",
    ),
}

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
    prefixes, suffixes = _NAME_PARTS.get(vertical.lower(), _NAME_PARTS["hvac"])
    reviews_pool = _REVIEWS.get(vertical.lower(), _REVIEWS["hvac"])

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
            address=f"{rng.randint(100, 9999)} {rng.choice(_STREETS)}, Tucson, AZ",
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

    with open(config.DATA_DIR / "prospects.json", "w", encoding="utf-8") as handle:
        json.dump([p.to_dict() for p in prospects], handle, ensure_ascii=False, indent=2)
    with open(config.DATA_DIR / "scores.json", "w", encoding="utf-8") as handle:
        json.dump([s.to_dict() for s in scores], handle, ensure_ascii=False, indent=2)

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
