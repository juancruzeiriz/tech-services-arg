"""python -m gtm.ui — arranca el server local y abre el navegador.

Bind a 127.0.0.1 siempre, nunca a 0.0.0.0: este proceso guarda en memoria
credenciales de Google/Postgres (vía `gtm/factory/config.py`) y no tiene capa
de autenticación — exponerlo a la red tiene que ser una decisión explícita de
quien lo corre, nunca el default.
"""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

import uvicorn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Panel local de la fábrica de prospección")
    parser.add_argument("--host", default="127.0.0.1", help="default: 127.0.0.1 (nunca 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-browser", action="store_true", help="no abre el navegador solo")
    parser.add_argument("--reload", action="store_true", help="recarga en caliente (desarrollo)")
    args = parser.parse_args(argv)

    url = f"http://{args.host}:{args.port}"
    if not args.no_browser:
        threading.Timer(0.9, lambda: webbrowser.open(url)).start()

    uvicorn.run(
        "gtm.ui.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
