"""Exporta el subconjunto público de FINDINGS para la página de auditoría del
sitio (`site/functions/api/audit.js`, Cloudflare Pages Function en JavaScript).

Por qué un export y no reescribir el copy en JS a mano: `findings.py` es la
única fuente de verdad del texto de venta (`gtm/factory/findings.py`) -- dos
copias del mismo texto en dos lenguajes de programación divergen con el
tiempo, sin que nada lo note. Este script corre en build time y deja un JSON
que la Function consume tal cual.

Solo el subconjunto **derivable en el edge sin Python**: hallazgos de
Lighthouse (PageSpeed Insights ya devuelve JSON, sin necesidad de parsear
HTML con BeautifulSoup) más `no_https`, que es una comparación de esquema de
URL. Los hallazgos forenses (`legacy_jquery`, `dated_palette`,
`stale_copyright`, tablas de maquetación, `no_social_presence`) exigen
parsear el HTML crudo del sitio -- portarlos a la Function duplicaría
`forensics.py` entero en JS y lo haría divergir. Quedan fuera de la versión
pública a propósito: ver `docs/superpowers/specs` o el plan de la sesión que
agregó este módulo para el razonamiento completo.

Uso:
    python -m gtm.factory.findings_export
    python -m gtm.factory.findings_export --output ruta/personalizada.json

Nota: este export es un paso manual, no automatizado en CI todavía. Si se
edita el texto de venta de uno de estos seis códigos en `findings.py`, hay
que volver a correr este comando y commitear el JSON actualizado -- de lo
contrario la página pública queda desincronizada del resto del pipeline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gtm.factory.findings import FINDINGS

# Únicamente los derivables en el edge: ver el docstring del módulo.
PUBLIC_CODES: tuple[str, ...] = (
    "no_https",
    "no_viewport",
    "tap_targets",
    "tiny_font",
    "crux_lcp_poor",
    "crux_inp_poor",
)

_DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "site" / "src" / "data" / "audit-findings.json"


def build_export() -> dict[str, dict[str, object]]:
    return {
        code: {
            "dimension": FINDINGS[code].dimension.value,
            "severity": FINDINGS[code].severity.value,
            "weight": FINDINGS[code].weight,
            "sales_line_en": FINDINGS[code].sales_line_en,
            "sales_line_es": FINDINGS[code].sales_line_es,
        }
        for code in PUBLIC_CODES
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=None, help=f"default: {_DEFAULT_OUTPUT}")
    args = parser.parse_args(argv)

    output_path = Path(args.output) if args.output else _DEFAULT_OUTPUT
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = build_export()
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(payload)} hallazgos exportados -> {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
