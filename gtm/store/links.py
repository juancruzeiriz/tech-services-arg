"""Tokens de redirección para medir aperturas de demo, sin tocar la demo en sí.

El link que efectivamente se manda al prospecto NO es la URL directa de la
demo — es `{base_url}/v/{token}`. Una Cloudflare Pages Function
(`cloudflare/functions/v/[token].js`) registra la apertura y redirige (302) a
la demo real. La demo HTML sigue haciendo cero requests externos —
`tests/gtm/test_generate.py::test_no_hace_requests_externas` no se toca — porque
el tracking pasa por la URL que se envía, no por nada embebido en la página.

Regla dura, la misma que ya está en `decision_criteria.yaml`: una apertura es
nivel 1 de la escalera de compromiso y **nunca** entra a `funnel_events`. Mide
curiosidad, no disposición a pagar — por eso vive en su propia tabla,
`demo_views`, sin relación con el criterio de kill/ganador.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from gtm.factory.pipeline import RunContext, RunResult
from gtm.factory.types import ContactPlan, Demo


def mint_token() -> str:
    """Token corto, no adivinable, apto para SMS/email. `secrets` (no
    `random`): tiene que ser imposible de enumerar -- es lo único que separa
    "quién abrió esta demo" de "cualquiera puede escanear /v/0, /v/1, ..."."""
    return secrets.token_urlsafe(8)


def tracked_url(base_url: str, token: str) -> str:
    """La URL que efectivamente se manda, en vez de la de la demo directa."""
    return f"{base_url.rstrip('/')}/v/{token}"


def demo_link_row(
    token: str,
    demo_slug: str,
    place_id: str,
    channel: str,
    *,
    run_id: str | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "token": token,
        "demo_slug": demo_slug,
        "place_id": place_id,
        "channel": channel,
        "run_id": run_id,
        "created_at": (created_at or datetime.now(UTC)).isoformat(),
    }


def mint_links_for_run(ctx: RunContext, result: RunResult) -> dict[str, str]:
    """Un token por cada `ContactPlan` accionable de la corrida -- uno por
    (demo, canal), no uno por demo: así se sabe si la apertura vino del mensaje
    de teléfono o del de formulario, no solo que alguien la abrió.

    Devuelve `{place_id: token}`. Quien llama (la UI, al mostrar la cola de
    contacto) arma la URL con `tracked_url()` y la pasa como `link_url` a
    `outreach.build_email` / `contact.build_form_message` / `build_call_script`
    en vez de dejar que usen `demo.url` directo. Las filas para persistir salen
    de `demo_link_rows()`, sobre este mismo diccionario.
    """
    demo_by_place_id: dict[str, Demo] = {d.place_id: d for d in result.demos}
    tokens: dict[str, str] = {}
    for plan in result.contacts:
        if not plan.is_actionable or plan.place_id not in demo_by_place_id:
            continue
        tokens[plan.place_id] = mint_token()
    return tokens


def demo_link_rows(
    ctx: RunContext, result: RunResult, tokens: dict[str, str]
) -> list[dict[str, Any]]:
    """Las filas de `demo_links` correspondientes a `tokens` (ver
    `mint_links_for_run`), listas para `repo.upsert(pool, "demo_links", rows)`."""
    demo_by_place_id: dict[str, Demo] = {d.place_id: d for d in result.demos}
    plan_by_place_id: dict[str, ContactPlan] = {p.place_id: p for p in result.contacts}

    rows: list[dict[str, Any]] = []
    for place_id, token in tokens.items():
        demo = demo_by_place_id.get(place_id)
        plan = plan_by_place_id.get(place_id)
        if demo is None or plan is None:
            continue
        rows.append(
            demo_link_row(token, demo.slug, place_id, plan.channel.value, run_id=ctx.run_id)
        )
    return rows
