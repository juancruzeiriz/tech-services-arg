"""Tests del preflight de configuración.

`check_config` es lo que le permite a la UI mostrar de una sola vez todo lo que
falta configurar antes de correr una etapa, en vez de que `require_env` explote a
mitad de una corrida ya empezada.
"""

from __future__ import annotations

import pytest

from gtm.factory import config
from gtm.send.types import SmtpSettings


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
        "GTM_SMTP_HOST",
        "GTM_SMTP_PORT",
        "GTM_SMTP_USER",
        "GTM_SMTP_PASSWORD",
        "GTM_BOUNCE_ADDRESS",
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

    def test_smtp_no_se_pide_por_defecto(self):
        missing = config.check_config(need_places=False, need_sender=False)
        assert "GTM_SMTP_HOST" not in missing

    def test_puede_pedir_smtp(self):
        missing = config.check_config(need_places=False, need_sender=False, need_smtp=True)
        assert set(missing) == {
            "GTM_SMTP_HOST", "GTM_SMTP_USER", "GTM_SMTP_PASSWORD", "GTM_BOUNCE_ADDRESS",
        }


class TestLoadSmtpSettings:
    def test_construye_settings_con_los_valores_del_entorno(self, monkeypatch):
        monkeypatch.setenv("GTM_SMTP_HOST", "smtp.zoho.com")
        monkeypatch.setenv("GTM_SMTP_PORT", "465")
        monkeypatch.setenv("GTM_SMTP_USER", "bounces@dominio.com")
        monkeypatch.setenv("GTM_SMTP_PASSWORD", "secreto")
        monkeypatch.setenv("GTM_BOUNCE_ADDRESS", "bounces@dominio.com")

        settings = config.load_smtp_settings()

        assert settings == SmtpSettings(
            host="smtp.zoho.com", port=465, username="bounces@dominio.com",
            password="secreto", bounce_address="bounces@dominio.com",
        )

    def test_puerto_por_defecto_465(self, monkeypatch):
        monkeypatch.setenv("GTM_SMTP_HOST", "smtp.zoho.com")
        monkeypatch.setenv("GTM_SMTP_USER", "u")
        monkeypatch.setenv("GTM_SMTP_PASSWORD", "p")
        monkeypatch.setenv("GTM_BOUNCE_ADDRESS", "b@dominio.com")

        assert config.load_smtp_settings().port == 465

    def test_sin_host_levanta_missing_config_error(self):
        with pytest.raises(config.MissingConfigError):
            config.load_smtp_settings()


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
