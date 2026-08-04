"""Registro de costos.

Sin esto, el panel de economía (tarea 25) no tiene de dónde sacar el costo
real -- `FunnelReport.spend_usd` seguía siendo un número tipeado a mano en
`ledger report --spend`. Vive en la página de configuración porque no es algo
que se cargue por corrida sino de forma esporádica (una suscripción, un
dominio, un crédito de API).
"""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse

from gtm.store import repo
from gtm.ui.deps import PoolDep

router = APIRouter(prefix="/costs")


@router.post("")
async def save_cost(
    pool: PoolDep,
    category: str = Form(...),
    amount_usd: float = Form(...),
    vendor: str = Form(""),
    run_id: str = Form(""),
    note: str = Form(""),
) -> RedirectResponse:
    if amount_usd > 0 and category.strip():
        await repo.record_cost(
            pool,
            category=category.strip(),
            amount_usd=amount_usd,
            vendor=vendor.strip() or None,
            run_id=run_id or None,
            note=note,
        )
    return RedirectResponse("/settings", status_code=303)
