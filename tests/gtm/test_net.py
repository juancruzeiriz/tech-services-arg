"""Tests de `probe_url`/`probe_url_async` (gtm/factory/net.py).

Hasta el 2026-08-11 no había ningún test de la frontera exacta entre
"reachable" y "no reachable": los tests de `score_prospect` mockean
`probe_url_async` entero. Un prospecto real (`leos-tree-service.com`)
mostró el costo de ese agujero -- el sitio devuelve 404 de verdad (confirmado
con curl) pero contaba como "reachable" porque el corte viejo era
`status_code < 500`, así que se lo mandaba a puntuar con PageSpeed en vez de
tratarlo como el mejor ángulo de venta posible ("tu sitio ni siquiera
carga"). Este archivo fija el contrato correcto (`< 400`) para que no vuelva
a romperse en silencio.
"""

from __future__ import annotations

import httpx

from gtm.factory.net import probe_url_async

_URL = "https://example.com"


def _client_returning(status: int) -> httpx.AsyncClient:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(_handler))


class TestProbeUrlAsync:
    async def test_200_es_reachable(self):
        async with _client_returning(200) as client:
            assert await probe_url_async(client, _URL) is True

    async def test_redirect_301_es_reachable(self):
        # httpx sigue redirects por default en los clientes del proyecto
        # (`follow_redirects=True` en `async_client`); acá se prueba el
        # status crudo que ve `probe_url_async` si por algo no se siguiera.
        async with _client_returning(301) as client:
            assert await probe_url_async(client, _URL) is True

    async def test_404_no_es_reachable(self):
        """El caso que motivó este archivo: una página que no existe."""
        async with _client_returning(404) as client:
            assert await probe_url_async(client, _URL) is False

    async def test_403_no_es_reachable(self):
        async with _client_returning(403) as client:
            assert await probe_url_async(client, _URL) is False

    async def test_500_no_es_reachable(self):
        async with _client_returning(500) as client:
            assert await probe_url_async(client, _URL) is False

    async def test_error_de_transporte_no_es_reachable(self):
        def _explode(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no resuelve", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(_explode)) as client:
            assert await probe_url_async(client, _URL) is False
