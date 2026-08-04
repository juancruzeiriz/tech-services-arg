"""Dashboards de lectura: embudo contra el criterio pre-registrado (tarea 24) y
economía real (tarea 25, en `/dashboard/economics`).

El embudo lee `gtm/funnel.jsonl` vía `FunnelLedger` -- es la fuente de verdad
operativa del pipeline, sobrevive sin Postgres, y es lo que
`decision_criteria.yaml` está pre-registrado contra. Postgres solo aporta acá
el total de costos y horas cargadas, para la proyección de corte temprano.
"""

from __future__ import annotations

from typing import Any

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from gtm.catalog import metros, trades
from gtm.factory import config
from gtm.factory.ledger import FunnelLedger, read_funnel_records
from gtm.factory.stats import wilson_interval
from gtm.factory.types import ContactChannel, Language
from gtm.store import repo
from gtm.ui.app import templates
from gtm.ui.deps import PoolDep, RegistryDep
from gtm.ui.registry import RunRegistry

router = APIRouter(prefix="/dashboard")

_PAIN_BUCKETS = ((0, 29), (30, 49), (50, 69), (70, 100))

_CRITERIA_PATH = config.GTM_DIR / "decision_criteria.yaml"


def _load_criteria() -> dict:
    if not _CRITERIA_PATH.exists():
        return {}
    return yaml.safe_load(_CRITERIA_PATH.read_text(encoding="utf-8")) or {}


def _step(successes: int, base: int) -> dict[str, float | int]:
    low, high = wilson_interval(successes, base)
    return {
        "n": successes,
        "base": base,
        "rate": successes / base if base else 0.0,
        "low": low,
        "high": high,
    }


def _cost_projection(
    *, contacted: int, total_minutes: int, criteria: dict
) -> dict[str, float | int | bool | None]:
    """Proyección del corte temprano por costo (§0.3 del plan): con las
    primeras `llamadas_de_calibracion` contactos ya se puede extrapolar cuántas
    horas más hacen falta para llegar a los 200 del criterio de kill, y
    compararlo contra el presupuesto de horas del horizonte del experimento."""
    corte = criteria.get("corte_temprano_por_costo", {})
    calibracion = int(corte.get("llamadas_de_calibracion", 50))
    horas_min = float(corte.get("horas_disponibles_semana_min", 5))
    horas_max = float(corte.get("horas_disponibles_semana_max", 10))
    horizonte = int(criteria.get("horizonte_semanas", 8))
    kill_contactados = int(criteria.get("umbrales", {}).get("kill_contactados", 200))

    hours_spent = total_minutes / 60
    budget_min = horizonte * horas_min
    budget_max = horizonte * horas_max

    ready = contacted >= calibracion
    contacts_per_hour = (contacted / hours_spent) if ready and hours_spent > 0 else None
    remaining_contacts = max(0, kill_contactados - contacted)

    projected_remaining_hours = (
        remaining_contacts / contacts_per_hour
        if contacts_per_hour and contacts_per_hour > 0
        else None
    )

    over_budget = None
    if projected_remaining_hours is not None:
        remaining_budget_min = budget_min - hours_spent
        remaining_budget_max = budget_max - hours_spent
        over_budget = projected_remaining_hours > max(remaining_budget_min, remaining_budget_max)

    return {
        "ready": ready,
        "calibracion": calibracion,
        "hours_spent": hours_spent,
        "budget_min": budget_min,
        "budget_max": budget_max,
        "contacts_per_hour": contacts_per_hour,
        "remaining_contacts": remaining_contacts,
        "projected_remaining_hours": projected_remaining_hours,
        "over_budget": over_budget,
    }


@router.get("/funnel", response_class=HTMLResponse)
async def funnel_dashboard(
    request: Request,
    pool: PoolDep,
    vertical: str = "",
    metro: str = "",
    channel: str = "",
    language: str = "",
) -> HTMLResponse:
    criteria = _load_criteria()
    total_minutes = await repo.total_minutes_logged(pool)
    total_cost = await repo.total_cost_usd(pool)

    report = FunnelLedger().report(
        spend_usd=total_cost,
        vertical=vertical or None,
        metro=metro or None,
        channel=channel or None,
        language=language or None,
    )

    proposal_sent = report.counts.get("proposal_sent", 0)
    steps = {
        "replied": _step(report.replied, report.contacted),
        "calls_booked": _step(report.calls_booked, report.replied),
        "proposal_sent": _step(proposal_sent, report.calls_booked),
        "paid": _step(report.paid, proposal_sent),
        "overall": _step(report.paid, report.contacted),
    }

    projection = _cost_projection(
        contacted=report.contacted, total_minutes=total_minutes, criteria=criteria
    )
    kill_triggered, kill_reason = report.kill_triggered

    return templates.TemplateResponse(
        request,
        "pages/dashboard_funnel.html",
        {
            "active": "funnel",
            "trades": trades(),
            "metros": metros(),
            # UNREACHABLE nunca llega a la cola de contacto (no es accionable,
            # ver contact.py) así que nunca aparece como canal grabado -- no
            # tiene sentido ofrecerlo como filtro.
            "channels": [c for c in ContactChannel if c is not ContactChannel.UNREACHABLE],
            "languages": list(Language),
            "filters": {
                "vertical": vertical,
                "metro": metro,
                "channel": channel,
                "language": language,
            },
            "report": report,
            "steps": steps,
            "kill_triggered": kill_triggered,
            "kill_reason": kill_reason,
            "kill_target": criteria.get("umbrales", {}).get("kill_contactados", 200),
            "projection": projection,
            "total_cost": total_cost,
        },
    )


def _cohorts(ledger: FunnelLedger, records: list[dict]) -> list[dict[str, Any]]:
    """Contactado/pagado/ingreso por (oficio, metro, idioma) -- dónde volver y
    dónde no (§1.8.5 del plan). Solo combinaciones que de verdad aparecen en el
    ledger: iterar el producto cartesiano completo del catálogo mostraría
    docenas de filas vacías."""
    combos = sorted(
        {
            (r.get("vertical") or "", r.get("metro") or "", r.get("language") or "")
            for r in records
        }
    )
    rows: list[dict[str, Any]] = []
    for vertical, metro, language in combos:
        if not (vertical or metro or language):
            continue
        rep = ledger.report(vertical=vertical or None, metro=metro or None, language=language or None)
        if rep.contacted == 0:
            continue
        rows.append(
            {
                "vertical": vertical,
                "metro": metro,
                "language": language,
                "contacted": rep.contacted,
                "paid": rep.paid,
                "revenue": rep.revenue_usd,
            }
        )
    rows.sort(key=lambda r: (-r["paid"], -r["contacted"]))
    return rows


def _pain_correlation(records: list[dict]) -> list[dict[str, Any]]:
    """¿El pain score predice conversión? (§1.8.6). Por prospecto: el
    pain_score con el que se lo contactó, y si esa misma clave llegó a
    "paid" -- ambos números viajan en cada evento (ver `queue.py`), así que
    alcanza con una pasada agrupando por `key`."""
    by_key: dict[str, dict[str, Any]] = {}
    for record in records:
        key = record.get("key", "")
        if not key:
            continue
        entry = by_key.setdefault(key, {"pain_score": 0, "contacted": False, "paid": False})
        if record.get("event") == "contacted":
            entry["pain_score"] = record.get("pain_score", 0) or entry["pain_score"]
            entry["contacted"] = True
        if record.get("event") == "paid":
            entry["paid"] = True

    contacted_only = [e for e in by_key.values() if e["contacted"]]
    rows: list[dict[str, Any]] = []
    for lo, hi in _PAIN_BUCKETS:
        in_bucket = [e for e in contacted_only if lo <= e["pain_score"] <= hi]
        paid = sum(1 for e in in_bucket if e["paid"])
        n = len(in_bucket)
        low, high = wilson_interval(paid, n)
        rows.append({"range": f"{lo}-{hi}", "n": n, "paid": paid, "rate": paid / n if n else 0.0, "low": low, "high": high})
    return rows


def _data_health(registry: RunRegistry) -> list[dict[str, Any]]:
    """Prospectos por corrida, cuántos calificaron, cuántos quedaron sin canal
    (§1.8.7) -- de las corridas que sigue conociendo este proceso, igual que
    hace `/runs`. Sin Postgres de por medio: si el proceso se reinicia, esta
    tabla se vacía, lo mismo que ya le pasa a `/runs`."""
    rows: list[dict[str, Any]] = []
    for handle in registry.all():
        if handle.result is None:
            continue
        result = handle.result
        no_channel = sum(1 for c in result.contacts if not c.is_actionable)
        rows.append(
            {
                "run_id": handle.ctx.run_id,
                "vertical": handle.ctx.vertical,
                "metro": handle.ctx.metro,
                "prospects": len(result.prospects),
                "qualified": sum(1 for s in result.scores if s.is_qualified),
                "no_channel": no_channel,
            }
        )
    return rows


@router.get("/economics", response_class=HTMLResponse)
async def economics_dashboard(request: Request, pool: PoolDep, registry: RegistryDep) -> HTMLResponse:
    total_cost = await repo.total_cost_usd(pool)
    total_minutes = await repo.total_minutes_logged(pool)
    hours = total_minutes / 60

    ledger = FunnelLedger()
    records = read_funnel_records()
    report = ledger.report(spend_usd=total_cost)

    net = report.revenue_usd - total_cost
    effective_usd_hour = net / hours if hours > 0 else None
    cac = total_cost / report.paid if report.paid > 0 else None

    return templates.TemplateResponse(
        request,
        "pages/dashboard_economics.html",
        {
            "active": "economics",
            "report": report,
            "total_cost": total_cost,
            "hours": hours,
            "net": net,
            "effective_usd_hour": effective_usd_hour,
            "cac": cac,
            "cohorts": _cohorts(ledger, records),
            "pain_correlation": _pain_correlation(records),
            "data_health": _data_health(registry),
        },
    )
