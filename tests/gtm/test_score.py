"""Tests de `score_website` (gtm/factory/score.py) contra el shape real de la
respuesta de PageSpeed Insights.

Hasta el 2026-08-11 ninguna prueba del repo ejercitaba esta función: todos los
tests de `score_prospect`/`score_all` (`test_pipeline_stages.py`) la mockean
entera con `monkeypatch.setattr(score_mod, "score_website", ...)`. Por eso un
rename real de Lighthouse (`viewport`→`meta-viewport`, `tap-targets`→
`target-size`, `font-size` sin sucesor) pasó desapercibido: `mobile_friendly`
y el hallazgo `tap_targets` quedaron sin poder dispararse nunca, para
cualquier sitio, sin que ningún test lo notara. Este archivo cierra ese
agujero fijando el contrato contra los IDs vigentes hoy.
"""

from __future__ import annotations

import httpx

from gtm.factory import score as score_mod

_URL = "https://example.com"


def _lighthouse_payload(
    *,
    performance: float = 0.32,
    seo: float = 0.7,
    accessibility: float = 0.8,
    meta_viewport_score: float | None = 1.0,
    target_size_score: float | None = 1.0,
) -> dict:
    """Payload con la forma real que devuelve PageSpeed Insights hoy (IDs de
    Lighthouse post-rename, verificados en vivo el 2026-08-11)."""
    audits: dict[str, dict] = {}
    if meta_viewport_score is not None:
        audits["meta-viewport"] = {"score": meta_viewport_score}
    if target_size_score is not None:
        audits["target-size"] = {"score": target_size_score}

    return {
        "lighthouseResult": {
            "categories": {
                "performance": {"score": performance},
                "seo": {"score": seo},
                "accessibility": {"score": accessibility},
            },
            "audits": audits,
        }
    }


def _client_returning(payload: dict) -> httpx.AsyncClient:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(_handler))


class TestScoreWebsite:
    async def test_extrae_las_tres_categorias_a_escala_0_100(self):
        async with _client_returning(_lighthouse_payload()) as client:
            result = await score_mod.score_website(client, _URL)

        assert result is not None
        assert result.performance == 32
        assert result.seo == 70
        assert result.accessibility == 80

    async def test_meta_viewport_en_1_marca_mobile_friendly(self):
        async with _client_returning(_lighthouse_payload(meta_viewport_score=1.0)) as client:
            result = await score_mod.score_website(client, _URL)

        assert result is not None
        assert result.mobile_friendly is True

    async def test_meta_viewport_en_0_marca_no_mobile_friendly(self):
        async with _client_returning(_lighthouse_payload(meta_viewport_score=0.0)) as client:
            result = await score_mod.score_website(client, _URL)

        assert result is not None
        assert result.mobile_friendly is False

    async def test_sin_audit_meta_viewport_no_rompe_y_queda_none(self):
        """Si Lighthouse no corrió el audit para esta URL (pasa con sitios muy
        rotos), no hay señal -- `mobile_friendly` queda `None`, no `False`."""
        async with _client_returning(_lighthouse_payload(meta_viewport_score=None)) as client:
            result = await score_mod.score_website(client, _URL)

        assert result is not None
        assert result.mobile_friendly is None

    async def test_target_size_reprobado_dispara_tap_targets(self):
        async with _client_returning(_lighthouse_payload(target_size_score=0.0)) as client:
            result = await score_mod.score_website(client, _URL)

        assert result is not None
        codes = {f.code for f in result.findings}
        assert "tap_targets" in codes

    async def test_target_size_aprobado_no_dispara_tap_targets(self):
        async with _client_returning(_lighthouse_payload(target_size_score=1.0)) as client:
            result = await score_mod.score_website(client, _URL)

        assert result is not None
        codes = {f.code for f in result.findings}
        assert "tap_targets" not in codes

    async def test_lighthouse_result_vacio_devuelve_none(self):
        async with _client_returning({}) as client:
            result = await score_mod.score_website(client, _URL)

        assert result is None

    async def test_fallo_de_red_degrada_a_none_sin_levantar(self):
        def _explode(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no resuelve", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(_explode)) as client:
            result = await score_mod.score_website(client, _URL)

        assert result is None


class TestAuditFailed:
    def test_score_bajo_1_es_fallo(self):
        lighthouse = {"audits": {"target-size": {"score": 0.0}}}
        assert score_mod._audit_failed(lighthouse, "target-size") is True

    def test_score_en_1_no_es_fallo(self):
        lighthouse = {"audits": {"target-size": {"score": 1.0}}}
        assert score_mod._audit_failed(lighthouse, "target-size") is False

    def test_audit_ausente_no_es_fallo(self):
        """Un ID que no está en la respuesta (audit no corrido, o renombrado
        de nuevo en el futuro) no debe leerse como "reprobado" -- si no hay
        señal, no corresponde restar."""
        assert score_mod._audit_failed({"audits": {}}, "target-size") is False

    def test_score_none_explicito_no_es_fallo(self):
        lighthouse = {"audits": {"target-size": {"score": None}}}
        assert score_mod._audit_failed(lighthouse, "target-size") is False
