"""J-Browser bridge server.

A small, dependency-free (stdlib only) HTTP/SSE server that connects the
JARVIS browser extension to an intelligence backend. It binds to
127.0.0.1 only.

Endpoints
---------
GET  /status     -> {"ok": bool, "kernel": "online"|"offline", ...}
POST /v1/chat    -> SSE stream of {"type":"start|delta|done|error"}
POST /v1/agent   -> SSE stream of the same protocol; runs a JARVIS agent task
                    (AgentLoop -> ToolExecutionService -> orbit.* -> CDP).
                    Only available when a kernel backend with an engine is
                    attached; otherwise answers 501 (fail closed).
POST /v1/cdp     -> NOT a raw control path; always 501. Browser control is
                    performed ONLY through JARVIS tools (ToolExecutionService
                    -> BrowserController -> CDP), never through this endpoint.

Backends
--------
* ``echo``    — deterministic offline stub (default; no kernel required).
* ``kernel``  — drives the real JARVIS stack through a ``StreamEngine``
  (see engine.py). ``serve(..., backend_kind="kernel", engine=engine)``:
  the default ``ModelGatewayEngine`` streams chat through the JARVIS model
  gateway (ProviderRouter fallback) with input/output budgets. Supply
  :class:`agent.AgentEngine` for task-driven (DSH-style) browsing.

Security (G1 hardenings)
------------------------
* Loopback-only bind (127.0.0.1).
* CORS restricted to ``chrome-extension://`` origins — never ``*``.
* Optional bearer-token auth: when ``serve(..., require_auth=True)`` every
  state-changing request must send ``Authorization: Bearer <token>``. The
  token is provided by the caller (env ``J_BROWSER_BRIDGE_TOKEN``) or
  auto-generated per server. The G6 extension client sends this token.

The backend is pluggable (see backend.py). Default is the deterministic
EchoBackend so the AI layer works end-to-end without a kernel attached.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from backend import KernelBackend, make_backend

logger = logging.getLogger("jbrowser-bridge")


def _agent_capable(backend) -> bool:
    """An agent task can only stream through a kernel backend with an engine."""
    return isinstance(backend, KernelBackend) and getattr(backend, "engine", None) is not None

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8170
TOKEN_ENV = "J_BROWSER_BRIDGE_TOKEN"

_SAFE_ORIGINS = re.compile(r"^chrome-extension://[a-p]{32}$")
_SAFE_ORIGIN = "chrome-extension://"


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "JBrowserBridge/0.1.0"
    backend: object = None  # injected by server factory
    auth_token: str | None = None  # injected; None => auth not required

    # ── CORS / plumbing ────────────────────────────────────────────────────
    def _cors(self, origin: str | None) -> None:
        """Restrict CORS to JARVIS Orbit chrome-extension origins."""
        safe = origin if (origin and _SAFE_ORIGINS.match(origin)) else None
        if safe:
            self.send_header("Access-Control-Allow-Origin", safe)
            self.send_header("Vary", "Origin")
        else:
            # No Origin (direct call) or untrusted origin: no CORS allowance.
            self.send_header("Access-Control-Allow-Origin", "")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "content-type, authorization")

    def _authorized(self) -> bool:
        """Enforce bearer-token auth when a token is configured."""
        if self.auth_token is None:
            return True
        expected = f"Bearer {self.auth_token}"
        return self.headers.get("Authorization") == expected

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors(self.headers.get("Origin"))
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
        self._cors(self.headers.get("Origin"))
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/status":
            self._json(200, self.backend.status())
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._json(401, {"ok": False, "error": "unauthorized", "code": "unauthorized"})
            return
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
    def _stream_chat(self, session_id: str, messages: list,
                     page: dict | None) -> None:
        """Emit the backend's stream as SSE, catching engine failures."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors(self.headers.get("Origin"))
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
        self._stream_chat(session_id, messages, page)

    def _agent(self) -> None:
        """Launch a JARVIS agent task (DSH-style) over the kernel engine.

        Real only when the backend is a kernel backend with an attached
        engine; otherwise this remains the Phase-3 seam and answers 501 so a
        silent downgrade is impossible (fail closed).
        """
        if not _agent_capable(self.backend):
            self._read_json()  # drain the body so the client reads a clean 501
            self._json(501, {
                "ok": False,
                "code": "not_implemented",
                "message": "agent endpoint needs a kernel backend with an engine attached",
            })
            return
        data = self._read_json()
        if data is None:
            self._json(400, {"ok": False, "error": "invalid json body"})
            return
        task = str(data.get("task") or data.get("text") or "").strip()
        messages = data.get("messages") or []
        if not messages:
            if not task:
                self._json(400, {"ok": False, "error": "missing 'task'"})
                return
            messages = [{"role": "user", "content": task}]
        session_id = str(data.get("session_id") or "anon")
        page = data.get("page")
        self._stream_chat(session_id, messages, page)

    def _cdp(self) -> None:
        """Permanently 501: NOT a raw control path.

        Browser control is performed only through JARVIS tools
        (ToolExecutionService -> BrowserController -> CDP), never through this
        endpoint. This guard prevents a second execution/control surface.
        """
        self._read_json()  # drain the request body so the client reads a clean 501
        self._json(501, {
            "ok": False,
            "code": "not_implemented",
            "message": "cdp endpoint is intentionally closed; control goes through JARVIS tools only",
        })


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
          backend_kind: str = "echo", engine=None,
          require_auth: bool = False, auth_token: str | None = None,
          ) -> ThreadingHTTPServer:
    """Start the bridge server.

    ``require_auth=True`` enables bearer-token auth: the token is taken from
    ``auth_token`` or the ``J_BROWSER_BRIDGE_TOKEN`` env var, or auto-generated
    (available via ``httpd.bridge_token``). The G6 extension client sends this
    token on every state-changing request.
    """
    backend = make_backend(backend_kind, engine=engine)
    token = None
    if require_auth:
        token = auth_token or os.environ.get(TOKEN_ENV) or secrets.token_hex(16)
    handler = type(
        "JBridgeHandler", (BridgeHandler,),
        {"backend": backend, "auth_token": token},
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.bridge_token = token
    httpd.daemon_threads = True
    return httpd


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="J-Browser bridge server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--backend", default="echo",
                        choices=["echo", "kernel"])
    parser.add_argument("--auth", action="store_true",
                        help="require bearer-token auth (J_BROWSER_BRIDGE_TOKEN or generated)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        stream=sys.stdout,
    )
    httpd = serve(args.host, args.port, backend_kind=args.backend,
                  require_auth=args.auth)
    logger.info("JBrowserBridge listening on http://%s:%d backend=%s auth=%s",
                args.host, args.port, args.backend,
                "on" if args.auth else "off")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
