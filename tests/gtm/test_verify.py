"""Tests de la Capa 2 de verificación de ausencia digital (`gtm/factory/verify.py`).

Google Maps es una sola fuente: un negocio puede tener dominio propio y no
haberlo vinculado en su ficha. Este módulo confirma la ausencia -- o la
desmiente -- antes de que `score.py` le asigne el dolor máximo (100) a un
prospecto y afirme, en la primera línea del mensaje, que "no tiene sitio".
"""

from __future__ import annotations

import httpx

from gtm.factory import verify
from gtm.factory.types import DigitalTrace, Prospect


def _prospect(**overrides) -> Prospect:
    defaults = {
        "place_id": "p1",
        "name": "Legacy Tree Company",
        "vertical": "tree_service",
        "metro": "Albuquerque, NM",
        "phone": "(505) 555-0148",
    }
    defaults.update(overrides)
    return Prospect(**defaults)


class TestCandidateDomains:
    def test_deriva_dominio_del_nombre_completo(self):
        domains = verify.candidate_domains(_prospect())
        assert "legacytreecompany.com" in domains

    def test_deriva_dominio_sin_el_sufijo_legal(self):
        """"Company" es un sufijo genérico -- el dominio más probable no lo
        incluye ("legacytree.com", no "legacytreecompany.com" solamente)."""
        domains = verify.candidate_domains(_prospect())
        assert "legacytree.com" in domains

    def test_prueba_dot_com_y_dot_net(self):
        domains = verify.candidate_domains(_prospect())
        assert "legacytree.net" in domains

    def test_tope_de_candidatos(self):
        domains = verify.candidate_domains(_prospect(name="A B C D E F G H Company"))
        assert len(domains) <= 6

    def test_nombre_sin_alfanumericos_no_rompe(self):
        assert verify.candidate_domains(_prospect(name="!!!")) == []


class TestVerifyAbsenceSubCapaA:
    """Sub-capa A: dominios derivados del nombre, gratis, sin API key."""

    async def test_dominio_propio_corroborado_por_telefono(self, monkeypatch):
        prospect = _prospect()

        async def _up(_client, url):
            return "legacytree.com" in url

        async def _fetch(_client, url):
            if "legacytree.com" not in url:
                return None
            return (url, "<html>Call us at (505) 555-0148 for a free quote</html>")

        monkeypatch.setattr(verify, "probe_url_async", _up)
        monkeypatch.setattr(verify, "fetch_text_async", _fetch)

        result = await verify.verify_absence(object(), prospect)

        assert result.kind is DigitalTrace.OWN_DOMAIN
        assert result.url is not None and "legacytree.com" in result.url

    async def test_dominio_que_responde_pero_sin_corroboracion_no_cuenta(self, monkeypatch):
        """Un dominio parqueado o de otro negocio no debe declararse propio
        solo porque responde -- tiene que citar el teléfono o el nombre."""
        prospect = _prospect()

        async def _up(_client, _url):
            return True

        async def _fetch(_client, url):
            return (url, "<html>This domain is for sale. Contact us.</html>")

        monkeypatch.setattr(verify, "probe_url_async", _up)
        monkeypatch.setattr(verify, "fetch_text_async", _fetch)

        result = await verify.verify_absence(object(), prospect)

        assert result.kind is not DigitalTrace.OWN_DOMAIN

    async def test_dominio_corroborado_por_nombre_sin_telefono(self, monkeypatch):
        prospect = _prospect(phone=None)

        async def _up(_client, _url):
            return True

        async def _fetch(_client, url):
            return (url, "<html>Welcome to Legacy Tree Company, tree service you can trust</html>")

        monkeypatch.setattr(verify, "probe_url_async", _up)
        monkeypatch.setattr(verify, "fetch_text_async", _fetch)

        result = await verify.verify_absence(object(), prospect)

        assert result.kind is DigitalTrace.OWN_DOMAIN


class TestVerifyAbsenceSinSubCapaB:
    async def test_sin_key_y_sin_dominio_propio_es_unverified(self, monkeypatch):
        async def _down(_client, _url):
            return False

        monkeypatch.setattr(verify, "probe_url_async", _down)

        result = await verify.verify_absence(object(), _prospect())

        assert result.kind is DigitalTrace.UNVERIFIED
        assert result.url is None


class TestVerifyAbsenceSubCapaB:
    """Sub-capa B: Google Programmable Search, solo si hay key+cx."""

    async def test_resultado_de_dominio_propio_es_own_domain(self, monkeypatch):
        async def _down(_client, _url):
            return False

        async def _search(_client, _prospect, _key, _cx):
            return [("legacytree.com", "https://legacytree.com")]

        monkeypatch.setattr(verify, "probe_url_async", _down)
        monkeypatch.setattr(verify, "_search", _search)

        result = await verify.verify_absence(
            object(), _prospect(), search_api_key="k", search_cx="cx"
        )

        assert result.kind is DigitalTrace.OWN_DOMAIN
        assert result.url == "https://legacytree.com"

    async def test_resultados_solo_de_directorios_es_directory_only(self, monkeypatch):
        async def _down(_client, _url):
            return False

        async def _search(_client, _prospect, _key, _cx):
            return [
                ("www.yelp.com", "https://www.yelp.com/biz/legacy-tree"),
                ("www.angi.com", "https://www.angi.com/companylist/legacy-tree"),
            ]

        monkeypatch.setattr(verify, "probe_url_async", _down)
        monkeypatch.setattr(verify, "_search", _search)

        result = await verify.verify_absence(
            object(), _prospect(), search_api_key="k", search_cx="cx"
        )

        assert result.kind is DigitalTrace.DIRECTORY_ONLY

    async def test_sin_resultados_es_no_trace(self, monkeypatch):
        async def _down(_client, _url):
            return False

        async def _search(_client, _prospect, _key, _cx):
            return []

        monkeypatch.setattr(verify, "probe_url_async", _down)
        monkeypatch.setattr(verify, "_search", _search)

        result = await verify.verify_absence(
            object(), _prospect(), search_api_key="k", search_cx="cx"
        )

        assert result.kind is DigitalTrace.NO_TRACE

    async def test_fallo_de_red_en_la_busqueda_degrada_a_unverified(self, monkeypatch):
        async def _down(_client, _url):
            return False

        async def _search(_client, _prospect, _key, _cx):
            raise httpx.HTTPStatusError("500", request=None, response=None)

        monkeypatch.setattr(verify, "probe_url_async", _down)
        monkeypatch.setattr(verify, "_search", _search)

        result = await verify.verify_absence(
            object(), _prospect(), search_api_key="k", search_cx="cx"
        )

        assert result.kind is DigitalTrace.UNVERIFIED

    async def test_resultado_de_google_maps_se_ignora(self, monkeypatch):
        """Un link a maps.google.com no es ni dominio propio ni directorio de
        terceros -- no debe contarse para ninguno de los dos."""
        async def _down(_client, _url):
            return False

        async def _search(_client, _prospect, _key, _cx):
            return [("maps.google.com", "https://maps.google.com/?cid=123")]

        monkeypatch.setattr(verify, "probe_url_async", _down)
        monkeypatch.setattr(verify, "_search", _search)

        result = await verify.verify_absence(
            object(), _prospect(), search_api_key="k", search_cx="cx"
        )

        assert result.kind is DigitalTrace.NO_TRACE


class TestSearchPayloadReal:
    """`_search` en sí, contra el shape real de la Custom Search JSON API --
    sin mockear la función entera, para no repetir el mismo agujero que
    dejó pasar el rename de Lighthouse (ver test_score.py)."""

    async def test_extrae_host_y_link_de_cada_item(self):
        payload = {
            "items": [
                {"link": "https://www.legacytree.com/", "displayLink": "www.legacytree.com"},
                {"link": "https://www.yelp.com/biz/legacy-tree", "displayLink": "www.yelp.com"},
            ]
        }

        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
            results = await verify._search(client, _prospect(), "key", "cx")

        assert results == [
            ("legacytree.com", "https://www.legacytree.com/"),
            ("yelp.com", "https://www.yelp.com/biz/legacy-tree"),
        ]

    async def test_sin_items_devuelve_lista_vacia(self):
        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={}, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
            results = await verify._search(client, _prospect(), "key", "cx")

        assert results == []
