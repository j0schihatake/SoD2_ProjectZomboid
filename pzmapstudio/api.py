"""Small HTTP API shared by agents and a future human UI."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .audit import audit_scene
from .guide import CAPABILITIES, format_help
from .render import render
from .scene import Scene


class Studio:
    def __init__(self, scene_path: str | Path):
        self.path = Path(scene_path)
        self.scene = Scene.load(self.path)
        self.lock = threading.RLock()

    def command(self, payload: dict) -> dict:
        with self.lock:
            result = self.scene.apply(payload)
            self.scene.save(self.path)
            return {"ok": True, "result": result, "stats": self.scene.stats()}

    def batch(self, payload: dict) -> dict:
        commands = payload.get("commands")
        if not isinstance(commands, list):
            raise ValueError("commands must be a list")
        with self.lock:
            result = self.scene.apply_batch(commands)
            self.scene.save(self.path)
            return {"ok": True, "result": result, "stats": self.scene.stats()}

    def audit(self) -> dict:
        with self.lock:
            return audit_scene(self.scene)

    def save(self) -> dict:
        with self.lock:
            self.scene.save(self.path)
            return {"ok": True, "stats": self.scene.stats()}

    def render_png(self, floor: int = 0) -> bytes:
        import tempfile
        with self.lock, tempfile.NamedTemporaryFile(suffix=".png") as handle:
            render(self.scene, handle.name, floor=floor)
            return Path(handle.name).read_bytes()


def make_handler(studio: Studio):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PZMapStudio/0.1"

        def log_message(self, fmt, *args):
            pass

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/scene":
                with studio.lock:
                    bbox = parse_qs(parsed.query).get("bbox", [""])[0]
                    layer = parse_qs(parsed.query).get("layer", [None])[0]
                    if bbox:
                        x, y, w, h = (int(part) for part in bbox.split(","))
                        self._json(200, studio.scene.query_area(x, y, w, h, layer))
                    else:
                        self._json(200, studio.scene.to_dict())
                return
            if parsed.path == "/api/stats":
                with studio.lock:
                    self._json(200, studio.scene.stats())
                return
            if parsed.path == "/api/audit":
                self._json(200, studio.audit())
                return
            if parsed.path == "/api/help":
                self._json(200, CAPABILITIES)
                return
            if parsed.path == "/api/help.txt":
                body = format_help().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/api/render.png":
                floor = int(parse_qs(parsed.query).get("floor", ["0"])[0])
                try:
                    png = studio.render_png(floor)
                except Exception as error:
                    self._json(400, {"ok": False, "error": str(error)})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png)))
                self.end_headers()
                self.wfile.write(png)
                return
            if parsed.path == "/":
                html = (
                    "<html><body><h1>PZMapStudio</h1>"
                    "<p>API: /api/scene, /api/render.png, POST /api/command</p>"
                    "</body></html>"
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return
            self._json(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            parsed = urlparse(self.path)
            try:
                payload = self._body()
                if parsed.path == "/api/command":
                    self._json(200, studio.command(payload))
                    return
                if parsed.path == "/api/batch":
                    self._json(200, studio.batch(payload))
                    return
                if parsed.path == "/api/save":
                    self._json(200, studio.save())
                    return
                self._json(404, {"ok": False, "error": "not found"})
            except Exception as error:
                self._json(400, {"ok": False, "error": str(error)})

    return Handler


def serve(scene_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    studio = Studio(scene_path)
    server = ThreadingHTTPServer((host, port), make_handler(studio))
    print(f"PZMapStudio: http://{host}:{port}  scene={scene_path}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
