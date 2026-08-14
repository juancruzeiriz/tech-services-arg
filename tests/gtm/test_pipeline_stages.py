"""Tests de discover, score, deploy y del transporte HTTP."""

from __future__ import annotations

import httpx
import pytest

from gtm.factory import deploy as deploy_mod
from gtm.factory import discover as discover_mod
from gtm.factory import net
from gtm.factory import score as score_mod
from gtm.factory import verify as verify_mod
from gtm.factory.types import (
    Demo,
    DeploymentError,
    DigitalTrace,
    Language,
    PainScore,
    Prospect,
    WebPresence,
)


def _place(
    place_id: str,
    name: str,
    *,
    reviews: int = 200,
    rating: float = 4.7,
    phone: str | None = "(520) 555-0142",
    website: str | None = None,
) -> dict:
    payload: dict = {
        "id": place_id,
        "displayName": {"text": name},
        "userRatingCount": reviews,
        "rating": rating,
        "formattedAddress": "1 Main St, Tucson, AZ",
    }
    if phone:
        payload["nationalPhoneNumber"] = phone
    if website:
        payload["websiteUri"] = website
    return payload


class TestDiscover:
    def test_filtra_por_resenas_rating_y_telefono(self, monkeypatch):
        page = {
            "places": [
                _place("ok", "Good Plumbing"),
                _place("few_reviews", "New Plumbing", reviews=3),
                _place("low_rating", "Bad Plumbing", rating=2.1),
                _place("no_phone", "Unreachable Plumbing", phone=None),
            ]
        }
        monkeypatch.setattr(discover_mod, "_search_page", lambda *a, **k: page)

        result = discover_mod.discover("plumber", "Tucson, AZ", limit=10, api_key="k")

        assert [p.place_id for p in result] == ["ok"]

    def test_prioriza_los_que_no_tienen_sitio(self, monkeypatch):
        page = {
            "places": [
                _place("has_site", "Has Site", website="https://hassite.example"),
                _place("social", "Social Only", website="https://facebook.com/x"),
                _place("none", "No Site"),
            ]
        }
        monkeypatch.setattr(discover_mod, "_search_page", lambda *a, **k: page)

        result = discover_mod.discover("plumber", "Tucson, AZ", limit=10, api_key="k")

        assert [p.place_id for p in result] == ["none", "social", "has_site"]

    def test_respeta_el_limite(self, monkeypatch):
        page = {"places": [_place(f"p{i}", f"Plumbing {i}") for i in range(10)]}
        monkeypatch.setattr(discover_mod, "_search_page", lambda *a, **k: page)

        result = discover_mod.discover("plumber", "Tucson, AZ", limit=3, api_key="k")

        assert len(result) == 3

    def test_deduplica_entre_paginas(self, monkeypatch):
        page = {"places": [_place("dupe", "Same Plumbing")], "nextPageToken": "t"}
        monkeypatch.setattr(discover_mod, "_search_page", lambda *a, **k: page)

        result = discover_mod.discover("plumber", "Tucson, AZ", limit=10, api_key="k")

        assert len(result) == 1

    def test_place_sin_nombre_se_ignora(self, monkeypatch):
        page = {"places": [{"id": "x", "userRatingCount": 300}]}
        monkeypatch.setattr(discover_mod, "_search_page", lambda *a, **k: page)

        assert discover_mod.discover("plumber", "Tucson, AZ", api_key="k") == []


class TestScore:
    """`score_prospect` recibe el cliente del lote: se comparte en toda la corrida."""

    CLIENT = object()

    @pytest.fixture(autouse=True)
    def _sin_senales_de_red_extra(self, monkeypatch):
        """`score_prospect` ahora también busca HTML (forensics), CrUX y
        Wayback en paralelo con PageSpeed. Sin esto, cualquier test que
        llegue a "el sitio existe y se puntúa" haría 3 requests reales
        contra dominios que no resuelven (`self.CLIENT` ni siquiera es un
        httpx.AsyncClient real) — lento, de red, y no es lo que este test
        mide. Los tests que sí quieren ejercitar esas señales sobreescriben
        el mock puntual después de pedir este fixture."""

        async def _sin_html(*_args, **_kwargs):
            return None

        async def _sin_crux(*_args, **_kwargs):
            return None

        async def _sin_archive(*_args, **_kwargs):
            return None

        monkeypatch.setattr(score_mod, "fetch_text_async", _sin_html)
        monkeypatch.setattr(score_mod, "_fetch_crux_safe", _sin_crux)
        monkeypatch.setattr(score_mod, "last_meaningful_change", _sin_archive)

    async def test_sin_sitio_no_llama_a_la_api(self, monkeypatch):
        async def _explode(*_args, **_kwargs):
            pytest.fail("no debe llamarse")

        monkeypatch.setattr(score_mod, "score_website", _explode)
        prospect = Prospect(place_id="p", name="X", vertical="plumber", metro="Tucson, AZ")

        result = await score_mod.score_prospect(self.CLIENT, prospect)

        assert result.score == 100
        assert not result.has_web_presence

    async def test_solo_redes_cuenta_como_sin_presencia_propia(self):
        prospect = Prospect(
            place_id="p",
            name="X",
            vertical="plumber",
            metro="Tucson, AZ",
            website="https://facebook.com/x",
        )
        result = await score_mod.score_prospect(self.CLIENT, prospect)

        assert prospect.web_presence is WebPresence.SOCIAL_ONLY
        assert result.score == 100
        assert "redes" in result.notes[0]

    async def test_verify_encuentra_dominio_propio_y_se_puntua_de_verdad(self, monkeypatch):
        """El caso central de la Capa 2: Maps dice `NONE`, pero
        `verify.verify_absence` corrobora un dominio propio -- el prospecto
        tiene que salir medido, no con el dolor 100 automático."""

        async def _found(*_args, **_kwargs):
            return verify_mod.VerifyResult(DigitalTrace.OWN_DOMAIN, url="https://legacytree.com")

        async def _lab(*_args, **_kwargs):
            return PainScore(place_id="", performance=40, seo=60, accessibility=70)

        monkeypatch.setattr(verify_mod, "verify_absence", _found)
        monkeypatch.setattr(score_mod, "score_website", _lab)

        prospect = Prospect(place_id="p", name="Legacy Tree Company", vertical="tree_service", metro="Albuquerque, NM")

        result = await score_mod.score_prospect(self.CLIENT, prospect)

        assert result.has_web_presence is True
        assert result.digital_trace is DigitalTrace.OWN_DOMAIN
        assert result.verified_domain == "https://legacytree.com"
        assert result.performance == 40
        assert result.score != 100

    async def test_verify_directory_only_mantiene_dolor_maximo_pero_guarda_el_trace(self, monkeypatch):
        async def _directory(*_args, **_kwargs):
            return verify_mod.VerifyResult(DigitalTrace.DIRECTORY_ONLY)

        async def _explode(*_args, **_kwargs):
            pytest.fail("no debe llamarse: no hay dominio propio que medir")

        monkeypatch.setattr(verify_mod, "verify_absence", _directory)
        monkeypatch.setattr(score_mod, "score_website", _explode)

        prospect = Prospect(place_id="p", name="X", vertical="plumber", metro="Tucson, AZ")

        result = await score_mod.score_prospect(self.CLIENT, prospect)

        assert result.score == 100
        assert not result.has_web_presence
        assert result.digital_trace is DigitalTrace.DIRECTORY_ONLY

    async def test_search_api_key_y_cx_se_pasan_a_verify(self, monkeypatch):
        captured: dict = {}

        async def _capture(_client, _prospect, *, search_api_key=None, search_cx=None):
            captured["search_api_key"] = search_api_key
            captured["search_cx"] = search_cx
            return verify_mod.VerifyResult(DigitalTrace.UNVERIFIED)

        monkeypatch.setattr(verify_mod, "verify_absence", _capture)

        prospect = Prospect(place_id="p", name="X", vertical="plumber", metro="Tucson, AZ")
        await score_mod.score_prospect(
            self.CLIENT, prospect, search_api_key="key123", search_cx="cx456"
        )

        assert captured == {"search_api_key": "key123", "search_cx": "cx456"}

    async def test_verify_absence_enabled_false_no_llama_a_verify(self, monkeypatch):
        async def _explode(*_args, **_kwargs):
            pytest.fail("no debe llamarse con verify_absence_enabled=False")

        monkeypatch.setattr(verify_mod, "verify_absence", _explode)

        prospect = Prospect(place_id="p", name="X", vertical="plumber", metro="Tucson, AZ")
        result = await score_mod.score_prospect(
            self.CLIENT, prospect, verify_absence_enabled=False
        )

        assert result.digital_trace is DigitalTrace.UNVERIFIED
        assert result.score == 100

    async def test_sitio_caido_no_se_puntua_con_lighthouse(self, monkeypatch):
        async def _down(*_args, **_kwargs):
            return False

        async def _explode(*_args, **_kwargs):
            pytest.fail("no debe llamarse")

        monkeypatch.setattr(score_mod, "probe_url_async", _down)
        monkeypatch.setattr(score_mod, "score_website", _explode)
        prospect = Prospect(
            place_id="p",
            name="X",
            vertical="plumber",
            metro="Tucson, AZ",
            website="https://down.example",
        )

        result = await score_mod.score_prospect(self.CLIENT, prospect)

        assert not result.reachable
        assert result.score == 95

    async def test_sitio_lento_genera_nota_verificable(self, monkeypatch):
        async def _up(*_args, **_kwargs):
            return True

        async def _slow(*_args, **_kwargs):
            return PainScore(place_id="", performance=18, seo=55, accessibility=80)

        monkeypatch.setattr(score_mod, "probe_url_async", _up)
        monkeypatch.setattr(score_mod, "score_website", _slow)
        prospect = Prospect(
            place_id="p",
            name="X",
            vertical="plumber",
            metro="Tucson, AZ",
            website="https://slow.example",
        )

        result = await score_mod.score_prospect(self.CLIENT, prospect)

        assert result.performance == 18
        assert any("18/100" in note for note in result.notes)

    async def test_score_prospect_junta_lab_campo_y_forense(self, monkeypatch):
        """Las tres fuentes -- Lighthouse, CrUX y forensics -- terminan en el
        mismo PainScore, cada una en su lugar."""
        from datetime import date

        from gtm.factory.crux import CruxMetrics

        async def _up(*_args, **_kwargs):
            return True

        async def _lab(*_args, **_kwargs):
            return PainScore(place_id="", performance=90, seo=90, accessibility=90, mobile_friendly=True)

        async def _html(_client, _url):
            return (_url, '<html><table bgcolor="#fff"><tr><td>x</td></tr></table></html>')

        async def _crux(*_args, **_kwargs):
            return CruxMetrics(lcp_ms=6200, inp_ms=100, cls=0.05)

        async def _archive(*_args, **_kwargs):
            return date(2016, 3, 12)

        monkeypatch.setattr(score_mod, "probe_url_async", _up)
        monkeypatch.setattr(score_mod, "score_website", _lab)
        monkeypatch.setattr(score_mod, "fetch_text_async", _html)
        monkeypatch.setattr(score_mod, "_fetch_crux_safe", _crux)
        monkeypatch.setattr(score_mod, "last_meaningful_change", _archive)

        prospect = Prospect(
            place_id="p", name="X", vertical="plumber", metro="Tucson, AZ",
            website="https://viejo.example",
        )

        result = await score_mod.score_prospect(self.CLIENT, prospect, crux_api_key="k")

        assert result.crux_lcp_ms == 6200
        assert result.has_field_data is True
        assert result.last_changed == date(2016, 3, 12)
        codes = {f.code for f in result.findings}
        assert "crux_lcp_poor" in codes
        assert "table_layout" in codes

    async def test_si_crux_no_tiene_datos_degrada_a_laboratorio(self, monkeypatch):
        """Un 404 de CrUX (ya resuelto a None por _fetch_crux_safe) es normal
        en negocios chicos; no puede tumbar la etapa ni perder el dato de
        laboratorio que sí se consiguió."""

        async def _up(*_args, **_kwargs):
            return True

        async def _lab(*_args, **_kwargs):
            return PainScore(place_id="", performance=40, seo=60)

        async def _sin_crux(*_args, **_kwargs):
            return None

        monkeypatch.setattr(score_mod, "probe_url_async", _up)
        monkeypatch.setattr(score_mod, "score_website", _lab)
        monkeypatch.setattr(score_mod, "_fetch_crux_safe", _sin_crux)

        prospect = Prospect(
            place_id="p", name="X", vertical="plumber", metro="Tucson, AZ",
            website="https://chico.example",
        )

        result = await score_mod.score_prospect(self.CLIENT, prospect, crux_api_key="k")

        assert result.has_field_data is False
        assert result.crux_lcp_ms is None
        assert result.performance == 40

    async def test_un_fallo_individual_no_aborta_la_corrida(self, monkeypatch):
        """gather propagaría la primera excepción y perderíamos los que sí se puntuaron."""

        async def _up(*_args, **_kwargs):
            return True

        async def _unanalyzable(*_args, **_kwargs):
            return None

        monkeypatch.setattr(score_mod, "probe_url_async", _up)
        monkeypatch.setattr(score_mod, "score_website", _unanalyzable)

        prospects = [
            Prospect(
                place_id="broken",
                name="Broken",
                vertical="plumber",
                metro="Tucson, AZ",
                website="https://x.example",
            ),
            Prospect(place_id="fine", name="Fine", vertical="plumber", metro="Tucson, AZ"),
        ]

        results = await score_mod.score_all(prospects)

        assert [r.place_id for r in results] == ["fine"]

    async def test_score_all_reenvia_los_parametros_de_verificacion(self, monkeypatch):
        """`score_all` es el punto de entrada real (CLI y UI): si no reenvía
        `search_api_key`/`search_cx`/`verify_absence_enabled` a
        `score_prospect`, la Capa 2 queda inalcanzable desde afuera."""
        captured: list[dict] = []

        async def _capture(_client, prospect, _api_key=None, *, crux_api_key=None, **kwargs):
            captured.append(kwargs)
            return PainScore(place_id=prospect.place_id)

        monkeypatch.setattr(score_mod, "score_prospect", _capture)

        prospects = [Prospect(place_id="p", name="X", vertical="plumber", metro="Tucson, AZ")]
        await score_mod.score_all(
            prospects,
            search_api_key="key123",
            search_cx="cx456",
            verify_absence_enabled=False,
        )

        assert captured == [
            {"search_api_key": "key123", "search_cx": "cx456", "verify_absence_enabled": False}
        ]

    async def test_puntua_el_lote_en_paralelo(self, monkeypatch):
        """En serie, 6 sitios de 50ms tardarían 300ms."""
        import asyncio

        async def _up(*_args, **_kwargs):
            return True

        async def _slow(*_args, **_kwargs):
            await asyncio.sleep(0.05)
            return PainScore(place_id="", performance=30, seo=60)

        monkeypatch.setattr(score_mod, "probe_url_async", _up)
        monkeypatch.setattr(score_mod, "score_website", _slow)

        prospects = [
            Prospect(
                place_id=f"p{i}",
                name=f"Co {i}",
                vertical="plumber",
                metro="Tucson, AZ",
                website=f"https://s{i}.example",
            )
            for i in range(6)
        ]

        loop = asyncio.get_running_loop()
        start = loop.time()
        results = await score_mod.score_all(prospects, concurrency=6)
        elapsed = loop.time() - start

        assert len(results) == 6
        assert elapsed < 0.20, f"parece serial: tardó {elapsed:.2f}s"

    def test_category_score_convierte_a_escala_100(self):
        lighthouse = {"categories": {"performance": {"score": 0.42}}}
        assert score_mod._category_score(lighthouse, "performance") == 42

    async def test_on_item_se_llama_una_vez_por_prospecto(self, monkeypatch):
        """El callback de progreso: sin él, la UI no tiene forma de mostrar avance
        durante los 30-60s por sitio que tarda esta etapa."""

        async def _up(*_args, **_kwargs):
            return True

        async def _fast(*_args, **_kwargs):
            return PainScore(place_id="", performance=50, seo=50)

        monkeypatch.setattr(score_mod, "probe_url_async", _up)
        monkeypatch.setattr(score_mod, "score_website", _fast)

        prospects = [
            Prospect(
                place_id=f"p{i}", name=f"Co {i}", vertical="plumber", metro="Tucson, AZ",
                website=f"https://s{i}.example",
            )
            for i in range(4)
        ]
        seen: list[str] = []
        await score_mod.score_all(prospects, on_item=seen.append)

        assert sorted(seen) == [p.place_id for p in prospects]

    async def test_on_item_se_llama_tambien_si_el_prospecto_falla(self, monkeypatch):
        """Un prospecto que no se pudo puntuar también cuenta como "terminado"
        para la barra de progreso — si no, el contador se queda pegado."""

        async def _up(*_args, **_kwargs):
            return True

        async def _unanalyzable(*_args, **_kwargs):
            return None

        monkeypatch.setattr(score_mod, "probe_url_async", _up)
        monkeypatch.setattr(score_mod, "score_website", _unanalyzable)

        prospect = Prospect(
            place_id="broken", name="Broken", vertical="plumber", metro="Tucson, AZ",
            website="https://x.example",
        )
        seen: list[str] = []
        await score_mod.score_all([prospect], on_item=seen.append)

        assert seen == ["broken"]

    def test_category_score_ausente_es_none(self):
        assert score_mod._category_score({"categories": {}}, "seo") is None


class TestDeploy:
    def test_dry_run_no_escribe_nada(self, tmp_path):
        source = tmp_path / "src" / "index.html"
        source.parent.mkdir(parents=True)
        source.write_text("<html></html>", encoding="utf-8")
        public = tmp_path / "public"

        result = deploy_mod.deploy(
            [Demo(place_id="p", slug="joe-plumbing-abc123", html_path=str(source))],
            "https://demos.example.com",
            dry_run=True,
            public_dir=public,
        )

        assert not public.exists()
        assert result[0].url == "https://demos.example.com/joe-plumbing-abc123/"
        assert result[0].deployed_at is None

    def test_publica_y_asigna_url_unica(self, tmp_path):
        public = tmp_path / "public"
        demos = []
        for slug in ("a-abc123", "b-def456"):
            source = tmp_path / slug / "index.html"
            source.parent.mkdir(parents=True)
            source.write_text(f"<html>{slug}</html>", encoding="utf-8")
            demos.append(Demo(place_id=slug, slug=slug, html_path=str(source)))

        result = deploy_mod.deploy(demos, "https://demos.example.com/", public_dir=public)

        assert len({d.url for d in result}) == 2
        assert (public / "a-abc123" / "index.html").exists()
        assert (public / "index.html").exists()
        assert all(d.is_live for d in result)

    def test_el_indice_no_es_indexable(self, tmp_path):
        public = tmp_path / "public"
        source = tmp_path / "s" / "index.html"
        source.parent.mkdir(parents=True)
        source.write_text("<html></html>", encoding="utf-8")

        deploy_mod.deploy(
            [Demo(place_id="p", slug="s-abc123", html_path=str(source))],
            "https://demos.example.com",
            public_dir=public,
        )

        assert "noindex" in (public / "index.html").read_text(encoding="utf-8")

    def test_html_faltante_falla_explicito(self, tmp_path):
        with pytest.raises(DeploymentError, match="generate"):
            deploy_mod.deploy(
                [Demo(place_id="p", slug="s", html_path=str(tmp_path / "nope.html"))],
                "https://demos.example.com",
                public_dir=tmp_path / "public",
            )

    def test_preserva_el_idioma_detectado(self, tmp_path):
        """Regresión: `deploy()` reconstruía `Demo` campo por campo y perdía
        cualquier campo que no copiara a mano -- `language` (detectado por
        prospecto, ver gtm/factory/lang.py) se perdía en el camino generate
        -> deploy, y todas las demos volvían a salir en inglés sin importar
        lo que `generate()` hubiera detectado."""
        source = tmp_path / "src" / "index.html"
        source.parent.mkdir(parents=True)
        source.write_text("<html></html>", encoding="utf-8")

        result = deploy_mod.deploy(
            [
                Demo(
                    place_id="p",
                    slug="jardineria-lopez-abc123",
                    html_path=str(source),
                    language=Language.ES,
                )
            ],
            "https://demos.example.com",
            dry_run=True,
            public_dir=tmp_path / "public",
        )

        assert result[0].language is Language.ES

    def test_copia_las_functions_desde_sus_fuentes_versionadas(self, tmp_path, monkeypatch):
        """Regresión: `gtm/public/functions/` no está en git (gtm/public/ entero
        está fuera de git) y hasta esta sesión nada lo armaba -- existía solo porque
        se había copiado a mano una vez. Un clon nuevo del repo perdía el unsubscribe
        y el tracking en silencio. `deploy()` ahora los junta desde las fuentes que sí
        están versionadas en cada corrida."""
        fake_v = tmp_path / "src" / "v_token.js"
        fake_v.parent.mkdir(parents=True)
        fake_v.write_text("export function onRequestGet() {}", encoding="utf-8")
        fake_unsub = tmp_path / "src" / "unsubscribe.js"
        fake_unsub.write_text("export function onRequestPost() {}", encoding="utf-8")
        monkeypatch.setattr(
            deploy_mod,
            "_FUNCTIONS_SOURCES",
            ((fake_v, "v/[token].js"), (fake_unsub, "api/unsubscribe.js")),
        )

        source = tmp_path / "demo" / "index.html"
        source.parent.mkdir(parents=True)
        source.write_text("<html></html>", encoding="utf-8")
        public = tmp_path / "public"

        deploy_mod.deploy(
            [Demo(place_id="p", slug="s-abc123", html_path=str(source))],
            "https://demos.example.com",
            public_dir=public,
        )

        assert (public / "functions" / "v" / "[token].js").read_text(encoding="utf-8") == (
            "export function onRequestGet() {}"
        )
        assert (public / "functions" / "api" / "unsubscribe.js").exists()

    def test_fuente_de_function_faltante_no_rompe_el_deploy(self, tmp_path, monkeypatch, caplog):
        """Si falta una fuente (repo movido, archivo borrado), el deploy de las
        demos tiene que seguir -- perder el tracking es peor, pero perder TODA la
        publicación por eso sería peor todavía."""
        monkeypatch.setattr(
            deploy_mod, "_FUNCTIONS_SOURCES", ((tmp_path / "no-existe.js", "v/[token].js"),)
        )

        source = tmp_path / "demo" / "index.html"
        source.parent.mkdir(parents=True)
        source.write_text("<html></html>", encoding="utf-8")
        public = tmp_path / "public"

        deploy_mod.deploy(
            [Demo(place_id="p", slug="s-abc123", html_path=str(source))],
            "https://demos.example.com",
            public_dir=public,
        )

        assert (public / "s-abc123" / "index.html").exists()
        assert not (public / "functions").exists() or not list((public / "functions").rglob("*"))


class TestNet:
    def test_backoff_es_acotado(self):
        for attempt in range(10):
            assert 0 <= net._backoff_delay(attempt) <= net.BACKOFF_MAX_SECONDS

    def test_error_no_reintentable_aborta_de_inmediato(self, monkeypatch):
        calls = {"n": 0}

        class _Client:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def request(self, *args, **kwargs):
                calls["n"] += 1
                request = httpx.Request("GET", "https://x.example")
                return httpx.Response(401, request=request)

        monkeypatch.setattr(net.httpx, "Client", _Client)

        with pytest.raises(httpx.HTTPStatusError):
            net.request_json("GET", "https://x.example")

        assert calls["n"] == 1, "un 401 no se reintenta: es un bug de configuración"

    def test_reintenta_errores_transitorios(self, monkeypatch):
        calls = {"n": 0}

        class _Client:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def request(self, *args, **kwargs):
                calls["n"] += 1
                request = httpx.Request("GET", "https://x.example")
                if calls["n"] < 3:
                    return httpx.Response(503, request=request)
                return httpx.Response(200, json={"ok": True}, request=request)

        monkeypatch.setattr(net.httpx, "Client", _Client)
        monkeypatch.setattr(net.time, "sleep", lambda _: None)

        assert net.request_json("GET", "https://x.example") == {"ok": True}
        assert calls["n"] == 3

    def test_probe_url_no_propaga_errores(self, monkeypatch):
        class _Client:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def get(self, *args, **kwargs):
                raise httpx.ConnectTimeout("timeout")

        monkeypatch.setattr(net.httpx, "Client", _Client)

        assert net.probe_url("https://down.example") is False
