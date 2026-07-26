from __future__ import annotations

import posixpath
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def make_handler(app_dir: Path, runtime_dir: Path):
    class OverlayHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(app_dir), **kwargs)

        def translate_path(self, path: str) -> str:
            runtime_path = self._translate_runtime_path(path)
            if runtime_path is not None:
                return str(runtime_path)
            return super().translate_path(path)

        def _translate_runtime_path(self, path: str) -> Path | None:
            request_path = urllib.parse.urlsplit(path).path
            if request_path == "/runtime":
                return runtime_dir
            if not request_path.startswith("/runtime/"):
                return None

            relative = urllib.parse.unquote(request_path.removeprefix("/runtime/"))
            normalized = posixpath.normpath(relative)
            parts = [
                part
                for part in normalized.split("/")
                if part and part not in (".", "..")
            ]
            return runtime_dir.joinpath(*parts)

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    return OverlayHandler


def serve(port: int, bind: str, app_dir: Path, runtime_dir: Path) -> None:
    server = ThreadingHTTPServer((bind, port), make_handler(app_dir, runtime_dir))
    print(f"OBS Browser Source URL: http://localhost:{port}/ad-overlay.html", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    server.serve_forever()
