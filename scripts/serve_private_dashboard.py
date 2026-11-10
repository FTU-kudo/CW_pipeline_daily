#!/usr/bin/env python3
"""Serve the static UI and local-only data artifacts; never bind beyond loopback."""
from __future__ import annotations

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_UI = ROOT / "docs"
DATA_ROOT = Path(os.environ.get("CW_DATA_DIR", ROOT / "output" / "private-data")).expanduser()
PRIVATE_DATA = DATA_ROOT / "dashboard"


class PrivateDataHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        parsed = urlsplit(path)
        clean = unquote(parsed.path).lstrip("/")
        if clean == "data" or clean.startswith("data/"):
            relative = clean.removeprefix("data").lstrip("/")
            resolved = (PRIVATE_DATA / relative).resolve()
            try:
                resolved.relative_to(PRIVATE_DATA.resolve())
            except ValueError:
                return str(ROOT / "__not_found__")
            return str(resolved)
        return str(PUBLIC_UI / clean)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not PRIVATE_DATA.is_dir():
        parser.error(f"No local dashboard data at {PRIVATE_DATA}; run python -m cwintel.build first")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(PrivateDataHandler, directory=str(PUBLIC_UI)))
    print(f"Private dashboard: http://127.0.0.1:{args.port}/ (data is served from ignored output/private-data/)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
