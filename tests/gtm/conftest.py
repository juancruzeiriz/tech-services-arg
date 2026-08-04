"""Fixtures compartidas del pipeline de prospección."""

from __future__ import annotations

import pytest

from gtm.factory.types import Demo, PainScore, Prospect, SenderIdentity


@pytest.fixture(autouse=True)
def _no_real_postgres(monkeypatch):
    """`gtm.store.pool.open_pool()` -- lo que corre el `lifespan` de cada
    `TestClient(create_app())` de este directorio -- lee `SUPABASE_DB_URL` vía
    `gtm.store.dsn.get_dsn()`. En esta máquina de desarrollo `.env.personal`
    tiene un DSN real de Supabase, y `monkeypatch.delenv("SUPABASE_DB_URL")`
    en un test individual NO alcanza: `dsn.py` cachea si ya cargó el archivo
    (`_loaded`) y, si no, vuelve a leerlo de disco la primera vez que algo
    llama a `get_dsn()` en el proceso, repoblando la env var que el test
    acaba de borrar.

    Sin este fixture, cualquier test que arme la app real (`test_ui_*.py`)
    abre una conexión real al pooler de Supabase y, si algún día un cambio de
    permisos o esquema hace que los `INSERT` que hoy fallan en silencio (ver
    `repo.upsert`, que atrapa la excepción y cae al outbox local) empiecen a
    tener éxito, el suite escribiría corridas simuladas en la base de datos
    de producción -- exactamente lo que la Fase 0.1 de este proyecto ya
    evitó una vez para `gtm/funnel.jsonl`.

    Se pisa `gtm.store.pool.get_dsn` (el nombre importado con `from ... import
    get_dsn`, no el módulo `gtm.store.dsn` en sí) para no tocar el smoke test
    real y deliberado de `test_store_migrate.py`, que solo corre bajo
    `skipif` cuando el desarrollador puso a propósito un DSN real."""
    from gtm.store import pool as pool_mod

    monkeypatch.setattr(pool_mod, "get_dsn", lambda: None)


@pytest.fixture
def prospect() -> Prospect:
    return Prospect(
        place_id="ChIJtest123",
        name="Ramirez Plumbing & Drain",
        vertical="plumber",
        metro="Tucson, AZ",
        phone="(520) 555-0142",
        website="http://ramirezplumbing.example",
        rating=4.8,
        review_count=214,
        address="1420 E Speedway Blvd, Tucson, AZ 85719",
        top_reviews=("Showed up in 40 minutes on a Sunday and fixed the leak.",),
    )


@pytest.fixture
def sender() -> SenderIdentity:
    return SenderIdentity(
        from_name="Juan Cruz Eiriz",
        from_email="juan@example.com",
        physical_address="Av. Siempre Viva 742, Cordoba, Argentina",
        unsubscribe_url="https://example.com/unsubscribe",
    )


@pytest.fixture
def live_demo() -> Demo:
    return Demo(
        place_id="ChIJtest123",
        slug="ramirez-plumbing-drain-abc123",
        html_path="/tmp/demo/index.html",
        url="https://demos.example.com/ramirez-plumbing-drain-abc123/",
    )


@pytest.fixture
def slow_site_score() -> PainScore:
    return PainScore(place_id="ChIJtest123", performance=23, seo=61, accessibility=70)
