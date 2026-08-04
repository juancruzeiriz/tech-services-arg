"""Catálogo de oficios y metros: la fuente de verdad para los desplegables de la UI.

Reemplaza cuatro diccionarios parciales que vivían dispersos y desincronizados
(`types.VERTICAL_LABELS`, `generate._SERVICES`, `simulate._NAME_PARTS`,
`simulate._REVIEWS`) por una sola fuente en YAML, ordenada por
ticket_promedio × urgencia — que es la señal barata de "mayor ganancia, menor
costo de elaboración" que se puede calcular sin haber vendido nada todavía.

No importa nada de `gtm.factory`: es al revés, `gtm.factory.types` importa de acá.
Un ciclo de imports rompería el módulo entero en tiempo de import, no en un test.
"""

from __future__ import annotations

from gtm.catalog.loader import (
    CatalogError,
    city_of,
    get_metro,
    get_metro_by_display,
    get_trade,
    metros,
    trades,
)
from gtm.catalog.types import Metro, ServiceCopy, Trade

__all__ = [
    "CatalogError",
    "Metro",
    "ServiceCopy",
    "Trade",
    "city_of",
    "get_metro",
    "get_metro_by_display",
    "get_trade",
    "metros",
    "trades",
]
