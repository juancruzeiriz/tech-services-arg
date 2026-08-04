"""Etapa 4: publicar las demos en URLs únicas y públicas.

Una demo que no está viva no sirve para prospectar. El mensaje "te armé el sitio" con
un adjunto o un mockup es exactamente el pitch que el prospecto ya recibió veinte
veces; un link que abre desde el teléfono, en dos segundos, no lo es.

Esta etapa arma el directorio publicable (`gtm/public/`) y lo deja listo para subir al
host estático:

    wrangler pages deploy gtm/public

`gtm/public/` está fuera de git a propósito. Contiene datos de contacto de negocios
reales que no pidieron estar acá; meterlos en el historial del repo los vuelve
permanentes y públicos. El artefacto se publica, no se versiona.

Uso:
    python -m gtm.factory.deploy --dry-run
    python -m gtm.factory.deploy
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from gtm.factory import artifacts, config
from gtm.factory.logs import get_logger
from gtm.factory.types import Demo, DeploymentError

_logger = get_logger(__name__)

PUBLIC_DIR = config.GTM_DIR / "public"

# El índice nunca debe indexarse ni ser navegable por terceros: lista prospectos.
_INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="robots" content="noindex,nofollow">
<title>Demos</title></head>
<body><h1>Demos publicadas</h1><ul>{items}</ul></body></html>
"""


def demo_url(slug: str, base_url: str) -> str:
    """URL pública y estable de una demo."""
    return f"{base_url.rstrip('/')}/{slug}/"


def deploy(
    demos: list[Demo],
    base_url: str,
    *,
    dry_run: bool = False,
    public_dir: Path | None = None,
) -> list[Demo]:
    """Copia las demos al directorio publicable y les asigna URL.

    Args:
        demos: demos ya generadas en disco.
        base_url: base pública (GitHub Pages o Cloudflare Pages).
        dry_run: calcula URLs sin escribir nada.
        public_dir: destino (para tests).

    Raises:
        DeploymentError: si falta en disco el HTML de alguna demo.
    """
    target_root = public_dir or PUBLIC_DIR
    published: list[Demo] = []

    for demo in demos:
        source = Path(demo.html_path)
        if not source.exists():
            raise DeploymentError(
                f"Falta el HTML de {demo.slug} en {source}: corré generate primero"
            )

        url = demo_url(demo.slug, base_url)

        if not dry_run:
            destination = target_root / demo.slug
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination / "index.html")

        published.append(
            Demo(
                place_id=demo.place_id,
                slug=demo.slug,
                html_path=demo.html_path,
                url=url,
                deployed_at=None if dry_run else datetime.now(UTC),
            )
        )

    if not dry_run:
        target_root.mkdir(parents=True, exist_ok=True)
        items = "".join(
            f'<li><a href="./{d.slug}/">{d.slug}</a></li>' for d in published
        )
        (target_root / "index.html").write_text(
            _INDEX_TEMPLATE.format(items=items), encoding="utf-8"
        )

    _logger.info(
        "deploy completado",
        extra={
            "event": "deploy_done",
            "count": len(published),
            "dry_run": dry_run,
            "target": str(target_root),
        },
    )
    return published


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publica las demos generadas")
    parser.add_argument("--input", default=None, help="default: gtm/build/data/demos.json")
    parser.add_argument("--base-url", default=None, help="default: $GTM_DEMO_BASE_URL")
    parser.add_argument(
        "--dry-run", action="store_true", help="muestra las URLs sin publicar nada"
    )
    args = parser.parse_args(argv)

    config.ensure_dirs()
    input_path = args.input or str(config.DATA_DIR / "demos.json")
    base_url = args.base_url or config.demo_base_url()

    demos = artifacts.read_demos(input_path)

    published = deploy(demos, base_url, dry_run=args.dry_run)

    artifacts.write_demos(input_path, published)

    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}{len(published)} demos -> {PUBLIC_DIR}")
    for demo in published:
        print(f"  {demo.url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
