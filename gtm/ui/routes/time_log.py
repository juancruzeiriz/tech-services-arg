"""Registro de horas trabajadas.

Sin esto, `horas_mes_por_cliente` (el desempate por mantenibilidad de
`decision_criteria.yaml`) y el USD/hora efectivo (el panel de economía, tarea
25) no tienen de dónde salir — el tiempo propio nunca se cargaba en ningún
lado. El cronómetro vive en el cliente (Alpine, en `queue.html`); acá solo se
guarda el resultado cuando el usuario aprieta "Guardar".
"""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse

from gtm.store import repo
from gtm.ui.deps import PoolDep

router = APIRouter(prefix="/time-log")


@router.post("")
async def save_time_log(
    pool: PoolDep,
    minutes: int = Form(...),
    activity: str = Form("contacto"),
    run_id: str = Form(""),
    note: str = Form(""),
    redirect_to: str = Form("/queue"),
) -> RedirectResponse:
    if minutes > 0:
        await repo.record_time(
            pool,
            minutes=minutes,
            activity=activity,
            run_id=run_id or None,
            note=note,
        )
    return RedirectResponse(redirect_to, status_code=303)
