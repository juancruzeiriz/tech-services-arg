"""Estadística mínima para no sobre-leer una muestra chica como si fuera la
verdad -- el error que ya motivó el re-registro de `decision_criteria.yaml`
(ver el comentario ahí: n=60 con la tasa buena tenía 42% de falso kill)."""

from __future__ import annotations

import math


def wilson_interval(successes: int, n: int, *, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de confianza de Wilson para una proporción binomial.

    Preferido sobre el intervalo normal porque no rompe los límites [0, 1] ni
    colapsa a un punto con `n` chico -- exactamente el régimen en el que este
    embudo va a vivir la mayor parte del experimento. `z=1.96` -> 95%.
    """
    if n <= 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1 + z**2 / n
    center = p + z**2 / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return max(0.0, (center - margin) / denom), min(1.0, (center + margin) / denom)
