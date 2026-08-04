"""Tests del cliente de la Chrome UX Report API (gtm/factory/crux.py)."""

from __future__ import annotations

import httpx
import pytest

from gtm.factory.crux import (
    CruxMetrics,
    classify_cls,
    classify_inp,
    classify_lcp,
    fetch_crux_metrics,
    parse_crux_payload,
)


def test_parsea_p75_de_las_tres_metricas():
    payload = {
        "record": {
            "metrics": {
                "largest_contentful_paint": {"percentiles": {"p75": 6200}},
                "interaction_to_next_paint": {"percentiles": {"p75": 480}},
                "cumulative_layout_shift": {"percentiles": {"p75": "0.31"}},
            }
        }
    }
    m = parse_crux_payload(payload)
    assert m.lcp_ms == 6200
    assert m.inp_ms == 480
    assert m.cls == pytest.approx(0.31)


def test_metricas_ausentes_quedan_en_none_sin_romper():
    m = parse_crux_payload({"record": {"metrics": {}}})
    assert m.lcp_ms is None
    assert m.inp_ms is None
    assert m.cls is None


def test_record_ausente_devuelve_metrica_vacia():
    m = parse_crux_payload({})
    assert m.lcp_ms is None and m.inp_ms is None and m.cls is None


class TestClasificacionLCP:
    def test_lcp_bueno_bajo_2500ms(self):
        assert classify_lcp(2000) == "good"

    def test_lcp_pobre_sobre_4000ms(self):
        assert classify_lcp(4500) == "poor"

    def test_lcp_necesita_mejora_en_el_medio(self):
        assert classify_lcp(3000) == "needs-improvement"

    def test_lcp_none_no_clasifica(self):
        assert classify_lcp(None) is None


class TestClasificacionINPyCLS:
    def test_inp_bueno_hasta_200ms(self):
        assert classify_inp(150) == "good"

    def test_inp_pobre_sobre_500ms(self):
        assert classify_inp(600) == "poor"

    def test_cls_bueno_hasta_0_1(self):
        assert classify_cls(0.05) == "good"

    def test_cls_pobre_sobre_0_25(self):
        assert classify_cls(0.4) == "poor"


class TestFetchCruxMetrics:
    async def test_404_no_es_error_devuelve_none(self, monkeypatch):
        async def _raise_404(*_args, **_kwargs):
            raise httpx.HTTPStatusError(
                "not found",
                request=httpx.Request("POST", "https://x"),
                response=httpx.Response(404),
            )

        import gtm.factory.crux as crux_mod

        monkeypatch.setattr(crux_mod, "request_json_async", _raise_404)

        async with httpx.AsyncClient() as client:
            result = await fetch_crux_metrics(client, "https://sitio-chico.example", api_key="k")
        assert result is None

    async def test_prueba_url_exacta_antes_que_origin(self, monkeypatch):
        calls: list[dict] = []

        async def _fake(_client, _method, _url, *, params=None, json_body=None, **_kwargs):
            calls.append(dict(json_body or {}))
            if "url" in (json_body or {}):
                raise httpx.HTTPStatusError(
                    "not found",
                    request=httpx.Request("POST", "https://x"),
                    response=httpx.Response(404),
                )
            return {"record": {"metrics": {}}}

        import gtm.factory.crux as crux_mod

        monkeypatch.setattr(crux_mod, "request_json_async", _fake)

        async with httpx.AsyncClient() as client:
            result = await fetch_crux_metrics(client, "https://sitio.example/pagina", api_key="k")

        assert result is not None
        assert any("url" in c for c in calls)
        assert any("origin" in c for c in calls)
        assert all(c.get("formFactor") == "PHONE" for c in calls)

    async def test_otro_error_http_se_propaga(self, monkeypatch):
        async def _raise_500(*_args, **_kwargs):
            raise httpx.HTTPStatusError(
                "server error",
                request=httpx.Request("POST", "https://x"),
                response=httpx.Response(500),
            )

        import gtm.factory.crux as crux_mod

        monkeypatch.setattr(crux_mod, "request_json_async", _raise_500)

        async with httpx.AsyncClient() as client:
            with pytest.raises(httpx.HTTPStatusError):
                await fetch_crux_metrics(client, "https://sitio.example", api_key="k")


def test_crux_metrics_es_serializable_a_dict_vacio_por_defecto():
    m = CruxMetrics()
    assert m.lcp_ms is None
    assert m.inp_ms is None
    assert m.cls is None
