"""IA para variar el copy genérico de las demos -- nunca hechos del negocio.

Regla dura del proyecto (`gtm/pipeline.md`: "Prohibido inventar"): un LLM
escribiendo sobre un negocio que no conocés inventa servicios, zonas y años
de experiencia. Por eso este módulo NUNCA le pasa al modelo ningún dato del
prospecto (nombre, teléfono, reseñas, ciudad) -- solo el oficio y el idioma,
que son categorías ya conocidas, no hechos fabricables.

Y solo puede variar los cinco slots del template (`gtm/template/site.html`
vía `generate.py`) que hoy son 100% genéricos, sin ningún dato interpolado:
`cta_body`, `trust_serving_label`, `trust_fast_label`, `services_heading`,
`reviews_heading`. Todo lo demás -- nombre, teléfono, dirección, reseñas,
rating, ciudad -- lo sigue escribiendo `generate.py` directo desde
`Prospect`, nunca pasa por acá. Esto no es una promesa de proceso: como
input al modelo no hay ningún hecho del negocio, es estructuralmente
imposible que el resultado invente uno.

Degrada a los defaults estáticos de `generate.py` si falta
`ANTHROPIC_API_KEY` o si la llamada falla -- igual que PageSpeed/CrUX en
`score.py`, un fallo acá nunca puede tumbar la generación de una demo.

Uso:
    python -m gtm.factory.generate --all --ai-copy
"""

from __future__ import annotations

import json
import os
from typing import Any

from gtm.factory.logs import get_logger
from gtm.factory.types import Language

_logger = get_logger(__name__)

_MODEL = "claude-opus-5"

# Los únicos slots del template sin ningún hecho del negocio interpolado --
# ver el docstring del módulo. No agregar claves acá sin verificar primero
# que generate.py no les interpola ningún dato de Prospect.
SLOTS: tuple[str, ...] = (
    "cta_body",
    "trust_serving_label",
    "trust_fast_label",
    "services_heading",
    "reviews_heading",
)

_SYSTEM_ES = (
    "Escribís copy corto de venta para un sitio de {vertical} en español neutro, "
    "para dueños de negocios de oficios en Estados Unidos que hablan español. "
    "No conocés ningún dato del negocio real -- ni nombre, ni ciudad, ni teléfono, "
    "ni reseñas -- así que NUNCA inventes ninguno: el texto que escribís no puede "
    "mencionar ni implicar ningún hecho específico del negocio, solo hablar en "
    "general del oficio. Directo, sin exagerar, sin emojis."
)
_SYSTEM_EN = (
    "You write short sales copy for a {vertical} website in English, for US "
    "home-service business owners. You know nothing about the real business -- "
    "no name, city, phone, or reviews -- so NEVER invent any of that: the text "
    "you write cannot mention or imply any specific fact about the business, "
    "only speak generally about the trade. Direct, no hype, no emojis."
)

_PROMPT = (
    "Devolvé variantes de estos cinco textos de una landing page: {slots}. "
    "cta_body: 1-2 oraciones invitando a llamar ahora, sin mencionar un dato "
    "puntual del negocio. trust_serving_label y trust_fast_label: 1-3 palabras "
    "cada uno, etiquetas genéricas de confianza (ej. una dice 'Atendemos' antes "
    "de que se le agregue la ciudad, la otra algo como 'Respuesta rápida'). "
    "services_heading y reviews_heading: título corto de sección (2-4 palabras)."
)

_SCHEMA = {
    "type": "object",
    "properties": {slot: {"type": "string"} for slot in SLOTS},
    "required": list(SLOTS),
    "additionalProperties": False,
}


def _client() -> Any:  # import diferido: no todo el pipeline necesita el paquete instalado
    import anthropic

    return anthropic.Anthropic()


def generate_variant_copy(vertical: str, language: Language) -> dict[str, str] | None:
    """Pide variantes de los 5 slots 100% genéricos del template.

    None si falta `ANTHROPIC_API_KEY`, si la llamada falla, o si la
    respuesta no trae las cinco claves como texto no vacío -- en cualquiera
    de esos casos `generate.py` cae a sus defaults estáticos.
    """
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None

    system = (_SYSTEM_ES if language is Language.ES else _SYSTEM_EN).format(vertical=vertical)
    prompt = _PROMPT.format(slots=", ".join(SLOTS))

    try:
        client = _client()
        response = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
        text = next(block.text for block in response.content if block.type == "text")
        data = json.loads(text)
    except Exception as exc:  # noqa: BLE001 - degradamos a los defaults, no rompemos la corrida
        _logger.warning(
            "IA de copy no respondió: se usan los defaults estáticos",
            extra={"event": "copy_ai_failed", "vertical": vertical, "error": str(exc)},
        )
        return None

    if not all(isinstance(data.get(slot), str) and data[slot].strip() for slot in SLOTS):
        _logger.warning(
            "IA de copy devolvió un JSON incompleto: se usan los defaults estáticos",
            extra={"event": "copy_ai_malformed", "vertical": vertical},
        )
        return None

    return {slot: data[slot].strip() for slot in SLOTS}
