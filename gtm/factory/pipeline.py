"""Orquesta el pipeline completo en un solo proceso Python.

Los 8 módulos de `gtm/factory/` (`discover`, `score`, `generate`, `deploy`,
`contact`, `outreach`, `ledger`, `simulate`) siguen siendo la interfaz de línea de
comandos: cada `main(argv)` sigue funcionando exactamente igual, con los mismos
flags, y sus tests no se tocan acá. Este módulo es el **segundo** consumidor de
las mismas funciones puras (`discover()`, `score_all()`, `generate()`, `deploy()`,
`resolve_all()`, `build_email()`, `simulate()`) — corre las etapas en un solo
proceso, con progreso reportado por callback, para que una UI (o un script) pueda
correr el pipeline completo sin invocar seis subprocesos ni releer/reescribir JSON
entre cada uno.

Cada corrida vive en su propio directorio, `gtm/build/runs/<run_id>/` por defecto:
dos corridas concurrentes —o una de prueba y una real— no se pisan los archivos.

Uso programático:
    ctx = RunContext.create("hvac", "Tucson, AZ", simulated=True)
    result = asyncio.run(run_pipeline(ctx))

Uso por CLI (equivalente a encadenar los 8 comandos a mano):
    python -m gtm.factory.pipeline --vertical hvac --metro "Tucson, AZ" --simulate
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from gtm.factory import artifacts, config
from gtm.factory.contact import resolve_all
from gtm.factory.deploy import deploy as deploy_demos
from gtm.factory.discover import MIN_RATING, MIN_REVIEWS, discover
from gtm.factory.generate import generate
from gtm.factory.ledger import SuppressionList
from gtm.factory.logs import get_logger
from gtm.factory.outreach import build_email
from gtm.factory.score import score_all
from gtm.factory.simulate import simulate
from gtm.factory.types import (
    ComplianceError,
    ContactPlan,
    Demo,
    GenerationError,
    Language,
    OutreachEmail,
    PainScore,
    Prospect,
    SenderIdentity,
)

_logger = get_logger(__name__)


class Stage(StrEnum):
    """Etapas que orquesta `run_pipeline`, en el orden en que corren."""

    DISCOVER = "discover"
    SCORE = "score"
    GENERATE = "generate"
    DEPLOY = "deploy"
    CONTACT = "contact"
    OUTREACH = "outreach"


@dataclass(frozen=True, slots=True)
class RunContext:
    """Todos los parámetros de una corrida, más dónde deja sus artefactos.

    Las rutas van en la instancia, no en `config` (constantes de módulo): eso es
    lo que permite que dos corridas no se pisen y que una corrida vieja se pueda
    releer para el backfill sin adivinar qué `prospects.json` le pertenecía. Usar
    `RunContext.create(...)`, no el constructor directo, salvo en tests que
    necesitan control total sobre las rutas.
    """

    run_id: str
    vertical: str
    metro: str
    data_dir: Path
    demos_dir: Path
    public_dir: Path
    language: Language = Language.EN
    limit: int = 20
    min_reviews: int = MIN_REVIEWS
    min_rating: float = MIN_RATING
    score_concurrency: int = 5
    contact_concurrency: int = 8
    probe_site: bool = True
    dry_run: bool = True
    simulated: bool = True
    seed: int = 42
    author_name: str = ""
    author_url: str = ""
    base_url: str = ""
    sender: SenderIdentity | None = None
    offer_price_usd: int = 950
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        vertical: str,
        metro: str,
        *,
        run_id: str | None = None,
        root: Path | None = None,
        language: Language = Language.EN,
        limit: int = 20,
        min_reviews: int = MIN_REVIEWS,
        min_rating: float = MIN_RATING,
        score_concurrency: int = 5,
        contact_concurrency: int = 8,
        probe_site: bool = True,
        dry_run: bool = True,
        simulated: bool = True,
        seed: int = 42,
        author_name: str = "",
        author_url: str = "",
        base_url: str = "",
        sender: SenderIdentity | None = None,
        offer_price_usd: int = 950,
    ) -> RunContext:
        """Genera un `run_id` (si no se pasa uno) y calcula las tres rutas de
        artefactos a partir de él. `root` es para tests; en producción siempre
        `gtm/build/runs/`."""
        rid = run_id or uuid.uuid4().hex[:12]
        run_root = (root or config.BUILD_DIR / "runs") / rid
        return cls(
            run_id=rid,
            vertical=vertical,
            metro=metro,
            data_dir=run_root / "data",
            demos_dir=run_root / "demos",
            public_dir=run_root / "public",
            language=language,
            limit=limit,
            min_reviews=min_reviews,
            min_rating=min_rating,
            score_concurrency=score_concurrency,
            contact_concurrency=contact_concurrency,
            probe_site=probe_site,
            dry_run=dry_run,
            simulated=simulated,
            seed=seed,
            author_name=author_name,
            author_url=author_url,
            base_url=base_url,
            sender=sender,
            offer_price_usd=offer_price_usd,
        )

    def ensure_dirs(self) -> None:
        for directory in (self.data_dir, self.demos_dir, self.public_dir):
            directory.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True, slots=True)
class StageResult:
    """Resultado de una sola etapa: cuánto tardó, cuántos ítems produjo, si falló."""

    stage: Stage
    ok: bool
    count: int
    duration_ms: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class RunResult:
    """Resultado completo de una corrida: una `StageResult` por etapa que llegó a
    correr, más los artefactos acumulados. Una etapa que falla corta el resto."""

    ctx: RunContext
    stages: tuple[StageResult, ...]
    prospects: tuple[Prospect, ...] = ()
    scores: tuple[PainScore, ...] = ()
    demos: tuple[Demo, ...] = ()
    contacts: tuple[ContactPlan, ...] = ()
    emails: tuple[OutreachEmail, ...] = ()

    @property
    def ok(self) -> bool:
        return all(stage.ok for stage in self.stages)

    def stage_result(self, stage: Stage) -> StageResult | None:
        return next((s for s in self.stages if s.stage is stage), None)


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """Un evento de progreso. `kind` es uno de "stage_start", "item", "stage_end",
    "log", "error" — deliberadamente `str`, no un enum cerrado: nuevos tipos de
    evento no deben exigir un release coordinado del lado que los consume (SSE)."""

    run_id: str
    stage: Stage | None
    kind: str
    index: int = 0
    total: int = 0
    message: str = ""
    at: datetime = field(default_factory=lambda: datetime.now(UTC))


ProgressFn = Callable[[ProgressEvent], None] | None
"""Sincrónico a propósito: el consumidor SSE lo implementa como
`queue.put_nowait(event)`, que nunca bloquea y nunca necesita `await`; un callback
async forzaría `to_thread` en las tres etapas sync sin ganar nada a cambio."""


def _emit(emit: ProgressFn, run_id: str, stage: Stage | None, kind: str, **kwargs: object) -> None:
    if emit is not None:
        emit(ProgressEvent(run_id=run_id, stage=stage, kind=kind, **kwargs))  # type: ignore[arg-type]


def _ms_since(start: float) -> int:
    return round((time.monotonic() - start) * 1000)


async def run_pipeline(
    ctx: RunContext,
    emit: ProgressFn = None,
    *,
    suppression: SuppressionList | None = None,
) -> RunResult:
    """Corre discover/simulate -> score -> generate -> deploy -> contact ->
    outreach, en ese orden, persistiendo cada etapa en `ctx.data_dir` con
    `gtm.factory.artifacts` — los mismos archivos que deja la secuencia de CLI.

    Una etapa que falla corta las siguientes (no tiene sentido puntuar sin
    prospectos), pero el resultado hasta ese punto se devuelve igual: la UI
    necesita mostrar qué se alcanzó a hacer, no solo "falló".
    """
    ctx.ensure_dirs()
    suppression_list = suppression if suppression is not None else SuppressionList()
    stages: list[StageResult] = []

    # --- discover / simulate ---
    _emit(emit, ctx.run_id, Stage.DISCOVER, "stage_start")
    t0 = time.monotonic()
    try:
        if ctx.simulated:
            prospects, simulated_scores = await asyncio.to_thread(
                simulate, ctx.vertical, ctx.metro, ctx.limit, ctx.seed
            )
        else:
            prospects = await asyncio.to_thread(
                discover,
                ctx.vertical,
                ctx.metro,
                ctx.limit,
                min_reviews=ctx.min_reviews,
                min_rating=ctx.min_rating,
            )
            simulated_scores = None
    except Exception as exc:  # noqa: BLE001 - se reporta como StageResult, no se re-lanza
        stages.append(StageResult(Stage.DISCOVER, False, 0, _ms_since(t0), str(exc)))
        _emit(emit, ctx.run_id, Stage.DISCOVER, "error", message=str(exc))
        return RunResult(ctx, tuple(stages))

    prospects, suppressed_early = suppression_list.filter_out(prospects)
    if suppressed_early:
        _logger.info(
            "prospectos suprimidos antes de puntuar",
            extra={"event": "run_suppressed_early", "run_id": ctx.run_id, "count": len(suppressed_early)},
        )

    artifacts.write_prospects(ctx.data_dir / "prospects.json", prospects)
    stages.append(StageResult(Stage.DISCOVER, True, len(prospects), _ms_since(t0)))
    _emit(emit, ctx.run_id, Stage.DISCOVER, "stage_end", total=len(prospects))

    if not prospects:
        return RunResult(ctx, tuple(stages), prospects=tuple(prospects))

    # --- score ---
    _emit(emit, ctx.run_id, Stage.SCORE, "stage_start", total=len(prospects))
    t0 = time.monotonic()
    if simulated_scores is not None:
        scores = simulated_scores
        for score in scores:
            _emit(emit, ctx.run_id, Stage.SCORE, "item", message=score.place_id)
    else:
        api_key = config.optional_env("PAGESPEED_API_KEY") or None
        # Mismo proyecto de Google Cloud habilita las dos APIs: si no hay una
        # key dedicada para CrUX, la de PageSpeed también sirve.
        crux_api_key = config.optional_env("CRUX_API_KEY") or api_key

        def _on_scored(place_id: str) -> None:
            _emit(emit, ctx.run_id, Stage.SCORE, "item", message=place_id)

        scores = await score_all(
            prospects, api_key, ctx.score_concurrency,
            crux_api_key=crux_api_key, on_item=_on_scored,
        )
    artifacts.write_scores(ctx.data_dir / "scores.json", scores)
    stages.append(StageResult(Stage.SCORE, True, len(scores), _ms_since(t0)))
    _emit(emit, ctx.run_id, Stage.SCORE, "stage_end", total=len(scores))

    # --- generate (solo prospectos que califican: gastar en el resto es ruido) ---
    _emit(emit, ctx.run_id, Stage.GENERATE, "stage_start")
    t0 = time.monotonic()
    qualified_ids = {s.place_id for s in scores if s.is_qualified}
    by_id = {p.place_id: p for p in prospects}
    targets = [by_id[pid] for pid in qualified_ids if pid in by_id]

    demos: list[Demo] = []
    for prospect in targets:
        try:
            demo = await asyncio.to_thread(
                generate,
                prospect,
                ctx.author_name,
                ctx.author_url,
                ctx.language,
                demos_dir=ctx.demos_dir,
            )
        except GenerationError as exc:
            _logger.warning(
                "demo omitida",
                extra={"event": "run_demo_skipped", "run_id": ctx.run_id, "place_id": prospect.place_id, "error": str(exc)},
            )
            continue
        demos.append(demo)
        _emit(emit, ctx.run_id, Stage.GENERATE, "item", message=prospect.place_id)

    artifacts.write_demos(ctx.data_dir / "demos.json", demos)
    stages.append(StageResult(Stage.GENERATE, True, len(demos), _ms_since(t0)))
    _emit(emit, ctx.run_id, Stage.GENERATE, "stage_end", total=len(demos))

    if not demos:
        return RunResult(
            ctx, tuple(stages), prospects=tuple(prospects), scores=tuple(scores), demos=()
        )

    # --- deploy ---
    _emit(emit, ctx.run_id, Stage.DEPLOY, "stage_start", total=len(demos))
    t0 = time.monotonic()
    try:
        published = await asyncio.to_thread(
            deploy_demos, demos, ctx.base_url, dry_run=ctx.dry_run, public_dir=ctx.public_dir
        )
    except Exception as exc:  # noqa: BLE001 - se reporta como StageResult
        stages.append(StageResult(Stage.DEPLOY, False, 0, _ms_since(t0), str(exc)))
        _emit(emit, ctx.run_id, Stage.DEPLOY, "error", message=str(exc))
        return RunResult(
            ctx, tuple(stages), prospects=tuple(prospects), scores=tuple(scores), demos=tuple(demos)
        )

    artifacts.write_demos(ctx.data_dir / "demos.json", published)
    stages.append(StageResult(Stage.DEPLOY, True, len(published), _ms_since(t0)))
    _emit(emit, ctx.run_id, Stage.DEPLOY, "stage_end", total=len(published))

    # --- contact ---
    _emit(emit, ctx.run_id, Stage.CONTACT, "stage_start")
    t0 = time.monotonic()
    demo_by_id = {d.place_id: d for d in published}
    contact_targets = [p for p in targets if p.place_id in demo_by_id]
    contact_targets, suppressed_before_contact = suppression_list.filter_out(contact_targets)
    if suppressed_before_contact:
        _logger.info(
            "prospectos suprimidos antes de contactar",
            extra={
                "event": "run_suppressed_before_contact",
                "run_id": ctx.run_id,
                "count": len(suppressed_before_contact),
            },
        )

    scores_by_id = {s.place_id: s for s in scores}

    def _on_resolved(place_id: str) -> None:
        _emit(emit, ctx.run_id, Stage.CONTACT, "item", message=place_id)

    plans = await resolve_all(
        contact_targets,
        scores_by_id,
        probe_site=ctx.probe_site,
        concurrency=ctx.contact_concurrency,
        on_item=_on_resolved,
    )
    artifacts.write_contacts(ctx.data_dir / "contacts.json", plans)
    stages.append(StageResult(Stage.CONTACT, True, len(plans), _ms_since(t0)))
    _emit(emit, ctx.run_id, Stage.CONTACT, "stage_end", total=len(plans))

    # --- outreach: opcional. Sin remitente configurado no hay email conforme que
    # construir, y eso no es un fallo de la corrida -- es la UI todavía sin
    # configurar el .env, que ya se puede prevalidar con config.check_config().
    emails: list[OutreachEmail] = []
    if ctx.sender is not None:
        _emit(emit, ctx.run_id, Stage.OUTREACH, "stage_start")
        t0 = time.monotonic()
        for prospect in contact_targets:
            outreach_demo = demo_by_id.get(prospect.place_id)
            if outreach_demo is None:
                continue
            try:
                email = build_email(
                    prospect,
                    outreach_demo,
                    ctx.sender,
                    scores_by_id.get(prospect.place_id),
                    language=ctx.language,
                    price_usd=ctx.offer_price_usd,
                )
            except ComplianceError as exc:
                _logger.warning(
                    "email descartado por incumplimiento",
                    extra={
                        "event": "run_email_rejected",
                        "run_id": ctx.run_id,
                        "place_id": prospect.place_id,
                        "error": str(exc),
                    },
                )
                continue
            emails.append(email)
            _emit(emit, ctx.run_id, Stage.OUTREACH, "item", message=prospect.place_id)

        artifacts.write_emails(ctx.data_dir / "emails.json", emails)
        stages.append(StageResult(Stage.OUTREACH, True, len(emails), _ms_since(t0)))
        _emit(emit, ctx.run_id, Stage.OUTREACH, "stage_end", total=len(emails))

    return RunResult(
        ctx=ctx,
        stages=tuple(stages),
        prospects=tuple(prospects),
        scores=tuple(scores),
        demos=tuple(published),
        contacts=tuple(plans),
        emails=tuple(emails),
    )


def _stdout_progress(event: ProgressEvent) -> None:
    stage = event.stage.value if event.stage else "-"
    if event.kind == "stage_start":
        print(f"[{stage}] iniciando...")
    elif event.kind == "stage_end":
        print(f"[{stage}] listo ({event.total})")
    elif event.kind == "error":
        print(f"[{stage}] ERROR: {event.message}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """CLI unificada, equivalente a encadenar los 8 comandos a mano.

    No reemplaza a los 8 `main(argv)` existentes -- cada uno sigue siendo el
    punto de entrada de su etapa cuando hace falta correrla sola o con flags que
    esta CLI no expone.
    """
    parser = argparse.ArgumentParser(description="Corre el pipeline completo en un proceso")
    parser.add_argument("--vertical", required=True)
    parser.add_argument("--metro", required=True)
    parser.add_argument("--language", default="en", choices=[lang.value for lang in Language])
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--simulate", action="store_true", help="usa datos sintéticos")
    parser.add_argument("--seed", type=int, default=42, help="solo con --simulate")
    parser.add_argument("--dry-run", action="store_true", help="no publica nada")
    parser.add_argument("--no-probe", action="store_true", help="no descarga sitios en contact")
    parser.add_argument("--author-name", default=None, help="default: $GTM_FROM_NAME")
    parser.add_argument("--author-url", default=None, help="default: $GTM_UNSUBSCRIBE_URL")
    parser.add_argument("--base-url", default=None, help="default: $GTM_DEMO_BASE_URL")
    parser.add_argument(
        "--with-outreach",
        action="store_true",
        help="también arma los emails (exige el remitente completo en .env.personal)",
    )
    args = parser.parse_args(argv)

    sender = None
    if args.with_outreach:
        sender = config.load_sender_identity()

    ctx = RunContext.create(
        args.vertical,
        args.metro,
        language=Language(args.language),
        limit=args.limit,
        simulated=args.simulate,
        seed=args.seed,
        dry_run=args.dry_run,
        probe_site=not args.no_probe,
        author_name=args.author_name or config.optional_env("GTM_FROM_NAME"),
        author_url=args.author_url or config.optional_env("GTM_UNSUBSCRIBE_URL"),
        base_url=args.base_url or config.optional_env("GTM_DEMO_BASE_URL"),
        sender=sender,
    )

    result = asyncio.run(run_pipeline(ctx, emit=_stdout_progress))

    print(f"\nrun_id={result.ctx.run_id}  ok={result.ok}")
    for stage_result in result.stages:
        status = "OK" if stage_result.ok else "FALLÓ"
        print(f"  {stage_result.stage.value:<10} {status:<5} {stage_result.count:>4} items  {stage_result.duration_ms:>6}ms")
    print(f"\nArtefactos en {ctx.data_dir}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
