"""Tests del runner de migraciones (`gtm/store/migrate.py`).

Corren enteramente contra un `FakeExecutor` en memoria: CI no tiene Postgres, y
la lógica que importa (orden, checksums, idempotencia, rollback) no depende de
una base de datos real para probarse. El único test que sí necesita Postgres de
verdad está al final, gateado con `skipif` — corre solo si `SUPABASE_DB_URL` está
seteada (nunca en CI, opcionalmente en desarrollo local).
"""

from __future__ import annotations

import os

import pytest

from gtm.store.migrate import (
    Migration,
    MigrationError,
    apply_migration,
    discover_migrations,
    migrate,
    plan,
)


class FakeExecutor:
    """Doble en memoria del `Protocol Executor`. No es un mock de psycopg -- es
    una base de datos de juguete que solo entiende las dos consultas que el
    runner necesita, lo suficiente para probar la lógica sin infraestructura."""

    def __init__(self) -> None:
        self.migrations_table: dict[str, str] = {}
        self.executed_sql: list[str] = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_on_substring: str | None = None

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        self.executed_sql.append(sql)
        if self.fail_on_substring and self.fail_on_substring in sql:
            raise RuntimeError("boom: migración simulada rota")
        if "insert into schema_migrations" in sql:
            version, checksum = params
            self.migrations_table[str(version)] = str(checksum)

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
        if "select version, checksum from schema_migrations" in sql:
            return list(self.migrations_table.items())
        return []

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _write_migration(tmp_path, name: str, sql: str = "create table x();"):
    (tmp_path / name).write_text(sql, encoding="utf-8")


class TestDiscoverMigrations:
    def test_ordena_por_nombre_de_archivo(self, tmp_path):
        _write_migration(tmp_path, "0002_second.sql")
        _write_migration(tmp_path, "0001_first.sql")
        migrations = discover_migrations(tmp_path)
        assert [m.version for m in migrations] == ["0001_first", "0002_second"]

    def test_ignora_archivos_que_no_son_sql(self, tmp_path):
        _write_migration(tmp_path, "0001_first.sql")
        (tmp_path / "README.md").write_text("no soy una migración", encoding="utf-8")
        migrations = discover_migrations(tmp_path)
        assert len(migrations) == 1

    def test_checksum_es_estable(self, tmp_path):
        _write_migration(tmp_path, "0001_first.sql", "create table x();")
        a = discover_migrations(tmp_path)[0]
        b = discover_migrations(tmp_path)[0]
        assert a.checksum == b.checksum

    def test_checksum_cambia_con_el_contenido(self, tmp_path):
        _write_migration(tmp_path, "0001_first.sql", "create table x();")
        before = discover_migrations(tmp_path)[0].checksum
        _write_migration(tmp_path, "0001_first.sql", "create table y();")
        after = discover_migrations(tmp_path)[0].checksum
        assert before != after


class TestPlan:
    def test_todo_pendiente_si_nada_esta_aplicado(self):
        migrations = [Migration("0001_a", None, "sql", "chk_a"), Migration("0002_b", None, "sql", "chk_b")]
        assert [m.version for m in plan(migrations, {})] == ["0001_a", "0002_b"]

    def test_nada_pendiente_si_todo_coincide(self):
        migrations = [Migration("0001_a", None, "sql", "chk_a")]
        assert plan(migrations, {"0001_a": "chk_a"}) == []

    def test_solo_lo_nuevo_esta_pendiente(self):
        migrations = [
            Migration("0001_a", None, "sql", "chk_a"),
            Migration("0002_b", None, "sql", "chk_b"),
        ]
        pending = plan(migrations, {"0001_a": "chk_a"})
        assert [m.version for m in pending] == ["0002_b"]

    def test_checksum_distinto_levanta(self):
        """La garantía central del runner: una migración aplicada no se edita."""
        migrations = [Migration("0001_a", None, "sql nuevo", "chk_nuevo")]
        with pytest.raises(MigrationError, match="0001_a"):
            plan(migrations, {"0001_a": "chk_viejo"})


class TestApplyMigration:
    def test_aplica_y_confirma(self):
        executor = FakeExecutor()
        migration = Migration("0001_a", None, "create table x();", "chk_a")

        apply_migration(executor, migration)

        assert executor.migrations_table == {"0001_a": "chk_a"}
        assert executor.commits == 1
        assert executor.rollbacks == 0

    def test_falla_hace_rollback_y_no_registra_la_version(self):
        executor = FakeExecutor()
        executor.fail_on_substring = "create table x()"
        migration = Migration("0001_a", None, "create table x();", "chk_a")

        with pytest.raises(RuntimeError, match="boom"):
            apply_migration(executor, migration)

        assert executor.rollbacks == 1
        assert executor.commits == 0
        assert "0001_a" not in executor.migrations_table


class TestMigrate:
    def test_aplica_todo_lo_pendiente_en_orden(self, tmp_path):
        _write_migration(tmp_path, "0001_first.sql", "create table a();")
        _write_migration(tmp_path, "0002_second.sql", "create table b();")
        executor = FakeExecutor()

        applied_now = migrate(executor, tmp_path)

        assert applied_now == ["0001_first", "0002_second"]
        assert set(executor.migrations_table) == {"0001_first", "0002_second"}

    def test_es_idempotente(self, tmp_path):
        _write_migration(tmp_path, "0001_first.sql", "create table a();")
        executor = FakeExecutor()

        first_run = migrate(executor, tmp_path)
        second_run = migrate(executor, tmp_path)

        assert first_run == ["0001_first"]
        assert second_run == [], "correrlo de nuevo no debe reaplicar nada"

    def test_sin_migraciones_pendientes_no_hace_nada(self, tmp_path):
        executor = FakeExecutor()
        assert migrate(executor, tmp_path) == []
        assert executor.commits == 1  # el bootstrap de la tabla igual commitea


@pytest.mark.skipif(
    not os.getenv("SUPABASE_DB_URL"), reason="requiere una base de datos Postgres real"
)
class TestMigrateContraPostgresReal:
    """Solo corre si SUPABASE_DB_URL está seteada -- nunca en CI. Sirve para
    verificar a mano, antes de la primera corrida real, que el runner funciona
    contra el pooler de Supabase de verdad, no solo contra el doble en memoria."""

    def test_migrate_aplica_contra_supabase(self):
        import psycopg

        from gtm.store.dsn import get_dsn
        from gtm.store.migrate import PsycopgExecutor

        dsn = get_dsn()
        assert dsn is not None
        with psycopg.connect(dsn) as conn:
            executor = PsycopgExecutor(conn)
            migrate(executor)  # no debe levantar
