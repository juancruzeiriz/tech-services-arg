"""Etapa opcional: informe de auditoría privado, material de apoyo para la llamada.

No es la oferta. La oferta es la demo (`generate.py`): la tesis del proyecto
(`gtm/README.md`) es entregar el trabajo *terminado* antes de la transacción,
y un informe que lista problemas es diagnóstico, no trabajo entregado. Este
módulo existe para un momento puntual y distinto: la objeción "ya tengo sitio
web" documentada en `gtm/pipeline.md` — en vez de mandar al prospecto a
pagespeed.web.dev con su propio número, se le muestra (en la llamada, no
antes) un informe con marca propia que cita la misma evidencia que ya
produce `score.py`, con el copy de venta que ya vive en `findings.py`.

Deliberadamente NO se publica. `deploy.py` solo mueve `gtm/build/demos/` a
`gtm/public/`; este módulo escribe en `gtm/build/audits/`, fuera de ese
camino, para que nunca termine online por accidente.

Uso:
    python -m gtm.factory.audit --prospect <place_id>
    python -m gtm.factory.audit --all
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from string import Template

from gtm.catalog import city_of
from gtm.factory import artifacts, config
from gtm.factory.logs import get_logger
from gtm.factory.types import GenerationError, Language, PainScore, Prospect, vertical_label

_logger = get_logger(__name__)

# Mismo orden que `_DIMENSION_WEIGHTS` en types.py (dict insertion order):
# PainScore.sub_scores ya itera en este orden, así que las barras salen
# consistentes corrida tras corrida sin que este módulo tenga que ordenar nada.
_DIMENSION_LABELS_ES = {
    "speed": "Velocidad",
    "mobile": "Uso en celular",
    "seo": "SEO",
    "modernity": "Modernidad",
    "conversion": "Conversión",
}
_DIMENSION_LABELS_EN = {
    "speed": "Speed",
    "mobile": "Mobile usability",
    "seo": "SEO",
    "modernity": "Modernity",
    "conversion": "Conversion",
}


def _dimension_label(dimension: str, language: Language) -> str:
    table = _DIMENSION_LABELS_ES if language is Language.ES else _DIMENSION_LABELS_EN
    return table.get(dimension, dimension.title())


def _sub_scores_html(score: PainScore, language: Language) -> str:
    rows: list[str] = []
    for dimension, value in score.sub_scores.items():
        label = html.escape(_dimension_label(dimension, language))
        rows.append(
            f'<div class="dim-row"><span class="dim-label">{label}</span>'
            f'<div class="dim-bar"><div class="dim-fill" style="width:{value}%"></div></div>'
            f'<span class="dim-value">{value}</span></div>'
        )
    return "\n".join(rows)


def _findings_html(score: PainScore, language: Language) -> str:
    # Ya vienen del más grave al menos grave -- ver PainScore.sales_lines.
    lines = score.sales_lines(language)
    if not lines:
        text = (
            "Sin hallazgos automatizados citables. Revisar el sitio a mano antes de la llamada."
            if language is Language.ES
            else "No automated, citable findings. Review the site by hand before the call."
        )
        return f'<p class="empty">{text}</p>'
    items = "\n".join(f"<li>{html.escape(line)}</li>" for line in lines)
    return f'<ul class="findings">{items}</ul>'


def _notes_html(score: PainScore) -> str:
    # `score.notes` sale de score.py siempre en español -- es diagnóstico
    # interno, no una línea de venta bilingüe como `sales_lines`, así que se
    # muestra tal cual sin importar el idioma del informe.
    if not score.notes:
        return '<p class="empty">—</p>'
    return "\n".join(f"<p>{html.escape(note)}</p>" for note in score.notes)


def _score_caption(score: PainScore, language: Language) -> str:
    if language is Language.ES:
        if score.is_qualified:
            return "Calificado como prospecto: hay dolor digital suficiente para justificar la llamada."
        return "Por debajo del umbral de calificación: la web ya está relativamente bien."
    if score.is_qualified:
        return "Qualifies as a prospect: enough digital pain to justify the call."
    return "Below the qualification threshold: the site is already relatively solid."


def render(
    prospect: Prospect, score: PainScore, author_name: str, language: Language = Language.EN
) -> str:
    """Renderiza el informe de auditoría de un prospecto ya puntuado.

    A diferencia de `generate.render`, no exige teléfono ni ningún otro dato
    de contacto: se puede generar para cualquier prospecto puntuado, incluso
    uno sin sitio web (el informe simplemente cita esa ausencia como hallazgo).

    Raises:
        GenerationError: si falta la plantilla o algún placeholder queda sin valor.
    """
    template_path = config.TEMPLATE_DIR / "audit.html"
    if not template_path.exists():
        raise GenerationError(f"Falta la plantilla de auditoría en {template_path}")

    label = vertical_label(prospect.vertical, language)
    business_name = html.escape(prospect.name)
    city = html.escape(city_of(prospect.metro))
    author_name_esc = html.escape(author_name)
    phone_suffix = f" · {html.escape(prospect.phone)}" if prospect.phone else ""

    if language is Language.ES:
        report_title = f"Auditoría digital — {business_name}"
        meta_line = f"{html.escape(label)} en {city}{phone_suffix}"
        internal_flag_label = "Documento interno"
        internal_flag_text = "material de apoyo para la llamada, no se manda tal cual al prospecto"
        findings_heading = "Hallazgos, del más grave al menos grave"
        notes_heading = "Notas adicionales"
        footer_note = (
            f"Generado por {author_name_esc} a partir de datos públicos del negocio y de "
            "PageSpeed Insights."
        )
    else:
        report_title = f"Digital audit — {business_name}"
        meta_line = f"{html.escape(label)} in {city}{phone_suffix}"
        internal_flag_label = "Internal document"
        internal_flag_text = "call support material, not meant to be sent to the prospect as-is"
        findings_heading = "Findings, most severe first"
        notes_heading = "Additional notes"
        footer_note = (
            f"Generated by {author_name_esc} from public business data and PageSpeed Insights."
        )

    values = {
        "lang": language.value,
        "report_title": report_title,  # ya lleva business_name pre-escapado, ver arriba
        "meta_line": meta_line,
        "internal_flag_label": internal_flag_label,
        "internal_flag_text": internal_flag_text,
        "score_value": str(score.score),
        "score_caption": html.escape(_score_caption(score, language)),
        "sub_scores_html": _sub_scores_html(score, language),
        "findings_heading": findings_heading,
        "findings_html": _findings_html(score, language),
        "notes_heading": notes_heading,
        "notes_html": _notes_html(score),
        "footer_note": footer_note,
    }

    template = Template(template_path.read_text(encoding="utf-8"))
    try:
        # substitute (no safe_substitute), mismo motivo que generate.render:
        # un placeholder sin valor tiene que explotar acá, no filtrarse al informe.
        return template.substitute(values)
    except KeyError as exc:
        raise GenerationError(f"Placeholder sin valor en la plantilla de auditoría: {exc}") from exc


def generate(
    prospect: Prospect,
    score: PainScore,
    author_name: str,
    language: Language = Language.EN,
    *,
    audits_dir: Path | None = None,
) -> str:
    """Renderiza y escribe el informe en disco. Idempotente por slug.

    Devuelve la ruta del HTML escrito. No hay un tipo `Demo`-like propio para
    este artefacto porque no participa del resto del pipeline: no se
    despliega (`deploy.py` no lo toca) y no se manda (`outreach.py`/`contact.py`
    tampoco). `audits_dir` sobreescribe `config.AUDITS_DIR` -- mismo patrón que
    `demos_dir` en `generate.generate`, para no pisar corridas concurrentes.
    """
    config.ensure_dirs()
    markup = render(prospect, score, author_name, language)

    audit_dir = (audits_dir or config.AUDITS_DIR) / prospect.slug
    audit_dir.mkdir(parents=True, exist_ok=True)
    html_path = audit_dir / "index.html"
    html_path.write_text(markup, encoding="utf-8")

    _logger.info(
        "informe de auditoría generado",
        extra={
            "event": "audit_generated",
            "place_id": prospect.place_id,
            "slug": prospect.slug,
            "score": score.score,
        },
    )
    return str(html_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Genera el informe de auditoría privado (no se publica, no se manda)"
    )
    parser.add_argument("--input", default=None, help="default: gtm/build/data/prospects.json")
    parser.add_argument("--scores", default=None, help="default: gtm/build/data/scores.json")
    parser.add_argument("--prospect", default=None, help="place_id único a generar")
    parser.add_argument("--all", action="store_true", help="genera para todos los prospectos puntuados")
    parser.add_argument("--author-name", default=None, help="default: $GTM_FROM_NAME")
    parser.add_argument(
        "--language", choices=[lang.value for lang in Language], default=Language.EN.value
    )
    args = parser.parse_args(argv)

    if not args.prospect and not args.all:
        parser.error("indicá --prospect <place_id> o --all")

    config.ensure_dirs()
    input_path = args.input or str(config.DATA_DIR / "prospects.json")
    scores_path = args.scores or str(config.DATA_DIR / "scores.json")
    author_name = args.author_name or config.require_env("GTM_FROM_NAME")
    language = Language(args.language)

    prospects = artifacts.read_prospects(input_path)
    if args.prospect:
        prospects = [p for p in prospects if p.place_id == args.prospect]
        if not prospects:
            print(f"No hay prospecto con place_id={args.prospect}", file=sys.stderr)
            return 1

    try:
        scores_by_id = {s.place_id: s for s in artifacts.read_scores(scores_path)}
    except FileNotFoundError:
        print(f"No hay scores en {scores_path}: corré `score` primero", file=sys.stderr)
        return 1

    written: list[str] = []
    skipped = 0
    for prospect in prospects:
        score = scores_by_id.get(prospect.place_id)
        if score is None:
            skipped += 1
            _logger.warning(
                "prospecto sin puntuar: no se genera informe",
                extra={"event": "audit_skipped", "place_id": prospect.place_id},
            )
            continue
        written.append(generate(prospect, score, author_name, language))

    suffix = f" ({skipped} sin score, omitidos)" if skipped else ""
    print(f"{len(written)} informes generados{suffix} -> {config.AUDITS_DIR}")
    for path in written:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
