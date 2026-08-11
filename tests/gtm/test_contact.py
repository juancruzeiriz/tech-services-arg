"""Tests de la resolución de canal de contacto y de la cola de trabajo."""

from __future__ import annotations

import asyncio

import pytest

from gtm.factory import contact as contact_mod
from gtm.factory.contact import (
    FORM_MESSAGE_MAX_CHARS,
    build_call_script,
    build_form_message,
    find_contact_form,
    render_queue,
    resolve_all,
    resolve_contact,
)
from gtm.factory.types import ContactChannel, Demo, Language, PainScore, Prospect

AUTHOR = "Juan Cruz Eiriz"

# Centinela: `resolve_contact` solo chequea si el cliente es None; nunca lo usa
# cuando `find_contact_form` está reemplazado.
CLIENT = object()


def _form_finder(result: str | None):
    """Reemplazo async de `find_contact_form`."""

    async def _fake(_client, _website):
        return result

    return _fake


def _fetcher(result):
    """Reemplazo async de `fetch_text_async`."""

    async def _fake(_client, _url):
        return result

    return _fake


def _page(body: str) -> tuple[str, str]:
    return ("https://sonoran.example/", f"<html><body>{body}</body></html>")


def _prospect(**kwargs) -> Prospect:
    defaults = {
        "place_id": "p1",
        "name": "Sonoran Air Conditioning",
        "vertical": "hvac",
        "metro": "Tucson, AZ",
        "phone": "(520) 555-0148",
    }
    return Prospect(**{**defaults, **kwargs})


def _demo(place_id: str = "p1") -> Demo:
    return Demo(
        place_id=place_id,
        slug="sonoran-air-abc123",
        html_path="/tmp/x/index.html",
        url="https://demos.example.com/sonoran-air-abc123/",
    )


class TestAsignacionDeCanal:
    """El canal sigue al pain score: los que más duelen no tienen sitio, tienen teléfono."""

    async def test_sin_sitio_va_por_telefono(self):
        score = PainScore(place_id="p1", has_web_presence=False)
        plan = await resolve_contact(_prospect(website=None), score, CLIENT)
        assert plan.channel is ContactChannel.PHONE
        assert plan.target == "(520) 555-0148"
        assert plan.pain_score == 100

    async def test_solo_redes_va_por_telefono(self):
        prospect = _prospect(website="https://facebook.com/sonoran")
        plan = await resolve_contact(prospect, PainScore(place_id="p1", has_web_presence=False))
        assert plan.channel is ContactChannel.PHONE

    async def test_con_sitio_va_por_formulario(self, monkeypatch):
        monkeypatch.setattr(
            contact_mod, "find_contact_form", _form_finder("https://sonoran.example/contact")
        )
        plan = await resolve_contact(_prospect(website="https://sonoran.example"), None, CLIENT)
        assert plan.channel is ContactChannel.CONTACT_FORM
        assert plan.target == "https://sonoran.example/contact"

    async def test_sin_formulario_ubicable_cae_a_telefono(self, monkeypatch):
        monkeypatch.setattr(contact_mod, "find_contact_form", _form_finder(None))
        plan = await resolve_contact(_prospect(website="https://sonoran.example"), None, CLIENT)
        assert plan.channel is ContactChannel.PHONE

    async def test_sin_nada_es_unreachable(self, monkeypatch):
        monkeypatch.setattr(contact_mod, "find_contact_form", _form_finder(None))
        prospect = _prospect(website="https://sonoran.example", phone=None)
        plan = await resolve_contact(prospect, None, CLIENT)
        assert plan.channel is ContactChannel.UNREACHABLE
        assert not plan.is_actionable

    async def test_sin_sitio_ni_telefono_es_unreachable(self):
        plan = await resolve_contact(_prospect(website=None, phone=None))
        assert plan.channel is ContactChannel.UNREACHABLE

    async def test_sin_cliente_no_descarga_nada(self, monkeypatch):
        """Corrida seca: sin cliente, los que tienen sitio caen a teléfono."""

        async def _explode(_client, _website):
            pytest.fail("no debe descargar sin cliente")

        monkeypatch.setattr(contact_mod, "find_contact_form", _explode)
        plan = await resolve_contact(_prospect(website="https://sonoran.example"), None, None)
        assert plan.channel is ContactChannel.PHONE

    def test_no_existe_canal_de_email_scrapeado(self):
        """Recolectar direcciones automáticamente es aggravated violation de CAN-SPAM."""
        assert {c.value for c in ContactChannel} == {"phone", "contact_form", "unreachable"}


class TestFindContactForm:
    async def test_encuentra_link_de_contacto(self, monkeypatch):
        monkeypatch.setattr(
            contact_mod, "fetch_text_async", _fetcher(_page('<a href="/contact-us">Contact Us</a>'))
        )
        found = await find_contact_form(CLIENT, "https://sonoran.example")
        assert found == "https://sonoran.example/contact-us"

    async def test_prefiere_intencion_de_compra_sobre_contacto_generico(self, monkeypatch):
        monkeypatch.setattr(
            contact_mod,
            "fetch_text_async",
            _fetcher(
                _page('<a href="/contact">Contact</a><a href="/request-a-quote">Get a Quote</a>')
            ),
        )
        found = await find_contact_form(CLIENT, "https://sonoran.example")
        assert found == "https://sonoran.example/request-a-quote"

    async def test_ignora_links_externos(self, monkeypatch):
        monkeypatch.setattr(
            contact_mod,
            "fetch_text_async",
            _fetcher(_page('<a href="https://facebook.com/contact">Contact</a>')),
        )
        assert await find_contact_form(CLIENT, "https://sonoran.example") is None

    async def test_ignora_mailto_y_tel(self, monkeypatch):
        monkeypatch.setattr(
            contact_mod,
            "fetch_text_async",
            _fetcher(
                _page('<a href="mailto:x@y.com">Contact</a><a href="tel:5205550148">Call</a>')
            ),
        )
        assert await find_contact_form(CLIENT, "https://sonoran.example") is None

    async def test_sitio_de_una_pagina_con_form_embebido(self, monkeypatch):
        monkeypatch.setattr(
            contact_mod, "fetch_text_async", _fetcher(_page("<form><input name='email'></form>"))
        )
        found = await find_contact_form(CLIENT, "https://sonoran.example")
        assert found == "https://sonoran.example/"

    async def test_form_con_textarea_cuenta_como_contacto(self, monkeypatch):
        monkeypatch.setattr(
            contact_mod,
            "fetch_text_async",
            _fetcher(_page("<form><textarea name='msg'></textarea></form>")),
        )
        assert await find_contact_form(CLIENT, "https://sonoran.example") is not None

    async def test_un_buscador_no_es_formulario_de_contacto(self, monkeypatch):
        """Casi todo sitio tiene un `<form>` de búsqueda; mandar el pitch por ahí no
        llega a nadie. Detectado probando contra HTML real."""
        monkeypatch.setattr(
            contact_mod,
            "fetch_text_async",
            _fetcher(_page("<form role='search'><input type='text' name='q'></form>")),
        )
        assert await find_contact_form(CLIENT, "https://sonoran.example") is None

    async def test_form_con_input_type_email_cuenta(self, monkeypatch):
        monkeypatch.setattr(
            contact_mod,
            "fetch_text_async",
            _fetcher(_page("<form><input type='email' name='addr'></form>")),
        )
        assert await find_contact_form(CLIENT, "https://sonoran.example") is not None

    async def test_sitio_caido_devuelve_none(self, monkeypatch):
        monkeypatch.setattr(contact_mod, "fetch_text_async", _fetcher(None))
        assert await find_contact_form(CLIENT, "https://down.example") is None


class TestMensajes:
    @pytest.mark.parametrize("language", list(Language))
    def test_mensaje_de_formulario_entra_en_el_limite(self, language):
        """Corre para los dos idiomas: el español suele ser ~15-20% más largo, así
        que el límite se pisa antes ahí, no en inglés."""
        message = build_form_message(_prospect(), _demo(), AUTHOR, language=language)
        assert len(message) <= FORM_MESSAGE_MAX_CHARS

    def test_mensaje_de_formulario_lleva_el_link(self):
        message = build_form_message(_prospect(), _demo(), AUTHOR)
        assert _demo().url in message
        assert "$950" in message

    def test_mensaje_de_formulario_no_lleva_footer_de_email(self):
        """Un formulario no admite dirección postal ni link de baja: sería ruido."""
        assert "unsubscribe" not in build_form_message(_prospect(), _demo(), AUTHOR).lower()

    def test_demo_sin_url_es_rechazada(self):
        mockup = Demo(place_id="p1", slug="x", html_path="/tmp/x/index.html")
        with pytest.raises(ValueError, match="URL pública"):
            build_form_message(_prospect(), mockup, AUTHOR)

    def test_guion_de_llamada_pide_permiso_antes_del_sms(self):
        """El SMS solo es legítimo como respuesta a una llamada que vos iniciaste."""
        script = build_call_script(_prospect(), _demo())
        assert "Can I text you the link" in script
        assert _demo().url in script

    def test_guion_de_llamada_en_ingles_no_mezcla_idiomas(self):
        """Regresión: la nota entre corchetes que le recuerda al vendedor mandar
        el SMS ("[Enviar SMS: ...]") estaba hardcodeada en español en las DOS
        ramas de build_call_script -- incluida la rama en inglés, que la leía
        en voz alta como "[Send SMS: ...]" debería decir. Encontrado leyendo el
        guion en voz alta (Día 7 del plan diario), no por inspección de código."""
        script = build_call_script(_prospect(), _demo())
        assert "Enviar" not in script
        assert "[Send SMS:" in script


class TestMensajesEnEspanol:
    def test_mensaje_de_formulario_lleva_el_link_y_precio(self):
        message = build_form_message(_prospect(), _demo(), AUTHOR, language=Language.ES)
        assert _demo().url in message
        assert "USD 950" in message

    def test_mensaje_de_formulario_no_lleva_footer_de_email(self):
        body = build_form_message(_prospect(), _demo(), AUTHOR, language=Language.ES).lower()
        assert "unsubscribe" not in body

    def test_guion_de_llamada_pide_permiso_antes_del_sms(self):
        script = build_call_script(_prospect(), _demo(), language=Language.ES)
        assert "¿Te puedo mandar el link" in script
        assert _demo().url in script

    def test_guion_de_llamada_usa_la_ciudad(self):
        script = build_call_script(_prospect(metro="Miami, FL"), _demo(), language=Language.ES)
        assert "Miami" in script

    def test_no_mezcla_idiomas(self):
        """El mensaje en español no debe traer texto en inglés que delate que se
        armó pegando dos plantillas."""
        message = build_form_message(_prospect(), _demo(), AUTHOR, language=Language.ES)
        assert "sample" not in message.lower()
        assert " the " not in message.lower()


class TestPluralDelRubro:
    """Regresión: el guion decía "I build websites for hvacs", que delata la plantilla
    en la primera línea del mensaje."""

    def test_hvac_usa_la_etiqueta_legible(self):
        script = build_call_script(_prospect(vertical="hvac"), _demo())
        assert "HVAC contractors" in script
        assert "hvacs" not in script

    def test_plumber_pluraliza_normal(self):
        assert "plumbers" in build_form_message(_prospect(vertical="plumber"), _demo(), AUTHOR)

    def test_roofer_usa_la_etiqueta_no_el_slug(self):
        script = build_call_script(_prospect(vertical="roofer"), _demo())
        assert "roofing contractors" in script
        assert "roofers" not in script

    def test_hvac_en_espanol_usa_el_plural_curado(self):
        script = build_call_script(_prospect(vertical="hvac"), _demo(), language=Language.ES)
        assert "técnicos de aire acondicionado" in script

    def test_roofer_en_espanol_usa_el_plural_curado(self):
        assert "techistas" in build_form_message(
            _prospect(vertical="roofer"), _demo(), AUTHOR, language=Language.ES
        )


class TestColaDeTrabajo:
    async def test_ordena_por_dolor_descendente(self):
        prospects = [
            _prospect(place_id="bajo", name="Low Pain", website=None),
            _prospect(place_id="alto", name="High Pain", website=None),
        ]
        scores = {
            "bajo": PainScore(place_id="bajo", performance=60, seo=80),
            "alto": PainScore(place_id="alto", has_web_presence=False),
        }
        plans = await resolve_all(prospects, scores, probe_site=False)
        assert [p.place_id for p in plans] == ["alto", "bajo"]

    async def test_separa_llamadas_de_formularios(self, monkeypatch):
        monkeypatch.setattr(
            contact_mod, "find_contact_form", _form_finder("https://x.example/contact")
        )
        por_telefono = _prospect(place_id="tel", name="No Website Co", website=None)
        por_form = _prospect(place_id="form", name="Has Site Co", website="https://x.example")

        plans = await resolve_all(
            [por_telefono, por_form],
            {
                "tel": PainScore(place_id="tel", has_web_presence=False),
                "form": PainScore(place_id="form", performance=20),
            },
        )
        queue = render_queue(
            plans,
            {"tel": por_telefono, "form": por_form},
            {"tel": _demo("tel"), "form": _demo("form")},
            AUTHOR,
        )

        assert "## Llamadas (1)" in queue
        assert "## Formularios (1)" in queue
        assert "No Website Co" in queue
        assert "Has Site Co" in queue

    async def test_lista_los_descartados_con_su_motivo(self):
        muerto = _prospect(place_id="dead", name="Unreachable Co", website=None, phone=None)
        plans = await resolve_all([muerto], {}, probe_site=False)
        queue = render_queue(plans, {"dead": muerto}, {}, AUTHOR)

        assert "## Descartados (1)" in queue
        assert "Unreachable Co" in queue

    async def test_prospecto_sin_demo_publicada_no_rompe_la_cola(self):
        prospect = _prospect(website=None)
        plans = await resolve_all([prospect], {}, probe_site=False)
        queue = render_queue(plans, {"p1": prospect}, {}, AUTHOR)

        assert "(sin demo publicada)" in queue


class TestConcurrencia:
    async def test_un_sitio_lento_no_bloquea_a_los_demas(self, monkeypatch):
        """En serie esto tardaría la suma; en paralelo, el máximo."""
        started: list[str] = []

        async def _slow(_client, website):
            started.append(website)
            await asyncio.sleep(0.05)
            return f"{website}/contact"

        monkeypatch.setattr(contact_mod, "find_contact_form", _slow)

        prospects = [
            _prospect(place_id=f"p{i}", name=f"Co {i}", website=f"https://s{i}.example")
            for i in range(6)
        ]
        scores = {f"p{i}": PainScore(place_id=f"p{i}", performance=10 * i) for i in range(6)}

        loop = asyncio.get_running_loop()
        start = loop.time()
        plans = await resolve_all(prospects, scores, concurrency=6)
        elapsed = loop.time() - start

        assert len(started) == 6
        assert elapsed < 0.20, f"parece serial: 6 sitios de 50ms tardaron {elapsed:.2f}s"
        assert all(p.channel is ContactChannel.CONTACT_FORM for p in plans)

    async def test_el_orden_no_depende_de_quien_termina_antes(self, monkeypatch):
        async def _variable(_client, website):
            # El de mayor dolor es el que más tarda.
            await asyncio.sleep(0.04 if "slow" in website else 0.0)
            return f"{website}/contact"

        monkeypatch.setattr(contact_mod, "find_contact_form", _variable)

        prospects = [
            _prospect(place_id="fast", name="Fast Co", website="https://fast.example"),
            _prospect(place_id="slow", name="Slow Co", website="https://slow.example"),
        ]
        scores = {
            "fast": PainScore(place_id="fast", performance=90),
            "slow": PainScore(place_id="slow", performance=5),
        }

        plans = await resolve_all(prospects, scores, concurrency=4)

        # Ordenado por dolor, no por quién terminó antes.
        assert [p.place_id for p in plans] == ["slow", "fast"]

    async def test_respeta_el_techo_de_concurrencia(self, monkeypatch):
        """Soltar 50 requests de golpe contra PageSpeed garantiza 429s."""
        activos = 0
        pico = 0

        async def _tracked(_client, website):
            nonlocal activos, pico
            activos += 1
            pico = max(pico, activos)
            await asyncio.sleep(0.01)
            activos -= 1
            return f"{website}/contact"

        monkeypatch.setattr(contact_mod, "find_contact_form", _tracked)

        prospects = [
            _prospect(place_id=f"p{i}", name=f"Co {i}", website=f"https://s{i}.example")
            for i in range(12)
        ]

        await resolve_all(prospects, {}, concurrency=3)

        assert pico <= 3, f"el semáforo no contuvo: pico de {pico} simultáneos"

    async def test_on_item_se_llama_una_vez_por_prospecto(self, monkeypatch):
        monkeypatch.setattr(contact_mod, "find_contact_form", _form_finder("https://s0.example/contact"))

        prospects = [
            _prospect(place_id=f"p{i}", name=f"Co {i}", website=f"https://s{i}.example")
            for i in range(5)
        ]
        seen: list[str] = []
        await resolve_all(prospects, {}, concurrency=5, on_item=seen.append)

        assert sorted(seen) == [p.place_id for p in prospects]

    async def test_on_item_se_llama_sin_probe(self):
        """También cuando no se descargan sitios (--no-probe): el contador de
        progreso de la UI no debe depender del canal que se termine usando."""
        prospects = [
            _prospect(place_id=f"p{i}", name=f"Co {i}", website=f"https://s{i}.example")
            for i in range(3)
        ]
        seen: list[str] = []
        await resolve_all(prospects, {}, probe_site=False, concurrency=3, on_item=seen.append)

        assert sorted(seen) == [p.place_id for p in prospects]
