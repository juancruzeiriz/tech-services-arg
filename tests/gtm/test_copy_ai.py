"""Tests de gtm/factory/copy_ai.py.

Nunca llaman a la API real: `client` se reemplaza por un doble de prueba vía
monkeypatch sobre `copy_ai._client`. El contrato que importa verificar acá no
es "el modelo responde bien" (eso es responsabilidad de Anthropic), sino que
un fallo de cualquier tipo degrada a None sin excepción -- porque generate.py
depende de esa garantía para no romper una corrida completa por un timeout.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from gtm.factory import copy_ai
from gtm.factory.types import Language


def _fake_response(payload: dict[str, str]):
    text_block = SimpleNamespace(type="text", text=json.dumps(payload))
    return SimpleNamespace(content=[text_block])


class _FakeClient:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    class _Messages:
        def __init__(self, outer):
            self._outer = outer

        def create(self, **kwargs):
            self._outer.calls.append(kwargs)
            if self._outer._error:
                raise self._outer._error
            return self._outer._response

    @property
    def messages(self):
        return self._Messages(self)


_VALID_PAYLOAD = {slot: f"valor {slot}" for slot in copy_ai.SLOTS}


class TestSinApiKey:
    def test_devuelve_none_sin_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert copy_ai.generate_variant_copy("plumber", Language.EN) is None


class TestConApiKey:
    def test_devuelve_los_cinco_slots(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        fake = _FakeClient(response=_fake_response(_VALID_PAYLOAD))
        monkeypatch.setattr(copy_ai, "_client", lambda: fake)

        result = copy_ai.generate_variant_copy("plumber", Language.EN)

        assert result == _VALID_PAYLOAD
        assert set(result.keys()) == set(copy_ai.SLOTS)

    def test_usa_el_modelo_correcto(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        fake = _FakeClient(response=_fake_response(_VALID_PAYLOAD))
        monkeypatch.setattr(copy_ai, "_client", lambda: fake)

        copy_ai.generate_variant_copy("plumber", Language.EN)

        assert fake.calls[0]["model"] == "claude-opus-5"

    def test_la_firma_no_admite_datos_del_prospecto(self):
        """Regresión de diseño: `generate_variant_copy` solo puede recibir el
        oficio y el idioma -- no hay parámetro por el que un caller pudiera
        colar nombre, teléfono, dirección o reseñas de un negocio real."""
        import inspect

        params = set(inspect.signature(copy_ai.generate_variant_copy).parameters)
        assert params == {"vertical", "language"}

    def test_ningun_valor_real_de_un_prospecto_llega_al_modelo(self, monkeypatch, prospect):
        """Con un prospecto real de fixture disponible en el módulo de test,
        confirma que ninguno de sus datos aparece en lo que se le manda a la
        API -- solo puede llegar el string del oficio."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        fake = _FakeClient(response=_fake_response(_VALID_PAYLOAD))
        monkeypatch.setattr(copy_ai, "_client", lambda: fake)

        copy_ai.generate_variant_copy(prospect.vertical, Language.EN)

        full_request = json.dumps(fake.calls[0])
        assert prospect.name not in full_request
        assert prospect.phone not in full_request
        assert prospect.address not in full_request
        for review in prospect.top_reviews:
            assert review not in full_request

    def test_system_prompt_en_espanol_para_idioma_es(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        fake = _FakeClient(response=_fake_response(_VALID_PAYLOAD))
        monkeypatch.setattr(copy_ai, "_client", lambda: fake)

        copy_ai.generate_variant_copy("plumber", Language.ES)

        assert "español" in fake.calls[0]["system"]

    def test_error_de_la_api_degrada_a_none(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        fake = _FakeClient(error=RuntimeError("timeout"))
        monkeypatch.setattr(copy_ai, "_client", lambda: fake)

        assert copy_ai.generate_variant_copy("plumber", Language.EN) is None

    def test_json_incompleto_degrada_a_none(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        incomplete = dict.fromkeys(list(copy_ai.SLOTS)[:-1], "x")  # falta uno
        fake = _FakeClient(response=_fake_response(incomplete))
        monkeypatch.setattr(copy_ai, "_client", lambda: fake)

        assert copy_ai.generate_variant_copy("plumber", Language.EN) is None

    def test_json_con_slot_vacio_degrada_a_none(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        payload = {**_VALID_PAYLOAD, "cta_body": "   "}
        fake = _FakeClient(response=_fake_response(payload))
        monkeypatch.setattr(copy_ai, "_client", lambda: fake)

        assert copy_ai.generate_variant_copy("plumber", Language.EN) is None

    def test_json_invalido_degrada_a_none(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        text_block = SimpleNamespace(type="text", text="esto no es json")
        fake = _FakeClient(response=SimpleNamespace(content=[text_block]))
        monkeypatch.setattr(copy_ai, "_client", lambda: fake)

        assert copy_ai.generate_variant_copy("plumber", Language.EN) is None

    def test_recorta_espacios_del_resultado(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        padded = {slot: f"  {value}  " for slot, value in _VALID_PAYLOAD.items()}
        fake = _FakeClient(response=_fake_response(padded))
        monkeypatch.setattr(copy_ai, "_client", lambda: fake)

        result = copy_ai.generate_variant_copy("plumber", Language.EN)

        for value in result.values():
            assert value == value.strip()
