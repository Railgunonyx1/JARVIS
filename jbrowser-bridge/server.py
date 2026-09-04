"""J-Browser bridge server.

A small, dependency-free (stdlib only) HTTP/SSE server that connects the
JARVIS browser extension to an intelligence backend. It binds to
127.0.0.1 only.

Endpoints
---------
GET  /status     -> {"ok": bool, "kernel": "online"|"offline", ...}
POST /v1/chat    -> SSE stream of {"type":"start|delta|done|error"}
POST /v1/agent   -> launch a Strawberry-style agent (Phase seam)
POST /v1/cdp     -> delegate a chrome.debugger/CDP command to the engine (seam)

The backend is pluggable (see backend.py). Default is the deterministic
EchoBackend so the AI layer works end-to-end without a kernel attached.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from backend import make_backend

logger = logging.getLogger("jbrowser-bridge")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8170

_SAFE_ORIGINS = re.compile(r"^chrome-extension://[a-p]{32}$")


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "JBrowserBridge/0.1.0"
    backend: object = None  # injected by server factory

    # ── CORS / plumbing ────────────────────────────────────────────────────
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type")

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def log_message(self, fmt: str, *args) -> None:
        logger.debug(fmt, *args)

    # ── HTTP verbs ─────────────────────────────────────────────────────────
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/status":
            self._json(200, self.backend.status())
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/v1/chat":
            self._chat()
            return
        if self.path == "/v1/agent":
            self._agent()
            return
        if self.path == "/v1/cdp":
            self._cdp()
            return
        self._json(404, {"ok": False, "error": "not found"})

    # ── endpoints ──────────────────────────────────────────────────────────
    def _chat(self) -> None:
        data = self._read_json()
        if data is None:
            self._json(400, {"ok": False, "error": "invalid json body"})
            return
        messages = data.get("messages") or []
        if not messages and data.get("text"):
            messages = [{"role": "user", "content": data.get("text")}]
        session_id = str(data.get("session_id") or "anon")
        page = data.get("page")

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()

        def emit(event: dict) -> None:
            try:
                self.wfile.write(b"data: " + json.dumps(event).encode("utf-8") + b"\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        try:
            self.backend.stream_chat(session_id, messages, page, emit)
        except Exception as exc:  # noqa: BLE001
            logger.exception("chat backend error")
            emit({"type": "error", "message": str(exc)[:500], "code": "backend_error"})
        # SSE streams end with the "done"/"error" event; close the connection
        # so clients that also read to EOF release cleanly.
        self.close_connection = True

    def _agent(self) -> None:
        """Launch a Strawberry-style agent. Phase 3 seam — not implemented."""
        self._json(501, {
            "ok": False,
            "code": "not_implemented",
            "message": "agent endpoint is a Phase-3 seam; wire to the agent runtime",
        })

    def _cdp(self) -> None:
        """Delegate a chrome.debugger/CDP command. Phase 2 seam — not implemented."""
        self._json(501, {
            "ok": False,
            "code": "not_implemented",
            "message": "cdp endpoint is a Phase-2 seam; wire to jbrowser engine",
        })


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
          backend_kind: str = "echo", engine=None) -> ThreadingHTTPServer:
    backend = make_backend(backend_kind, engine=engine)
    handler = type(
        "JBridgeHandler", (BridgeHandler,), {"backend": backend}
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    return httpd


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="J-Browser bridge server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--backend", default="echo",
                        choices=["echo", "kernel"])
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        stream=sys.stdout,
    )
    httpd = serve(args.host, args.port, backend_kind=args.backend)
    logger.info("JBrowserBridge listening on http://%s:%d backend=%s",
                args.host, args.port, args.backend)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
