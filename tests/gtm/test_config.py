"""Tests del preflight de configuración.

`check_config` es lo que le permite a la UI mostrar de una sola vez todo lo que
falta configurar antes de correr una etapa, en vez de que `require_env` explote a
mitad de una corrida ya empezada.
"""

from __future__ import annotations

import pytest

from gtm.factory import config


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    """Ninguno de estos tests debe depender de lo que haya en .env.personal."""
    for name in (
        "GOOGLE_PLACES_API_KEY",
        "GTM_FROM_NAME",
        "GTM_FROM_EMAIL",
        "GTM_PHYSICAL_ADDRESS",
        "GTM_UNSUBSCRIBE_URL",
        "GTM_DEMO_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


class TestCheckConfig:
    def test_todo_falta_por_defecto(self):
        missing = config.check_config()
        assert "GOOGLE_PLACES_API_KEY" in missing
        assert "GTM_FROM_NAME" in missing
        assert "GTM_FROM_EMAIL" in missing
        assert "GTM_PHYSICAL_ADDRESS" in missing
        assert "GTM_UNSUBSCRIBE_URL" in missing
        # No se pidió: no debe reclamarse.
        assert "GTM_DEMO_BASE_URL" not in missing

    def test_no_levanta_nunca(self):
        """A diferencia de require_env, nunca debe lanzar."""
        config.check_config(need_places=True, need_sender=True, need_demo_base_url=True)

    def test_nada_falta_si_todo_esta_seteado(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "abc")
        assert config.check_config(need_places=True, need_sender=False) == []

    def test_solo_pide_lo_que_se_le_pidio(self):
        missing = config.check_config(need_places=False, need_sender=False)
        assert missing == []

    def test_puede_pedir_demo_base_url(self):
        missing = config.check_config(
            need_places=False, need_sender=False, need_demo_base_url=True
        )
        assert missing == ["GTM_DEMO_BASE_URL"]

    def test_valor_solo_espacios_cuenta_como_faltante(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "   ")
        assert "GOOGLE_PLACES_API_KEY" in config.check_config(
            need_places=True, need_sender=False
        )


class TestReloadEnv:
    def test_relee_el_archivo_con_override(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env.personal"
        env_file.write_text("GTM_FROM_NAME=Primero\n", encoding="utf-8")
        monkeypatch.setattr(config, "ROOT", tmp_path)
        config.reload_env()
        assert config.optional_env("GTM_FROM_NAME") == "Primero"

        env_file.write_text("GTM_FROM_NAME=Segundo\n", encoding="utf-8")
        config.reload_env()
        assert config.optional_env("GTM_FROM_NAME") == "Segundo"
