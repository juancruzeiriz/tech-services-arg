"""Tests del cliente de la Wayback Machine CDX API (gtm/factory/archive.py)."""

from __future__ import annotations

from datetime import date

import httpx

from gtm.factory.archive import (
    format_month_year,
    last_meaningful_change,
    parse_cdx_rows,
)


def test_devuelve_la_fecha_del_ultimo_cambio_de_contenido():
    # collapse=digest: una fila por cambio real de contenido, no una por
    # captura -- un sitio archivado 400 veces sin cambiar da una sola fila.
    rows = [["timestamp", "digest"], ["20160312090000", "AAA"], ["20190104120000", "BBB"]]
    assert parse_cdx_rows(rows) == date(2019, 1, 4)


def test_sin_capturas_devuelve_none():
    assert parse_cdx_rows([["timestamp", "digest"]]) is None
    assert parse_cdx_rows([]) is None


def test_ignora_filas_con_timestamp_corrupto():
    rows = [["timestamp", "digest"], ["basura", "AAA"], ["20200101000000", "BBB"]]
    assert parse_cdx_rows(rows) == date(2020, 1, 1)


def test_toma_la_fecha_mas_reciente_sin_asumir_orden():
    rows = [
        ["timestamp", "digest"],
        ["20220601000000", "CCC"],
        ["20160312090000", "AAA"],
        ["20190104120000", "BBB"],
    ]
    assert parse_cdx_rows(rows) == date(2022, 6, 1)


class TestFormatMonthYear:
    def test_formatea_en_espanol(self):
        assert format_month_year(date(2016, 3, 12), "es") == "marzo de 2016"

    def test_formatea_en_ingles(self):
        assert format_month_year(date(2016, 3, 12), "en") == "March 2016"


class TestLastMeaningfulChange:
    async def test_devuelve_none_si_la_api_falla(self, monkeypatch):
        async def _raise(*_args, **_kwargs):
            raise httpx.TransportError("timeout")

        import gtm.factory.archive as archive_mod

        monkeypatch.setattr(archive_mod, "request_json_async", _raise)
        archive_mod.last_meaningful_change.cache_clear()

        async with httpx.AsyncClient() as client:
            result = await last_meaningful_change(client, "sitio-caido.example")
        assert result is None

    async def test_devuelve_la_fecha_cuando_la_api_responde(self, monkeypatch):
        async def _fake(*_args, **_kwargs):
            return [["timestamp", "digest"], ["20180501000000", "AAA"]]

        import gtm.factory.archive as archive_mod

        monkeypatch.setattr(archive_mod, "request_json_async", _fake)
        archive_mod.last_meaningful_change.cache_clear()

        async with httpx.AsyncClient() as client:
            result = await last_meaningful_change(client, "sitio.example")
        assert result == date(2018, 5, 1)

    async def test_cachea_por_host_dentro_de_la_corrida(self, monkeypatch):
        calls = {"n": 0}

        async def _fake(*_args, **_kwargs):
            calls["n"] += 1
            return [["timestamp", "digest"], ["20180501000000", "AAA"]]

        import gtm.factory.archive as archive_mod

        monkeypatch.setattr(archive_mod, "request_json_async", _fake)
        archive_mod.last_meaningful_change.cache_clear()

        async with httpx.AsyncClient() as client:
            await last_meaningful_change(client, "mismo-host.example")
            await last_meaningful_change(client, "mismo-host.example")

        assert calls["n"] == 1


def test_parse_cdx_rows_no_lanza_con_filas_incompletas():
    assert parse_cdx_rows([["timestamp", "digest"], ["20200101000000"]]) == date(2020, 1, 1)
