"""La mitad prospectiva que faltaba en /dashboard/economics.

Ese dashboard mira para atrás: qué pasó. Esta pantalla mira para adelante:
¿el precio del paquete alcanza, y cuánto cobrar por trabajo que no es el
paquete? Ninguna de las dos preguntas tenía antes un lugar en la UI --
"cuánto debo cobrar" vivía en la cabeza de Juan, no en un cálculo con los
datos que `costs.py`/`time_log.py` ya vienen registrando.

El precio del paquete fijo (`PACKAGE_PRICE_USD`) es una constante de
lectura, no un default editable: `decision_criteria.yaml` lo fija para todo
el experimento (ver `gtm/pipeline.md`), y la aritmética del criterio de kill
depende de que no se mueva a mitad de camino. Esta pantalla existe para
SABER si 950 alcanza, nunca para sugerir cambiarlo.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from gtm.factory.ledger import FunnelLedger
from gtm.store import repo
from gtm.ui.app import templates
from gtm.ui.deps import PoolDep

router = APIRouter(prefix="/pricing")

PACKAGE_PRICE_USD = 950


@router.get("", response_class=HTMLResponse)
async def pricing(
    request: Request,
    pool: PoolDep,
    estimated_hours: float = 0.0,
    quote_hours: float = 0.0,
) -> HTMLResponse:
    total_cost = await repo.total_cost_usd(pool)
    total_minutes = await repo.total_minutes_logged(pool)
    hours_logged = total_minutes / 60

    # Piso de costo: cuánto infra/API ya cuesta cada hora trabajada. No mide
    # el valor del tiempo de Juan -- mide el punto por debajo del cual ni
    # siquiera se recupera el gasto de costs.py, sea cual sea el precio.
    floor_usd_hour = total_cost / hours_logged if hours_logged > 0 else None

    report = FunnelLedger().report(spend_usd=total_cost)

    # Horas por venta: reales si ya hubo una venta pagada (gtm/funnel.jsonl
    # sigue vacío al momento de escribir esto), o la estimación manual que el
    # formulario permite cargar -- sin esto la pantalla no dice nada hasta
    # que exista la primera venta real.
    hours_per_sale: float | None
    hours_per_sale_is_estimate = False
    if report.paid > 0:
        hours_per_sale = hours_logged / report.paid
    elif estimated_hours > 0:
        hours_per_sale = estimated_hours
        hours_per_sale_is_estimate = True
    else:
        hours_per_sale = None

    package_rate = PACKAGE_PRICE_USD / hours_per_sale if hours_per_sale else None
    clears_floor = (
        package_rate >= floor_usd_hour
        if package_rate is not None and floor_usd_hour is not None
        else None
    )

    # Cotizador genérico para trabajo que NO es el paquete de USD 950 (demos
    # de reservas, calculadoras a medida, cualquier otro servicio del
    # catálogo) -- usa el piso como tarifa de referencia porque es el único
    # número que sale de datos reales, no de una corazonada.
    quote_total = (
        quote_hours * floor_usd_hour if quote_hours > 0 and floor_usd_hour is not None else None
    )

    return templates.TemplateResponse(
        request,
        "pages/pricing.html",
        {
            "active": "pricing",
            "total_cost": total_cost,
            "hours_logged": hours_logged,
            "floor_usd_hour": floor_usd_hour,
            "cost_per_contact": report.cost_per_contact,
            "contacted": report.contacted,
            "package_price": PACKAGE_PRICE_USD,
            "paid": report.paid,
            "hours_per_sale": hours_per_sale,
            "hours_per_sale_is_estimate": hours_per_sale_is_estimate,
            "package_rate": package_rate,
            "clears_floor": clears_floor,
            "estimated_hours": estimated_hours,
            "quote_hours": quote_hours,
            "quote_total": quote_total,
        },
    )
