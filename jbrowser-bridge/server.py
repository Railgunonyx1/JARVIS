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
* ``echo``    â€” deterministic offline stub (default; no kernel required).
* ``kernel``  â€” drives the real JARVIS stack through a ``StreamEngine``
  (see engine.py). ``serve(..., backend_kind="kernel", engine=engine)``:
  the default ``ModelGatewayEngine`` streams chat through the JARVIS model
  gateway (ProviderRouter fallback) with input/output budgets. Supply
  :class:`agent.AgentEngine` for task-driven (DSH-style) browsing.

Security (G1 hardenings)
------------------------
* Loopback-only bind (127.0.0.1).
* CORS restricted to ``chrome-extension://`` origins â€” never ``*``.
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

from voice import _clamp_speed, stt_bytes, voice_status, _tts_one, _header_safe

logger = logging.getLogger("jbrowser-bridge")


def _agent_capable(backend) -> bool:
    """An agent task can only stream through a kernel backend with an engine."""
    return isinstance(backend, KernelBackend) and getattr(backend, "engine", None) is not None

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8170
TOKEN_ENV = "J_BROWSER_BRIDGE_TOKEN"

# Canonical per-installation token: env override, else the launcher's token
# file (same resolution as the WS bridge and Electron main â€” one secret).
_TOKEN_FILE = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "JARVIS", "bridge-token",
)


def _resolve_token() -> str | None:
    tok = (os.environ.get(TOKEN_ENV) or "").strip()
    if tok:
        return tok
    try:
        with open(_TOKEN_FILE, encoding="utf-8") as fh:
            tok = fh.read().strip()
        return tok or None
    except OSError:
        return None

_SAFE_ORIGINS = re.compile(r"^chrome-extension://[a-p]{32}$")
_SAFE_ORIGIN = "chrome-extension://"


class BridgeHandler(BaseHTTPRequestHandler):
    server_version = "JBrowserBridge/0.1.0"
    backend: object = None  # injected by server factory
    auth_token: str | None = None  # injected; None => auth not required

    # â”€â”€ CORS / plumbing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _cors(self, origin: str | None) -> None:
        """Restrict CORS to JARVIS Orbit chrome-extension origins.

        The renderer itself is file:// (Origin: null) and dsh-native fetches
        the kernel from there; with mandatory bearer auth on every route,
        CORS is defense-in-depth only â€” the token is the real boundary.
        """
        safe = origin if (origin and _SAFE_ORIGINS.match(origin)) else None
        if safe is None and origin == "null":
            safe = origin
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

    def _host_ok(self) -> bool:
        """Reject requests whose Host header is not loopback.

        DNS-rebinding defense: a rebound hostname (attacker.com -> 127.0.0.1)
        arrives with a non-loopback Host header. Everything legitimate binds
        to 127.0.0.1/localhost. Applied to every state-changing and read
        route, including GETs (models list leaks provider configuration).
        """
        host = (self.headers.get("Host") or "").split(":")[0].strip().lower()
        return host in ("127.0.0.1", "localhost")

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        # Protocol hygiene: a POST that is rejected BEFORE its body is read
        # (401/403 on the auth/host gate) leaves bytes unread on a keep-alive
        # socket. Closing with unread data makes Windows abort the connection
        # (RST, WinError 10053): the client dies on the read instead of
        # receiving the 401/403 it is owed (measured: test_posts_require_token
        # failed with ConnectionAbortedError). Draining the body first lets
        # the rejection be delivered cleanly.
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length > 0 and not getattr(self, "_body_consumed", False):
            try:
                self.rfile.read(min(length, 1 << 20))  # 1MB drain cap
                self._body_consumed = True
            except OSError:
                pass
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
        self._body_consumed = True
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def log_message(self, fmt: str, *args) -> None:
        logger.debug(fmt, *args)

    # â”€â”€ HTTP verbs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors(self.headers.get("Origin"))
        self.end_headers()

    def _tts(self) -> None:
        """POST /v1/tts — render speech audio from text.

        Request body: {"text": str, "speed": float} (speed clamped to
        ``SPEED_MIN..SPEED_MAX``, default 1.0).

        Response: 200 JSON {"ok": True, "engine": str, "audio_b64": str};
        400 invalid body; 401 unauth; 500 when TTS fails.
        """
        if not self._host_ok():
            self._json(403, {"ok": False, "error": "forbidden host"})
            return
        if not self._authorized():
            self._json(401, {"ok": False, "error": "unauthorized", "code": "unauthorized"})
            return
        data = self._read_json()
        if data is None:
            self._json(400, {"ok": False, "error": "invalid json body"})
            return
        text = str(data.get("text") or "").strip()
        if not text:
            self._json(400, {"ok": False, "error": "text is required"})
            return
        speed = _clamp_speed(data.get("speed", 1.0))
        # Optional engine pin from the voice menu ("auto" keeps the default
        # chain). Unknown names fall back inside ``_select_tts_engine``.
        voice_model = str(data.get("voice_model") or "auto").strip().lower() or "auto"
        # Kokoro voice id ("af_sarah", "bm_george", ...). Empty means the
        # engine default; engines without a voice parameter ignore it.
        voice_name = str(data.get("voice") or "").strip()
        try:
            data_b, mime, engine_used = _tts_one(
                text, speed=speed, engine_name=voice_model, voice=voice_name)
        except Exception:  # noqa: BLE001
            logger.exception("tts failed")
            self._json(500, {"ok": False, "error": "tts failed", "code": "tts_failed", "engine": "sapi"})
            return
        format_raw = str(data.get("format", "json")).lower() == "raw"
        if format_raw:
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("X-Voice-Engine", _header_safe(engine_used))
            self.send_header("Content-Length", str(len(data_b)))
            self.end_headers()
            try:
                self.wfile.write(data_b)
            except (BrokenPipeError, ConnectionResetError,
                    ConnectionAbortedError, TimeoutError, OSError):
                pass
        else:
            import base64 as _b64
            self._json(200, {"ok": True, "engine": engine_used, "audio_b64": _b64.b64encode(data_b).decode()})

    def _stt(self) -> None:
        """POST /v1/stt — transcribe audio bytes to text.

        Request body: JSON {"audio_b64": str, "filename": str} (audio_b64 is
        base64-encoded audio). The filename defaults to ``audio.webm``.

        Response: 200 JSON {"ok": True, "text": str}; 400 invalid body;
        401 unauth; 503 when STT cannot run (no API key / unavailable engine).
        """
        if not self._host_ok():
            self._json(403, {"ok": False, "error": "forbidden host"})
            return
        if not self._authorized():
            self._json(401, {"ok": False, "error": "unauthorized", "code": "unauthorized"})
            return
        data = self._read_json()
        if data is None:
            self._json(400, {"ok": False, "error": "invalid json body"})
            return
        audio_b64 = data.get("audio_b64")
        if not audio_b64:
            self._json(400, {"ok": False, "error": "audio_b64 is required"})
            return
        filename = data.get("filename", "audio.webm")
        try:
            import base64 as _b64
            raw = _b64.b64decode(audio_b64)
        except Exception as exc:  # noqa: BLE001
            logger.debug("stt: undecodable audio_b64: %s", exc)
            self._json(400, {"ok": False, "error": "invalid audio_b64"})
            return
        if len(raw) < 100:
            self._json(400, {"ok": False, "error": "audio too short"})
            return
        try:
            text = stt_bytes(raw, filename=filename)
        except Exception:  # noqa: BLE001
            logger.exception("stt failed")
            self._json(503, {"ok": False, "error": "ELEVENLABS_API_KEY not configured", "code": "stt_unavailable"})
            return
        self._json(200, {"ok": True, "text": text})

    def _voice_status(self) -> None:
        """GET /v1/voice/status — bridge voice subsystem status.

        Response: 200 JSON status payload from :func:`voice_status` plus
        voice menu capability metadata (engine list, precision, speed range).
        """
        if not self._host_ok():
            self._json(403, {"ok": False, "error": "forbidden host"})
            return
        status = voice_status()
        # ``voice_status()`` already reports the live engine chain and the
        # clamped speed range; the renderer only needs it under a stable
        # ``voice_menu`` key. Deriving the engine list from
        # ``_resolve_tts_engine()`` would be wrong anyway: that returns a
        # single callable, not an iterable of engines.
        chain = status.get("tts_chain") or ["sapi"]
        status["voice_menu"] = {
            "engines": list(chain),
            "default": "auto",
            "speed_range": status.get("speed_range", [0.5, 2.0]),
        }
        self._json(200, status)

    # ── CORS / plumbing

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_ok():
            self._json(403, {"ok": False, "error": "forbidden host"})
            return
        if not self._authorized():
            self._json(401, {"ok": False, "error": "unauthorized", "code": "unauthorized"})
            return
        if self.path == "/status":
            self._json(200, self.backend.status())
            return
        if self.path == "/v1/models":
            self._models()
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_ok():
            self._json(403, {"ok": False, "error": "forbidden host"})
            return
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
        if self.path == "/v1/tts":
            self._tts()
            return
        if self.path == "/v1/stt":
            self._stt()
            return
        if self.path == "/v1/voice/status":
            self._voice_status()
            return
        self._json(404, {"ok": False, "error": "not found"})

    # â”€â”€ endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def _models(self) -> None:
        """GET /v1/models â€” selectable models for the browser model picker.

        Reads availability live from the engine's router (config models +
        dynamic Ollama tags). Answers with an empty list rather than failing
        when no kernel engine is attached, so the UI still renders.
        """
        models: list[dict] = []
        engine = getattr(self.backend, "engine", None)
        if engine is not None and hasattr(engine, "_models"):
            try:
                models = engine._models()
            except Exception:  # noqa: BLE001
                models = []
        self._json(200, {"ok": True, "models": models})

    def _stream_chat(self, session_id: str, messages: list,
                     page: dict | None, model: str | None = None) -> None:
        """Emit the backend's stream as SSE, catching engine failures.

        Emits a trailing ``meta`` event with the provider that actually served
        the reply and the end-to-end latency, so the UI can show real provenance.

        **Queue-based decoupling.** ``emit()`` pushes SSE events to a
        ``threading.Queue`` instead of writing directly to the socket.  A
        dedicated *drain* thread on the **handler** thread pops events and
        performs the blocking ``wfile.write`` + ``wfile.flush``.  This keeps
        the shared async loop free â€” a slow-reading SSE client now only
        stalls its own drain thread, never every other concurrent chat.
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors(self.headers.get("Origin"))
        self.end_headers()

        import queue
        import threading
        import time as _time

        _DONE = object()
        event_queue: queue.Queue = queue.Queue()

        def emit(event: dict) -> None:
            event_queue.put(event)

        def _drain() -> None:
            """Pop SSE events and write them to the client socket.

            Runs on the **handler** thread (separate from the shared async
            loop).  The queue blocks on ``get()`` until the next event or
            ``_DONE`` sentinel arrives; ``wfile.flush()`` applies natural
            back-pressure that now only affects this drain thread and the
            client it serves â€” never the loop.
            """
            while True:
                ev = event_queue.get()
                if ev is _DONE:
                    break
                try:
                    self.wfile.write(b"data: " + json.dumps(ev).encode("utf-8") + b"\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError,
                        ConnectionAbortedError, TimeoutError, OSError):
                    # ConnectionAbortedError is a Windows-specific abort
                    # (WinError 10053) â€” a sibling of, not a subclass of,
                    # the reset/broken errors. Any of these means the
                    # client is gone; stop draining. OSError is the
                    # umbrella for exotic socket teardowns.
                    break

        drain_thread = threading.Thread(
            target=_drain, daemon=True, name="sse-drain",
        )
        drain_thread.start()

        started = _time.monotonic()
        try:
            self.backend.stream_chat(session_id, messages, page, emit, model=model)
        except Exception as exc:  # noqa: BLE001
            logger.exception("chat backend error")
            emit({"type": "error", "message": str(exc)[:500], "code": "backend_error"})
        finally:
            # Provenance + latency AFTER the terminal event, so clients that
            # treat the first error/done as final still work and tests that
            # assert events[-1] type are unaffected (meta is trailing info).
            try:
                import engine as _eng
                router_obj = _eng._router_cache
                last = (
                    (router_obj._last_provider, router_obj._last_model)
                    if router_obj is not None else None
                )
            except Exception:
                last = None
            latency_ms = int((_time.monotonic() - started) * 1000)
            meta: dict = {"latency_ms": latency_ms}
            if last and last[0]:
                meta["provider"] = last[0]
                meta["model"] = f"{last[0]}/{last[1]}" if last[1] else last[0]
            emit({"type": "meta", **meta})
            event_queue.put(_DONE)
            drain_thread.join(timeout=2.0)
        # SSE streams end with the "done"/"error" event; close the connection
        # so clients that also read to EOF release cleanly.
        self.close_connection = True

    def _chat(self) -> None:
        data = self._read_json()
        if data is None:
            self._json(400, {"ok": False, "error": "invalid json body"})
            return
        messages = data.get("messages") or []
        text = str(data.get("text") or "").strip()
        if text:
            # Append the current turn to the prior thread (if the client sent
            # one) instead of REPLACING it â€” this is what gives the model
            # conversation continuity across calls.
            messages = list(messages) + [{"role": "user", "content": text}]
        if not messages:
            messages = [{"role": "user", "content": "(empty request)"}]
        session_id = str(data.get("session_id") or "anon")
        page = data.get("page")
        model = data.get("model") or None
        self._stream_chat(session_id, messages, page, model)

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
        token = auth_token or _resolve_token() or secrets.token_hex(16)
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
    parser.add_argument("--auth", action="store_true", default=True,
                        help="require bearer-token auth (J_BROWSER_BRIDGE_TOKEN or generated); ON by default")
    parser.add_argument("--no-auth", action="store_false", dest="auth",
                        help="explicitly disable bearer auth (development only)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    # UTF-8 stdout handler: on Windows the default cp1252 console codec
    # crashes logging on unicode (provider names use "\u2192" arrows), which
    # raised inside logging and noise-killed handler threads mid-request.
    handler = logging.StreamHandler(
        open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)
    )
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        handlers=[handler],
    )
    # A `kernel` backend is only real intelligence when an engine is attached.
    # ModelGatewayEngine is the default chat engine (lazy provider import â€”
    # constructing it never loads the model stack; if no provider is usable the
    # first chat turn fails closed with a clear SSE error instead of silently).
    engine = None
    if args.backend == "kernel":
        try:
            from engine import ModelGatewayEngine
            engine = ModelGatewayEngine()
            logger.info("kernel backend attached with engine=%s", engine.name)
            # Warm eagerly at boot: the router build (~3s) plus provider SDK
            # imports (~8s) must land during startup, not on the first hello
            # (which would otherwise pay 10s+ of TTFT). Background thread â€”
            # the server binds and answers /status immediately.
            import threading
            def _warm() -> None:
                try:
                    import engine as _eng
                    router = _eng._get_router()
                    router.warm()
                    logger.info("provider warmup complete (SDKs imported)")
                    # TTFT prewarm: open the TLS/TCP connection to the top
                    # race providers with a 1-token ping so the first REAL
                    # message skips the ~1-2s connection handshake and any
                    # per-key first-request overhead. Failures are fine â€”
                    # the connection cache is per-client and a 429 still
                    # establishes the socket.
                    import asyncio
                    async def _ping(name: str) -> None:
                        try:
                            provider = router._providers.get(name)
                            if provider is None:
                                return
                            # Consume the FULL (2-token) stream: breaking after
                            # the first chunk abandons the SSE response mid-
                            # flight, the HTTP connection cannot return to the
                            # pool, and the "prewarm" warms nothing (measured:
                            # first real message still paid a 2.2s reconnect).
                            async for _ in provider.complete_stream(
                                [{"role": "user", "content": "1"}],
                                "reply with the single character: 1", 2,
                            ):
                                pass
                        except Exception:
                            pass
                    async def _ping_all() -> None:
                        # Quota-aware keepalive target: ping ONE provider â€”
                        # the highest-priority available one whose free-tier
                        # quotas comfortably absorb a 2-token ping every 3
                        # minutes (>=15 RPM and >=5,000 RPD). OpenRouter's
                        # 200-req/day pool cannot absorb 480 pings/day; Groq's
                        # 28,800/day barely notices. _ping drains the stream
                        # fully so the connection actually returns to the pool.
                        for name in router._get_available_chain():
                            p = router._providers.get(name)
                            cfg = getattr(p, "config", {}) or {}
                            rpm = cfg.get("requests_per_minute", 0) or 0
                            rpd = cfg.get("requests_per_day", 0) or 0
                            if rpm >= 15 and rpd >= 5000:
                                await _ping(name)
                                return

                    async def _warm_engine_path() -> None:
                        # Drain ONE stream through the engine's REAL dispatch
                        # path (_race_providers -> router.complete_stream ->
                        # sticky bookkeeping) â€” the provider pings above warm
                        # sockets but skip the router/race machinery entirely,
                        # so the first real message paid that machinery's
                        # first-run cost (measured: boot-edge turn ~2-3s even
                        # after connection prewarm). Runs at boot only; the
                        # keepalive below needs sockets, not machinery.
                        import engine as _e
                        stream = _e._race_providers(
                            router,
                            [{"role": "user", "content": "1"}],
                            "reply with the single character: 1", 2, None)
                        async for _ in stream:
                            pass
                    # CRITICAL: pings must run on the engine's SHARED loop.
                    # asyncio.run() here would warm connections owned by a
                    # throwaway loop's HTTP clients â€” useless to the message
                    # path, which runs on _get_shared_loop() (measured: first
                    # turn after idle still paid a 2.1s reconnect with the
                    # old throwaway-loop prewarm).
                    try:
                        import engine as _eng_warm
                        loop = _eng_warm._get_shared_loop()
                        futures = asyncio.run_coroutine_threadsafe(
                            _ping_all(), loop)
                        futures.result(timeout=90)
                        logger.info("TTFT prewarm complete (shared-loop connections open)")
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("TTFT prewarm skipped: %s", exc)

                    # Engine-path warmup: same shared loop, runs the race
                    # machinery once so turn 1 skips its first-run cost.
                    try:
                        import engine as _eng_warm2
                        loop2 = _eng_warm2._get_shared_loop()
                        fut2 = asyncio.run_coroutine_threadsafe(
                            _warm_engine_path(), loop2)
                        fut2.result(timeout=90)
                        logger.info("engine-path warmup complete (race machinery exercised)")
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("engine-path warmup skipped: %s", exc)

                    # Keepalive: provider idle timeouts close pooled TLS
                    # connections after a few minutes; the next real message
                    # then pays a fresh handshake (measured 600-2100ms). Re-ping
                    # the top chain providers well inside that window.
                    import threading as _th
                    def _keepalive() -> None:
                        import time as _time
                        import engine as _eng_ka
                        loop_ka = _eng_ka._get_shared_loop()
                        # Ping-FIRST cadence: first ping at ~t+10s lands well
                        # inside the boot prewarm connection's 30s
                        # keepalive_expiry, refreshing it before eviction. The
                        # old sleep(30)+sleep(25)-then-ping order left a dead
                        # zone (~t+50..55s) where the prewarm connection had
                        # expired but no ping had run yet â€” a turn there paid
                        # the full ~2.1-3s reconnect (re-measured at t+45s).
                        _time.sleep(10)
                        while True:
                            try:
                                f = asyncio.run_coroutine_threadsafe(
                                    _ping_all(), loop_ka)
                                f.result(timeout=60)
                                logger.debug("provider keepalive ping ok")
                            except Exception:  # noqa: BLE001
                                pass
                            # 25s interval: pairs with the provider SDK pools'
                            # 30s keepalive_expiry â€” each ping refreshes a
                            # connection that is never older than ~25s, so a
                            # real turn NEVER finds a connection in the
                            # 30s-eviction zone. 2880 pings/day â‰ˆ 10% of
                            # groq's 28,800/day free quota.
                            _time.sleep(25)
                    _th.Thread(target=_keepalive, daemon=True,
                               name="bridge-provider-keepalive").start()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("provider warmup failed: %s", exc)
            threading.Thread(target=_warm, daemon=True, name="bridge-warmup").start()
        except Exception as exc:  # noqa: BLE001 - degrade to hollow, never crash
            logger.error("could not attach kernel engine (%s); serving hollow", exc)
    httpd = serve(args.host, args.port, backend_kind=args.backend,
                  engine=engine, require_auth=args.auth)
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
