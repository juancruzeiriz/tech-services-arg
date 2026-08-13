"""Carga y valida `trades.yaml` y `metros.yaml`. Cacheado: son ~35 entradas chicas
leídas muchas veces por corrida, no hace falta releer el archivo cada vez."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from gtm.catalog.types import Metro, ServiceCopy, Trade

_CATALOG_DIR = Path(__file__).resolve().parent


class CatalogError(Exception):
    """El catálogo no parsea o le falta un campo obligatorio."""


def _load_yaml(name: str) -> list[dict[str, Any]]:
    path = _CATALOG_DIR / name
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, list):
        raise CatalogError(f"{name}: se esperaba una lista en el nivel superior")
    return data


def _services(raw: list[dict[str, str]]) -> tuple[ServiceCopy, ...]:
    return tuple(ServiceCopy(title=item["title"], body=item["body"]) for item in raw)


def _build_trade(item: dict[str, Any]) -> Trade:
    try:
        return Trade(
            key=item["key"],
            places_query=item["places_query"],
            label_en=item["label_en"],
            label_es=item["label_es"],
            plural_en=item["plural_en"],
            plural_es=item["plural_es"],
            article_en=item["article_en"],
            avg_ticket_usd=item["avg_ticket_usd"],
            urgency=item["urgency"],
            rank=item["rank"],
            theme_primary=item["theme_primary"],
            theme_primary_dark=item["theme_primary_dark"],
            theme_bg_tint=item["theme_bg_tint"],
            icon=item["icon"],
            services_en=_services(item["services_en"]),
            services_es=_services(item["services_es"]),
            name_prefixes=tuple(item["name_prefixes"]),
            name_suffixes=tuple(item["name_suffixes"]),
            sample_reviews_en=tuple(item["sample_reviews_en"]),
        )
    except KeyError as exc:
        raise CatalogError(f"trades.yaml: falta {exc} en {item.get('key', '?')!r}") from exc


def _build_metro(item: dict[str, Any]) -> Metro:
    try:
        return Metro(
            key=item["key"],
            city=item["city"],
            state=item["state"],
            display=item["display"],
            timezone=item["timezone"],
            population=item["population"],
            hispanic_pct=item["hispanic_pct"],
            language_default=item["language_default"],
            mini_tcpa_risk=item["mini_tcpa_risk"],
            rank=item["rank"],
        )
    except KeyError as exc:
        raise CatalogError(f"metros.yaml: falta {exc} en {item.get('key', '?')!r}") from exc


@lru_cache(maxsize=1)
def _all_trades() -> tuple[Trade, ...]:
    return tuple(_build_trade(item) for item in _load_yaml("trades.yaml"))


@lru_cache(maxsize=1)
def _all_metros() -> tuple[Metro, ...]:
    return tuple(_build_metro(item) for item in _load_yaml("metros.yaml"))


@lru_cache(maxsize=1)
def _trades_by_key() -> dict[str, Trade]:
    return {t.key: t for t in _all_trades()}


@lru_cache(maxsize=1)
def _metros_by_key() -> dict[str, Metro]:
    return {m.key: m for m in _all_metros()}


def trades() -> tuple[Trade, ...]:
    """Todos los oficios, ordenados por `rank` ascendente (mejor primero)."""
    return tuple(sorted(_all_trades(), key=lambda t: t.rank))


def metros() -> tuple[Metro, ...]:
    """Todos los metros, ordenados por `rank` ascendente (mejor primero)."""
    return tuple(sorted(_all_metros(), key=lambda m: m.rank))


def get_trade(key: str) -> Trade | None:
    """`None` si no está en el catálogo — nunca levanta. El texto libre es un
    camino válido, no un error: `RunContext.vertical` sigue siendo `str`."""
    if not key:
        return None
    return _trades_by_key().get(key.strip().lower())


def get_metro(key: str) -> Metro | None:
    if not key:
        return None
    return _metros_by_key().get(key.strip().lower())


def get_metro_by_display(display: str) -> Metro | None:
    """Busca por el string "City, ST" tal como lo usa el resto del pipeline."""
    display_norm = display.strip()
    if not display_norm:
        return None
    for metro in _all_metros():
        if metro.display == display_norm:
            return metro
    return None


def city_of(metro: str) -> str:
    """Ciudad legible a partir de un metro. Colapsa los dos helpers duplicados que
    existían en `generate._city` y en `contact.py` (línea inline, sin fallback)."""
    found = get_metro_by_display(metro) or get_metro(metro)
    if found is not None:
        return found.city
    return metro.split(",")[0].strip() or metro
