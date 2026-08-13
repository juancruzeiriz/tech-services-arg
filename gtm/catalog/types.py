"""Modelos del catálogo. Sin dependencias de `gtm.factory`: ver el docstring del
paquete para por qué eso es una regla dura, no un estilo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServiceCopy:
    """Una tarjeta de servicio en la demo: título corto + una línea de contexto."""

    title: str
    body: str


@dataclass(frozen=True, slots=True)
class Trade:
    """Un oficio del catálogo: todo lo que varía por rubro en un solo lugar.

    `rank` ordena el desplegable de la UI. Se calcula como
    `avg_ticket_usd × peso_de_urgencia` (alto=3, medio=2, bajo=1): la aproximación
    más barata posible a "mayor ganancia esperada, sin haber vendido nada todavía"
    — el ticket define cuánto vale la venta, la urgencia define qué tan bien
    convierte el ángulo de "se te va la llamada, se te va la plata".
    """

    key: str
    places_query: str
    label_en: str
    label_es: str
    plural_en: str
    plural_es: str
    article_en: str
    avg_ticket_usd: int
    urgency: str
    rank: int
    # Identidad visual de la demo (gtm/factory/generate.py la vuelca en CSS custom
    # properties). Sin fotos reales del negocio -- los Términos de Places prohíben
    # cachearlas -- esto es lo que hace que dos oficios distintos no se lean como
    # el mismo template. `icon` es una clave de gtm/factory/icons.py, no markup.
    theme_primary: str
    theme_primary_dark: str
    theme_bg_tint: str
    icon: str
    services_en: tuple[ServiceCopy, ...]
    services_es: tuple[ServiceCopy, ...]
    name_prefixes: tuple[str, ...]
    name_suffixes: tuple[str, ...]
    sample_reviews_en: tuple[str, ...]

    def label(self, language: str) -> str:
        return self.label_es if language == "es" else self.label_en

    def plural(self, language: str) -> str:
        return self.plural_es if language == "es" else self.plural_en

    def services(self, language: str) -> tuple[ServiceCopy, ...]:
        return self.services_es if language == "es" else self.services_en


@dataclass(frozen=True, slots=True)
class Metro:
    """Un área metropolitana del catálogo.

    `rank` ordena el desplegable de metros: tamaño de pool esperado (población)
    × % hispano (proxy de la ventaja competitiva de vender en español) ÷ riesgo
    legal (mini-TCPA). Ver `gtm/catalog/metros.yaml` para el cálculo exacto de
    cada entrada.
    """

    key: str
    city: str
    state: str
    display: str
    timezone: str
    population: int
    hispanic_pct: float
    language_default: str
    mini_tcpa_risk: bool
    rank: int
