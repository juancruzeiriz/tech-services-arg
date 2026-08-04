"""Runner de migraciones: SQL plano + una tabla de versiones.

No alembic: alembic autogenera diffs desde modelos SQLAlchemy, y este proyecto no
tiene ORM ni SQLAlchemy en ningún lado — adoptarlo para redescribir en Python las
11 tablas que ya están descritas en `schema/0001_init.sql` sería una dependencia
grande a cambio de reemplazar ~80 líneas de runner.

La única garantía real que un runner naive NO da y este SÍ: si una migración ya
aplicada cambió de contenido en disco, `migrate()` se niega a correr en vez de
aplicar el archivo modificado o ignorarlo en silencio. Es el mismo principio que
`decision_criteria.yaml` — el historial de lo que se aplicó no se reescribe.

Uso:
    python -m gtm.store.migrate            # aplica lo pendiente
    python -m gtm.store.migrate --status   # solo muestra el estado, no aplica
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from gtm.store.dsn import get_dsn

_SCHEMA_DIR = Path(__file__).resolve().parent / "schema"

_BOOTSTRAP_SQL = """
create table if not exists schema_migrations (
    version     text primary key,
    applied_at  timestamptz not null default now(),
    checksum    text not null
);
"""


class MigrationError(Exception):
    """Estado inconsistente: una migración aplicada cambió de contenido."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    path: Path
    sql: str
    checksum: str


class Executor(Protocol):
    """Lo mínimo que el runner necesita de una conexión — un `Protocol`, no
    `psycopg.Connection`, para poder probar el orden/checksum/idempotencia con
    un doble en memoria (`FakeExecutor`, en los tests), sin una base de datos
    real. CI no tiene Postgres; esto es lo que permite probar la lógica igual.
    """

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None: ...
    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[tuple[object, ...]]: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def discover_migrations(schema_dir: Path | None = None) -> list[Migration]:
    """Todas las migraciones en `schema/`, ordenadas por nombre de archivo —
    por eso el prefijo numérico (`0001_`, `0002_`, ...)."""
    directory = schema_dir or _SCHEMA_DIR
    return [
        Migration(version=path.stem, path=path, sql=(sql := path.read_text(encoding="utf-8")), checksum=_checksum(sql))
        for path in sorted(directory.glob("*.sql"))
    ]


def applied_versions(executor: Executor) -> dict[str, str]:
    """version -> checksum de lo que ya corrió. Vacío en la primera corrida."""
    executor.execute(_BOOTSTRAP_SQL)
    executor.commit()
    rows = executor.fetch_all("select version, checksum from schema_migrations")
    return {str(version): str(checksum) for version, checksum in rows}


def plan(migrations: list[Migration], applied: dict[str, str]) -> list[Migration]:
    """Qué migraciones faltan aplicar.

    Raises:
        MigrationError: si una ya aplicada tiene un checksum distinto al del
            archivo en disco — se editó después de aplicarse.
    """
    pending: list[Migration] = []
    for migration in migrations:
        seen_checksum = applied.get(migration.version)
        if seen_checksum is None:
            pending.append(migration)
        elif seen_checksum != migration.checksum:
            raise MigrationError(
                f"{migration.version} ya se aplicó pero el archivo cambió "
                f"(checksum {seen_checksum[:12]}... -> {migration.checksum[:12]}...): "
                "no se edita una migración aplicada, se escribe una nueva."
            )
    return pending


def apply_migration(executor: Executor, migration: Migration) -> None:
    try:
        executor.execute(migration.sql)
        executor.execute(
            "insert into schema_migrations (version, checksum) values (%s, %s)",
            (migration.version, migration.checksum),
        )
    except Exception:
        executor.rollback()
        raise
    else:
        executor.commit()


def migrate(executor: Executor, schema_dir: Path | None = None) -> list[str]:
    """Aplica toda migración pendiente, en orden. Devuelve las versiones recién
    aplicadas (vacío si no había nada que hacer)."""
    migrations = discover_migrations(schema_dir)
    applied = applied_versions(executor)
    pending = plan(migrations, applied)
    for migration in pending:
        apply_migration(executor, migration)
    return [m.version for m in pending]


class PsycopgExecutor:
    """Adapta una conexión sync de `psycopg` al `Protocol` `Executor` de arriba."""

    def __init__(self, conn: object) -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        with self._conn.cursor() as cur:  # type: ignore[attr-defined]
            cur.execute(sql, params)

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
        with self._conn.cursor() as cur:  # type: ignore[attr-defined]
            cur.execute(sql, params)
            return cur.fetchall()  # type: ignore[no-any-return]

    def commit(self) -> None:
        self._conn.commit()  # type: ignore[attr-defined]

    def rollback(self) -> None:
        self._conn.rollback()  # type: ignore[attr-defined]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aplica las migraciones pendientes del store")
    parser.add_argument(
        "--status", action="store_true", help="solo muestra el estado, no aplica nada"
    )
    args = parser.parse_args(argv)

    dsn = get_dsn()
    if dsn is None:
        print("Falta SUPABASE_DB_URL en .env.personal", file=sys.stderr)
        return 1

    import psycopg

    with psycopg.connect(dsn) as conn:
        executor = PsycopgExecutor(conn)
        migrations = discover_migrations()
        applied = applied_versions(executor)

        if args.status:
            for migration in migrations:
                mark = "x" if migration.version in applied else " "
                print(f"  [{mark}] {migration.version}")
            pending_count = len(plan(migrations, applied))
            print(f"\n{pending_count} pendientes de {len(migrations)}")
            return 0

        applied_now = migrate(executor, None)

    if applied_now:
        for version in applied_now:
            print(f"  aplicada: {version}")
    print(f"{len(applied_now)} migraciones aplicadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
