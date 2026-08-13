"""Ícono lineal por oficio, para el logo y el arte del hero de cada demo.

No hay fotos reales del negocio: los Términos de Places prohíben cachear sus fotos
(ver `gtm/factory/discover.py`). Este módulo es el sustituto -- un ícono vectorial
simple, un solo color (`currentColor`), consistente en estilo (trazo, viewBox 48x48)
entre los 15 oficios del catálogo. `gtm/catalog/trades.yaml` solo guarda la *clave*
(`icon: tree`); el markup vive acá, no en el YAML, porque el catálogo no conoce HTML.

Todos comparten atributos de trazo -- `stroke-width`, `stroke-linecap`,
`stroke-linejoin`, `fill="none"` -- para que ningún ícono se vea "de otro set"
al lado de los demás.
"""

from __future__ import annotations

_VIEWBOX = "0 0 48 48"

# path `d` únicamente -- el wrapper <svg>/<path> común lo arma icon_markup().
_PATHS: dict[str, str] = {
    "roof": "M6 26 24 8l18 18M10 24v16h28V24",
    "fan": (
        "M24 6v36M8 15l32 18M40 15 8 33"
        "M24 6l-4 7M24 6l4 7M24 42l-4-7M24 42l4-7"
        "M8 15l4 7M8 15l7-3M40 33l-4-7M40 33l-7 3"
        "M40 15l-4 7M40 15l-7-3M8 33l4-7M8 33l7 3"
    ),
    "drop": "M24 6C24 6 12 22 12 30a12 12 0 0 0 24 0C36 22 24 6 24 6z",
    "tree": "M24 5 11 25h6L9 38h10v5h10v-5h10l-8-13h6L24 5z",
    "roller": "M8 9h22v11H8zM14 20v7M14 27h5a5 5 0 0 1 5 5v6",
    "fence": "M10 12v28M20 8v32M30 8v32M40 12v28M5 21h38M5 32h38",
    "garage": "M5 19 24 6l19 13v21H5zM5 25h38M5 31h38M5 37h38",
    "bolt": "M27 4 12 26h10l-3 18 19-24H27z",
    "leaf": "M10 37C6 20 20 7 39 7c0 18-13 32-29 30zM13 34 30 17",
    "gutter": "M6 13v11a5 5 0 0 0 5 5h26a5 5 0 0 0 5-5V13M24 33v9M17 37l7 7 7-7",
    "shield": "M24 4 8 10v13c0 12 8 19 16 21 8-2 16-9 16-21V10L24 4zM17 24l5 5 9-10",
    "wave": "M4 18c4-4 8-4 12 0s8 4 12 0 8-4 12 0 8-4 12 0M4 29c4-4 8-4 12 0s8 4 12 0 8-4 12 0 8-4 12 0",
    "gear": (
        "M24 16a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM24 4v6M24 38v6M4 24h6M38 24h6"
        "M9.5 9.5l4.2 4.2M34.3 34.3l4.2 4.2M38.5 9.5l-4.2 4.2M13.7 34.3l-4.2 4.2"
    ),
    "key": "M18 21a9 9 0 1 1 6.4 8.6L40 45l-4.5 4.5-4.5-4.5-4 4-5.4-5.4 9.9-9.9A9 9 0 0 1 18 21z",
    "truck": (
        "M4 30V16h21v14H4zM25 22h7l7 7v1H25v-8z"
        "M11 35a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM33 35a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"
    ),
    # Fallback: cualquier vertical fuera del catálogo (texto libre desde la UI) --
    # una marca de verificación, coherente con "servicio confiable" sin atarse a
    # ningún oficio en particular. Mismo patrón que _DEFAULT_SERVICES_EN en generate.py.
    "check": "M24 4a20 20 0 1 0 0 40 20 20 0 0 0 0-40zM15 24l6.5 6.5L34 18",
}

DEFAULT_ICON = "check"


def icon_path(key: str) -> str:
    """El `d` del ícono, o el de fallback si la clave no existe."""
    return _PATHS.get(key, _PATHS[DEFAULT_ICON])


def icon_markup(key: str, *, size: int = 48, stroke_width: float = 2.4) -> str:
    """`<svg>` autocontenido, trazo en `currentColor` -- hereda el color de quien
    lo envuelva (el logo lo tiñe de blanco sobre un círculo de marca, el hero art
    lo tiñe con `theme_primary`). Sin `fill`, sin degradados: se ve igual de bien
    a cualquier tamaño."""
    d = icon_path(key)
    return (
        f'<svg viewBox="{_VIEWBOX}" width="{size}" height="{size}" '
        'fill="none" stroke="currentColor" stroke-linecap="round" '
        f'stroke-linejoin="round" stroke-width="{stroke_width}" aria-hidden="true">'
        f'<path d="{d}"/></svg>'
    )
