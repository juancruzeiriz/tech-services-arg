"""Registros persistentes: lista de supresión y embudo.

Los dos comparten un problema y por eso comparten módulo: tienen que sobrevivir entre
corridas y entre máquinas —si se pierden, le volvés a escribir a quien pidió que no, y
el criterio de kill queda sin nada contra qué medirse— pero no pueden contener datos de
contacto de negocios reales, porque el historial de un repo es permanente y público.

La salida es guardar **hashes**. Un SHA-256 de un place_id o de un teléfono normalizado
alcanza para responder "¿a este ya lo contacté?" sin almacenar a quién. Los archivos
(`gtm/suppression.jsonl`, `gtm/funnel.jsonl`) sí van a git: son la memoria del sistema.

Formato JSONL append-only: dos corridas concurrentes no se pisan, y el historial de git
muestra exactamente qué se supo y cuándo.

Uso:
    python -m gtm.factory.ledger suppress --place-id ChIJ... --reason opted_out
    python -m gtm.factory.ledger record --place-id ChIJ... --event replied
    python -m gtm.factory.ledger report --spend 150
    python -m gtm.factory.ledger sync-unsubscribes
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from gtm.factory import config
from gtm.factory.logs import get_logger
from gtm.factory.types import (
    ContactChannel,
    FunnelEvent,
    GTMError,
    Language,
    Prospect,
    SuppressionReason,
)

_logger = get_logger(__name__)

SUPPRESSION_PATH = config.GTM_DIR / "suppression.jsonl"
FUNNEL_PATH = config.GTM_DIR / "funnel.jsonl"


class LedgerError(GTMError):
    """Error de lectura o escritura de un registro persistente."""


def _normalize(kind: str, value: str) -> str:
    """Normaliza antes de hashear: "(520) 555-0148" y "5205550148" son el mismo negocio."""
    cleaned = value.strip().lower()
    if kind == "phone":
        return re.sub(r"\D", "", cleaned)
    if kind == "domain":
        host = urlparse(cleaned if "//" in cleaned else f"//{cleaned}").netloc or cleaned
        return host.removeprefix("www.")
    return cleaned


def hash_key(kind: str, value: str) -> str:
    """Clave estable y no reversible. El `kind` va adentro para que un teléfono y un
    place_id con el mismo texto no colisionen."""
    normalized = _normalize(kind, value)
    if not normalized:
        raise LedgerError(f"Valor vacío para {kind!r}: no se puede hashear")
    return hashlib.sha256(f"{kind}:{normalized}".encode()).hexdigest()[:32]


def prospect_keys(prospect: Prospect) -> set[str]:
    """Todas las claves con las que un prospecto puede estar suprimido.

    Se chequean varias porque el mismo negocio puede reaparecer con otro place_id
    (Google los reemite) pero conservando teléfono y dominio.
    """
    keys = {hash_key("place_id", prospect.place_id)}
    if prospect.phone:
        keys.add(hash_key("phone", prospect.phone))
    if prospect.website:
        # Un website presente pero basura (cadena vacía tras normalizar) no debe
        # impedir el chequeo por place_id y teléfono, que son los que importan.
        with contextlib.suppress(LedgerError):
            keys.add(hash_key("domain", prospect.website))
    return keys


def _append(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                # Una línea corrupta no puede invalidar todo el registro: perder la
                # lista de supresión entera significaría re-contactar a todos.
                _logger.warning(
                    "línea ilegible en el registro",
                    extra={
                        "event": "ledger_bad_line",
                        "path": str(path),
                        "line_no": line_no,
                        "error": str(exc),
                    },
                )
    return records


def read_suppression_records(path: Path | None = None) -> list[dict[str, Any]]:
    """Registros crudos de supresión, tal como están en el JSONL — sin agregar
    ni deduplicar. Para el backfill a Postgres (`gtm/store/backfill.py`); el uso
    normal del pipeline pasa por `SuppressionList`, no por acá."""
    return _read(path or SUPPRESSION_PATH)


def read_funnel_records(path: Path | None = None) -> list[dict[str, Any]]:
    """Igual que `read_suppression_records`, para `gtm/funnel.jsonl`."""
    return _read(path or FUNNEL_PATH)


class SuppressionList:
    """A quién no hay que volver a contactar."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or SUPPRESSION_PATH
        self._keys: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        self._keys = {}
        for record in _read(self.path):
            key = record.get("key")
            if key:
                self._keys[key] = record.get("reason", SuppressionReason.CONTACTED.value)

    def add(self, kind: str, value: str, reason: SuppressionReason, note: str = "") -> str:
        """Suprime un identificador. Idempotente: repetirlo no duplica el efecto."""
        key = hash_key(kind, value)
        _append(
            self.path,
            {
                "key": key,
                "kind": kind,
                "reason": reason.value,
                "at": datetime.now(UTC).isoformat(),
                "note": note,
            },
        )
        self._keys[key] = reason.value
        _logger.info(
            "prospecto suprimido",
            extra={"event": "suppressed", "kind": kind, "reason": reason.value},
        )
        return key

    def suppress_prospect(self, prospect: Prospect, reason: SuppressionReason) -> None:
        """Suprime por place_id y, si hay, también por teléfono y dominio."""
        self.add("place_id", prospect.place_id, reason)
        if prospect.phone:
            self.add("phone", prospect.phone, reason)

    def reason_for(self, prospect: Prospect) -> SuppressionReason | None:
        for key in prospect_keys(prospect):
            if key in self._keys:
                return SuppressionReason(self._keys[key])
        return None

    def contains(self, prospect: Prospect) -> bool:
        return self.reason_for(prospect) is not None

    def reason_for_key(self, kind: str, value: str) -> SuppressionReason | None:
        """Como `reason_for`, para un `(kind, value)` suelto en vez de un
        `Prospect` entero -- lo que necesita `gtm/send/worker.py` para chequear
        un `to_address` de email antes de enviar, ya que un mensaje en el outbox
        no trae el `Prospect` completo."""
        try:
            key = hash_key(kind, value)
        except LedgerError:
            return None
        reason = self._keys.get(key)
        return SuppressionReason(reason) if reason else None

    def contains_key(self, kind: str, value: str) -> bool:
        return self.reason_for_key(kind, value) is not None

    def filter_out(self, prospects: list[Prospect]) -> tuple[list[Prospect], list[Prospect]]:
        """Separa en (contactables, suprimidos)."""
        allowed: list[Prospect] = []
        blocked: list[Prospect] = []
        for prospect in prospects:
            (blocked if self.contains(prospect) else allowed).append(prospect)

        if blocked:
            _logger.info(
                "prospectos filtrados por supresión",
                extra={"event": "suppression_filtered", "blocked": len(blocked)},
            )
        return allowed, blocked

    def __len__(self) -> int:
        return len(self._keys)


def fetch_unsynced_unsubscribes(executor: Any) -> list[dict[str, Any]]:
    """Filas de `unsubscribes` (Postgres) que `sync_unsubscribes` todavía no
    volcó a la lista de supresión local. `executor` sigue el mismo `Protocol`
    que `gtm.store.migrate.Executor` (no `psycopg.Connection` directo), para
    poder probar `sync_unsubscribes` con un doble en memoria, igual que el
    runner de migraciones."""
    rows = executor.fetch_all(
        "select id, email from unsubscribes where synced_at is null order by at"
    )
    return [{"id": str(row[0]), "email": str(row[1])} for row in rows]


def mark_unsubscribes_synced(executor: Any, ids: list[str]) -> None:
    if not ids:
        return
    executor.execute(
        "update unsubscribes set synced_at = now() where id = any(%s)",
        (ids,),
    )
    executor.commit()


def sync_unsubscribes(executor: Any, suppression: SuppressionList | None = None) -> int:
    """Vuelca cada baja pendiente de Postgres a la lista de supresión local
    (`gtm/suppression.jsonl`), que es la que de verdad filtra a quién no se
    vuelve a contactar -- Postgres es el buzón de entrada del formulario web
    (`site/functions/api/unsubscribe.js`), no la fuente de decisión.

    Suprime por `email` (no por `place_id`): el link de baja es una URL fija
    para todos los envíos, `outreach.py` no genera un token por email
    enviado, así que no hay forma de saber solo con el clic a qué prospecto
    corresponde -- ver el comentario en `0007_unsubscribes.sql`.

    Devuelve cuántas filas se sincronizaron. Idempotente: correrlo de nuevo
    sin filas nuevas no hace nada (`synced_at` ya está seteado).
    """
    # `suppression or SuppressionList()` sería un bug real acá: `SuppressionList`
    # define `__len__`, así que una lista vacía (el caso normal, recién creada
    # en un test con tmp_path) es *falsy* y el `or` la reemplazaría en
    # silencio por una instancia nueva sin `path` -- que escribe en el
    # `gtm/suppression.jsonl` real del repo, no en la que pasó el caller.
    if suppression is None:
        suppression = SuppressionList()
    pending = fetch_unsynced_unsubscribes(executor)
    for row in pending:
        suppression.add("email", row["email"], SuppressionReason.OPTED_OUT, "vía unsubscribe.js")
    mark_unsubscribes_synced(executor, [row["id"] for row in pending])
    return len(pending)


@dataclass(frozen=True, slots=True)
class FunnelReport:
    """Estado del embudo contra el criterio pre-registrado."""

    counts: dict[str, int]
    unique_prospects: int
    revenue_usd: float
    spend_usd: float

    @property
    def contacted(self) -> int:
        return self.counts.get(FunnelEvent.CONTACTED.value, 0)

    @property
    def replied(self) -> int:
        return self.counts.get(FunnelEvent.REPLIED.value, 0)

    @property
    def calls_booked(self) -> int:
        return self.counts.get(FunnelEvent.CALL_BOOKED.value, 0)

    @property
    def paid(self) -> int:
        return self.counts.get(FunnelEvent.PAID.value, 0)

    @property
    def reply_rate(self) -> float:
        return self.replied / self.contacted if self.contacted else 0.0

    @property
    def cost_per_call(self) -> float | None:
        """Costo por señal Nivel-3. None si todavía no hay ninguna."""
        return self.spend_usd / self.calls_booked if self.calls_booked else None

    @property
    def cost_per_contact(self) -> float | None:
        """Costo por prospecto contactado (Nivel-1). A diferencia de
        `cost_per_call`, no espera ninguna señal de interés -- es el "techo de
        gasto" real del proyecto (ver docs/PLAN_DIARIO.md, Día 17): la
        publicidad paga se descartó por aritmética (README.md), así que lo que
        sí importa vigilar acá es cuánto cuesta cada prospecto contactado, no
        un CPC de un canal que no se usa."""
        return self.spend_usd / self.contacted if self.contacted else None

    @property
    def has_winner(self) -> bool:
        """Criterio pre-registrado (v2): 1 venta cobrada. Nivel 5 es terminal.

        v1 admitía una vía alternativa ("3 llamadas agendadas") que resultó
        estadísticamente inalcanzable al volumen del experimento y se retiró en el
        re-registro — ver decision_criteria.yaml.
        """
        return self.paid >= 1

    @property
    def kill_triggered(self) -> tuple[bool, str]:
        """Criterio de kill pre-registrado (v2), con el motivo.

        Si se dispara, lo que cambia es el vertical o la oferta — **no la redacción**.
        Retocar el asunto por décima vez es la forma más común de no aceptar un no.
        """
        if self.contacted >= 200 and self.paid == 0 and self.replied < 5:
            return True, (
                f"{self.contacted} contactados, {self.paid} ventas y solo "
                f"{self.replied} respuestas"
            )
        if self.replied >= 10 and self.calls_booked == 0:
            return True, f"{self.replied} respuestas y ninguna llamada agendada"
        return False, ""


class FollowupStage(StrEnum):
    """Etapa de la cadencia de seguimiento Día 0/3/7 (`gtm/pipeline.md`).

    Deliberadamente no es un `FunnelEvent`: los cinco escalones del embudo son
    el compromiso pre-registrado de `decision_criteria.yaml` y agregar uno
    nuevo exigiría re-registrar el experimento. La cadencia se DERIVA de lo
    que ya está -- un `CONTACTED` sin `REPLIED` (ni nada posterior) de la
    misma clave -- no agrega un evento nuevo al embudo.
    """

    NUDGE = "nudge"
    """Día 3: recordatorio corto, mismo canal."""

    CLOSE = "close"
    """Día 7: sin respuesta, dar por no interesado por ahora
    (`SuppressionReason.NOT_INTERESTED`, no permanente) -- la demo sigue
    online, el costo de dejarla es casi cero."""


@dataclass(frozen=True, slots=True)
class FollowupDue:
    """Un prospecto contactado que no respondió, listo para su seguimiento.

    `key` es la clave hasheada (`hash_key("place_id", ...)`), no el place_id:
    el ledger nunca guarda identificadores en claro. El llamador (la cola de
    contacto) recorre sus propios prospectos accionables y recalcula
    `hash_key("place_id", plan.place_id)` para saber a cuál de ellos
    corresponde cada `FollowupDue`.
    """

    key: str
    days_since_contact: float
    stage: FollowupStage


class FunnelLedger:
    """Registro de eventos del embudo. Hace operativo a decision_criteria.yaml."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or FUNNEL_PATH

    def record(
        self,
        place_id: str,
        event: FunnelEvent,
        *,
        vertical: str = "",
        metro: str = "",
        channel: ContactChannel | str = "",
        language: Language | str = "",
        run_id: str = "",
        pain_score: int = 0,
        amount_usd: float = 0.0,
        note: str = "",
        at: datetime | None = None,
    ) -> None:
        """Registra un evento. Los metadatos no son personales: sirven para segmentar.

        `channel` e `idioma` son la segmentación que `decision_criteria.yaml` exige
        (`segmentacion_obligatoria`): sin ellos, "pocas respuestas" agregado no dice
        si el problema es el teléfono, el formulario, el inglés o el español —
        diagnósticos distintos con arreglos distintos.

        `at`: inyectable para tests y para reconstruir eventos históricos (mismo
        patrón que `store.repo`); por defecto, el momento real del registro.
        """
        channel_value = channel.value if isinstance(channel, ContactChannel) else channel
        language_value = language.value if isinstance(language, Language) else language
        _append(
            self.path,
            {
                "key": hash_key("place_id", place_id),
                "event": event.value,
                "level": event.level,
                "at": (at or datetime.now(UTC)).isoformat(),
                "vertical": vertical,
                "metro": metro,
                "channel": channel_value,
                "language": language_value,
                "run_id": run_id,
                "pain_score": pain_score,
                "amount_usd": amount_usd,
                "note": note,
            },
        )

    def report(
        self,
        spend_usd: float = 0.0,
        vertical: str | None = None,
        channel: str | None = None,
        language: str | None = None,
        metro: str | None = None,
    ) -> FunnelReport:
        """Agrega el embudo. Cada prospecto cuenta una vez por escalón alcanzado.

        `channel`/`language`/`metro` filtran igual que `vertical`: registros
        grabados antes de que existieran esos campos quedan afuera de un filtro
        explícito (su valor es `""`), no adentro por accidente.
        """
        seen: set[tuple[str, str]] = set()
        counts: Counter[str] = Counter()
        prospects: set[str] = set()
        revenue = 0.0

        for record in _read(self.path):
            if vertical and record.get("vertical") != vertical:
                continue
            if channel and record.get("channel") != channel:
                continue
            if language and record.get("language") != language:
                continue
            if metro and record.get("metro") != metro:
                continue
            key = record.get("key", "")
            event = record.get("event", "")
            if not key or not event:
                continue

            prospects.add(key)
            # Dos "replied" del mismo negocio son una sola respuesta.
            if (key, event) not in seen:
                seen.add((key, event))
                counts[event] += 1
            revenue += float(record.get("amount_usd", 0) or 0)

        return FunnelReport(
            counts=dict(counts),
            unique_prospects=len(prospects),
            revenue_usd=revenue,
            spend_usd=spend_usd,
        )

    def due_followups(
        self,
        now: datetime | None = None,
        *,
        nudge_after_days: int = 3,
        close_after_days: int = 7,
    ) -> list[FollowupDue]:
        """Prospectos con un `CONTACTED` sin `REPLIED` (ni nada posterior) de
        la misma clave, hace `nudge_after_days` o más.

        No agrega ningún evento al embudo -- ver el docstring de
        `FollowupStage`. `now` es un parámetro, no `datetime.now(UTC)` interno,
        para que el resultado no dependa del reloj real de quien corre el test.
        """
        now = now or datetime.now(UTC)

        last_contacted: dict[str, datetime] = {}
        progressed: set[str] = set()

        for record in _read(self.path):
            key = record.get("key", "")
            event = record.get("event", "")
            if not key or not event:
                continue

            if event == FunnelEvent.CONTACTED.value:
                try:
                    last_contacted[key] = datetime.fromisoformat(record.get("at", ""))
                except ValueError:
                    continue
                # Un contacto nuevo reabre la ventana: CONTACTED es válido de
                # reintentar (a diferencia de OPTED_OUT), y si se reintentó es
                # porque el ciclo anterior no llegó a nada -- vuelve a estar
                # pendiente desde cero.
                progressed.discard(key)
            elif key in last_contacted:
                progressed.add(key)

        due: list[FollowupDue] = []
        for key, contacted_at in last_contacted.items():
            if key in progressed:
                continue
            days = (now - contacted_at).total_seconds() / 86400
            if days < nudge_after_days:
                continue
            stage = FollowupStage.CLOSE if days >= close_after_days else FollowupStage.NUDGE
            due.append(FollowupDue(key=key, days_since_contact=days, stage=stage))

        return due


def format_report(report: FunnelReport) -> str:
    """Reporte para terminal. A 5-10 hs semanales esto reemplaza a un dashboard."""
    lines = [
        "Embudo",
        "──────",
        f"  Nivel 1  contactados      {report.contacted:>4}",
        f"  Nivel 2  respondieron     {report.replied:>4}   ({report.reply_rate:.1%})",
        f"  Nivel 3  llamadas         {report.calls_booked:>4}",
        f"  Nivel 4  propuestas       {report.counts.get('proposal_sent', 0):>4}",
        f"  Nivel 5  pagaron          {report.paid:>4}",
        "",
        f"  Ingresos   USD {report.revenue_usd:>8,.0f}",
        f"  Gasto      USD {report.spend_usd:>8,.0f}",
    ]

    if report.cost_per_call is not None:
        lines.append(f"  Costo por llamada agendada  USD {report.cost_per_call:,.0f}")

    lines.append("")
    killed, motivo = report.kill_triggered
    if report.has_winner:
        lines.append("✅ GANADOR: se cumplió el criterio pre-registrado.")
    elif killed:
        lines += [
            f"🛑 KILL: {motivo}.",
            "   Cambiar de vertical u oferta — NO de redacción.",
        ]
    else:
        faltan_contactos = max(0, 200 - report.contacted)
        lines.append(
            f"⏳ En curso. Faltan {faltan_contactos} contactos para evaluar el criterio de kill."
        )
    return "\n".join(lines)


def _cmd_suppress(args: argparse.Namespace) -> int:
    suppression = SuppressionList()
    reason = SuppressionReason(args.reason)

    if args.place_id:
        suppression.add("place_id", args.place_id, reason, args.note)
    if args.phone:
        suppression.add("phone", args.phone, reason, args.note)
    if args.domain:
        suppression.add("domain", args.domain, reason, args.note)

    if not (args.place_id or args.phone or args.domain):
        print("Indicá --place-id, --phone o --domain", file=sys.stderr)
        return 1

    print(f"Suprimido como {reason.value}. Lista: {len(suppression)} entradas.")
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    FunnelLedger().record(
        args.place_id,
        FunnelEvent(args.event),
        vertical=args.vertical,
        metro=args.metro,
        channel=args.channel,
        language=args.language,
        pain_score=args.pain_score,
        amount_usd=args.amount,
        note=args.note,
    )
    print(f"Registrado: {args.event}")

    # Una venta saca al negocio de prospección: ya es cliente.
    if FunnelEvent(args.event) is FunnelEvent.PAID:
        SuppressionList().add("place_id", args.place_id, SuppressionReason.CUSTOMER)
        print("Y suprimido de prospección (ahora es cliente).")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    report = FunnelLedger().report(args.spend, args.vertical, args.channel, args.language)
    print(format_report(report))
    return 0


def _cmd_sync_unsubscribes(args: argparse.Namespace) -> int:
    from gtm.store.dsn import get_dsn
    from gtm.store.migrate import PsycopgExecutor

    dsn = get_dsn()
    if dsn is None:
        print("Falta SUPABASE_DB_URL en .env.personal", file=sys.stderr)
        return 1

    import psycopg

    with psycopg.connect(dsn) as conn:
        executor = PsycopgExecutor(conn)
        count = sync_unsubscribes(executor)

    print(f"{count} baja(s) sincronizada(s) a la lista de supresión local.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Registros persistentes del pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    suppress = sub.add_parser("suppress", help="agrega a la lista de supresión")
    suppress.add_argument("--place-id")
    suppress.add_argument("--phone")
    suppress.add_argument("--domain")
    suppress.add_argument(
        "--reason",
        default=SuppressionReason.OPTED_OUT.value,
        choices=[r.value for r in SuppressionReason],
    )
    suppress.add_argument("--note", default="")
    suppress.set_defaults(func=_cmd_suppress)

    record = sub.add_parser("record", help="registra un evento del embudo")
    record.add_argument("--place-id", required=True)
    record.add_argument("--event", required=True, choices=[e.value for e in FunnelEvent])
    record.add_argument("--vertical", default="")
    record.add_argument("--metro", default="")
    record.add_argument(
        "--channel",
        default="",
        choices=["", *(c.value for c in ContactChannel)],
        help="canal por el que se contactó (para segmentar el embudo)",
    )
    record.add_argument(
        "--language",
        default="",
        choices=["", *(lang.value for lang in Language)],
        help="idioma del mensaje enviado (para segmentar el embudo)",
    )
    record.add_argument(
        "--pain-score", type=int, default=0, help="score del prospecto al momento del evento"
    )
    record.add_argument("--amount", type=float, default=0.0)
    record.add_argument("--note", default="")
    record.set_defaults(func=_cmd_record)

    report = sub.add_parser("report", help="estado del embudo vs. criterio pre-registrado")
    report.add_argument("--spend", type=float, default=0.0, help="gasto acumulado en USD")
    report.add_argument("--vertical", default=None)
    report.add_argument("--channel", default=None, choices=[c.value for c in ContactChannel])
    report.add_argument("--language", default=None, choices=[lang.value for lang in Language])
    report.set_defaults(func=_cmd_report)

    sync_unsub = sub.add_parser(
        "sync-unsubscribes",
        help="vuelca las bajas nuevas de Postgres (unsubscribes) a la lista de supresión local",
    )
    sync_unsub.set_defaults(func=_cmd_sync_unsubscribes)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
