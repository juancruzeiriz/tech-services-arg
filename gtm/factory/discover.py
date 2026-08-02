"""Etapa 1: descubrir negocios candidatos vía Google Places API (New).

Filtro de calificación: negocios con demanda probada (reseñas suficientes) y que
se ocupan de su reputación (rating alto), pero con presencia web pobre. Ese cruce
—les importa el negocio y les va bien, pero su web es mala— es el prospecto ideal:
tiene plata, tiene dolor y no está peleando por sobrevivir.

Uso:
    python -m gtm.factory.discover --vertical plumber --metro "Tucson, AZ" --limit 20
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from gtm.factory import config
from gtm.factory.logs import get_logger
from gtm.factory.net import request_json
from gtm.factory.types import DiscoveryError, Prospect, WebPresence

_logger = get_logger(__name__)

_PLACES_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"

# Pedimos solo los campos que usamos: el pricing de Places es por field mask, así
# que traer campos de más se paga literalmente.
_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.nationalPhoneNumber",
        "places.websiteUri",
        "places.rating",
        "places.userRatingCount",
        "places.reviews",
        "nextPageToken",
    )
)

MIN_REVIEWS = 50
"""Prueba de demanda real. Debajo de esto no sabemos si el negocio factura."""

MIN_RATING = 4.0
"""Les importa su reputación, así que les va a importar su presencia web."""

_MAX_PAGE_SIZE = 20  # límite duro de la API por página


def _extract_reviews(place: dict[str, Any], limit: int = 3) -> tuple[str, ...]:
    """Extrae textos de reseñas para personalizar la demo.

    Usar las reseñas reales del negocio en su propia demo es lo que separa un
    artefacto creíble de una plantilla obvia.
    """
    reviews: list[str] = []
    for review in place.get("reviews", [])[:limit]:
        text = (review.get("text") or {}).get("text", "").strip()
        if text:
            reviews.append(text)
    return tuple(reviews)


def _to_prospect(place: dict[str, Any], vertical: str, metro: str) -> Prospect | None:
    """Mapea un place de la API a Prospect. Devuelve None si le falta lo esencial."""
    place_id = place.get("id")
    name = (place.get("displayName") or {}).get("text", "").strip()
    if not place_id or not name:
        return None

    return Prospect(
        place_id=place_id,
        name=name,
        vertical=vertical,
        metro=metro,
        phone=place.get("nationalPhoneNumber"),
        website=place.get("websiteUri"),
        rating=place.get("rating"),
        review_count=place.get("userRatingCount", 0),
        address=place.get("formattedAddress"),
        top_reviews=_extract_reviews(place),
    )


def _search_page(
    query: str, api_key: str, page_size: int, page_token: str | None
) -> dict[str, Any]:
    body: dict[str, Any] = {"textQuery": query, "pageSize": page_size}
    if page_token:
        body["pageToken"] = page_token

    try:
        return request_json(
            "POST",
            _PLACES_ENDPOINT,
            json_body=body,
            headers={
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": _FIELD_MASK,
                "Content-Type": "application/json",
            },
        )
    except Exception as exc:  # noqa: BLE001 - se re-lanza tipada abajo
        raise DiscoveryError(f"Places API falló para {query!r}: {exc}") from exc


def discover(
    vertical: str,
    metro: str,
    limit: int = 20,
    *,
    min_reviews: int = MIN_REVIEWS,
    min_rating: float = MIN_RATING,
    api_key: str | None = None,
) -> list[Prospect]:
    """Busca negocios del vertical en el metro y devuelve los que califican.

    Args:
        vertical: rubro en inglés, tal como lo buscaría un cliente ("plumber").
        metro: ciudad y estado ("Tucson, AZ").
        limit: máximo de prospectos calificados a devolver.
        min_reviews: piso de reseñas (prueba de demanda).
        min_rating: piso de rating.
        api_key: sobreescribe GOOGLE_PLACES_API_KEY (para tests).

    Returns:
        Prospectos calificados, ordenados poniendo primero a los que no tienen sitio.
    """
    key = api_key or config.require_env("GOOGLE_PLACES_API_KEY")
    query = f"{vertical} in {metro}"

    qualified: list[Prospect] = []
    seen: set[str] = set()
    page_token: str | None = None
    pages = 0

    # Cortamos a 5 páginas: más allá, Places devuelve negocios cada vez menos
    # relevantes al query y el costo por prospecto útil se dispara.
    while len(qualified) < limit and pages < 5:
        payload = _search_page(query, key, min(_MAX_PAGE_SIZE, limit), page_token)
        places = payload.get("places", [])
        pages += 1

        for place in places:
            prospect = _to_prospect(place, vertical, metro)
            if prospect is None or prospect.place_id in seen:
                continue
            seen.add(prospect.place_id)

            if prospect.review_count < min_reviews:
                continue
            if prospect.rating is not None and prospect.rating < min_rating:
                continue
            # Sin teléfono no hay ángulo de "llamada perdida", que es toda la oferta.
            if not prospect.phone:
                continue

            qualified.append(prospect)
            if len(qualified) >= limit:
                break

        page_token = payload.get("nextPageToken")
        if not page_token or not places:
            break

    # Los que no tienen sitio propio van primero: no hay incumbente que defender.
    priority = {WebPresence.NONE: 0, WebPresence.SOCIAL_ONLY: 1, WebPresence.HAS_SITE: 2}
    qualified.sort(key=lambda p: (priority[p.web_presence], -p.review_count))

    _logger.info(
        "discovery completado",
        extra={
            "event": "discover_done",
            "vertical": vertical,
            "metro": metro,
            "pages_fetched": pages,
            "qualified": len(qualified),
            "no_website": sum(1 for p in qualified if p.web_presence is WebPresence.NONE),
        },
    )
    return qualified


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Descubre prospectos vía Google Places")
    parser.add_argument("--vertical", required=True, help='Rubro en inglés, ej: "plumber"')
    parser.add_argument("--metro", required=True, help='Ciudad y estado, ej: "Tucson, AZ"')
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--min-reviews", type=int, default=MIN_REVIEWS)
    parser.add_argument("--min-rating", type=float, default=MIN_RATING)
    parser.add_argument(
        "--output",
        default=None,
        help="Ruta del JSON de salida (default: gtm/build/data/prospects.json)",
    )
    args = parser.parse_args(argv)

    config.ensure_dirs()
    output = args.output or str(config.DATA_DIR / "prospects.json")

    prospects = discover(
        args.vertical,
        args.metro,
        args.limit,
        min_reviews=args.min_reviews,
        min_rating=args.min_rating,
    )

    with open(output, "w", encoding="utf-8") as handle:
        json.dump([p.to_dict() for p in prospects], handle, ensure_ascii=False, indent=2)

    print(f"{len(prospects)} prospectos calificados -> {output}")
    for prospect in prospects:
        print(
            f"  [{prospect.web_presence.value:>12}] {prospect.name} "
            f"({prospect.review_count} reseñas, {prospect.rating})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
