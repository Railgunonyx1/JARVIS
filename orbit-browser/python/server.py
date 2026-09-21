#!/usr/bin/env python3
"""JARVIS Orbit — WebSocket Bridge Server.

Bridges the Electron browser to the JARVIS backend via WebSocket.
This server:
1. Requires the per-launch bearer token (J_BROWSER_BRIDGE_TOKEN env) in the
   WebSocket subprotocol and an allowed Origin (Electron file:// => null)
2. Forwards to the token-authenticated kernel bridge (HTTP/SSE on 8170)
3. Translates between WebSocket ↔ HTTP/SSE

Usage:
    J_BROWSER_BRIDGE_TOKEN=<token> python orbit-browser/python/server.py \
        --port 8171 --bridge-port 8170
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    import websockets
    from websockets.server import serve
except ImportError:
    print("ERROR: websockets not installed. Run: pip install websockets")
    sys.exit(1)


# ── Configuration ──────────────────────────────────────────────────
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8170
WS_HOST = "127.0.0.1"
WS_PORT = 8171

import os  # noqa: E402 — token env read

# ── Handshake security (A-01) ─────────────────────────────────────────
# Browsers do not apply CORS to WebSocket upgrades, so any web page can
# attempt ws://127.0.0.1:8171. Defense: (1) require the per-launch bearer
# token in the subprotocol field — a page cannot know it; (2) reject any
# Origin header that is not the Orbit app's own.
ORBIT_TOKEN_ENV = "J_BROWSER_BRIDGE_TOKEN"

# Canonical per-installation token: env override, else the launcher's token
# file. Every component resolves the token the SAME way, so a stale env on
# one spawn chain (PowerShell -> cmd -> Electron) can never split the
# secret between services and put the status indicator in a reconnect loop.
_TOKEN_FILE = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "JARVIS", "bridge-token",
)


def _resolve_token() -> str | None:
    tok = (os.environ.get(ORBIT_TOKEN_ENV) or "").strip()
    if tok:
        return tok
    try:
        with open(_TOKEN_FILE, "r", encoding="utf-8") as fh:
            tok = fh.read().strip()
        return tok or None
    except OSError:
        return None
_ALLOWED_ORIGINS = {
    "http://localhost:8172", "https://localhost:8172",
    "http://127.0.0.1:8172",
    "null",  # Electron main-window loads are file:// (Origin: null)
    "",      # Non-browser clients (Node ws) send no Origin header at all
}
_SUBPROTOCOL = "orbit-v1"
_MAX_TEXT = 64 * 1024  # 64KB per message
_MAX_CLIENTS = 8


class JarvisBridge:
    """WebSocket bridge between Electron and JARVIS backend."""

    _all_clients: set = set()  # class-level: connection cap spans instances

    # Polling cadence for the shared watchdog. Long enough to stay invisible
    # (2s x ~1 HTTP call ≈ 43k/day for 8 clients — bounded by _MAX_CLIENTS=8),
    # short enough that a kernel death is pushed to clients in seconds. The
    # RENDERER never polls at a fixed rate; it receives these pushes (spec
    # rule: "Renderer does not poll JARVIS. Events only.").
    _WATCHDOG_INTERVAL_S = 2.0

    def __init__(self, bridge_url: str):
        self.bridge_url = bridge_url
        self.clients: set = set()
        self.session_id: str = f"orbit-{int(time.time())}"
        self._bridge_ok = False

    def _check_bridge(self) -> bool:
        """Check if the JARVIS bridge is running (token-authenticated)."""
        try:
            req = Request(f"{self.bridge_url}/status", headers=_bridge_headers())
            with urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read())
            self._bridge_ok = data.get("ok", False)
            return self._bridge_ok
        except Exception:
            self._bridge_ok = False
            return False

    async def _broadcast_status(self, ok: bool) -> None:
        """Push a status transition to every connected client.

        The watchdog owns kernel-death detection; the renderer receives
        events instead of polling. Send failures drop the payload — the
        dead socket's own close path handles cleanup.
        """
        dead: list = []
        msg = json.dumps({
            "type": "status",
            "payload": {
                "ok": ok,
                "kernel": "online" if ok else "offline",
                "session": self.session_id,
                "bridge": self.bridge_url,
            },
        })
        for ws in list(JarvisBridge._all_clients):
            try:
                await ws.send(msg)
            except Exception:  # noqa: BLE001 - dead socket, close path handles it
                dead.append(ws)
        for ws in dead:
            JarvisBridge._all_clients.discard(ws)

    async def _status_watchdog(self) -> None:
        """One shared watchdog: pushes transitions only (edge-triggered).

        Replaces per-renderer 5s HTTP polling: previously only the initial
        connect message caught kernel death, so the renderer kept its own
        poll. One poller per BRIDGE process, transitions pushed to all —
        ~0 cost when the kernel state is stable.
        """
        while True:
            await asyncio.sleep(self._WATCHDOG_INTERVAL_S)
            if not JarvisBridge._all_clients:
                continue  # nobody listening; skip the probe entirely
            ok = await asyncio.get_event_loop().run_in_executor(
                None, self._check_bridge)
            if ok != self._bridge_ok:
                print(f"[BRIDGE] Kernel {'online' if ok else 'offline'} - pushing transition")
                await self._broadcast_status(ok)

    async def register(self, websocket):
        JarvisBridge._all_clients.add(websocket)
        self.clients.add(websocket)
        print(f"[BRIDGE] Client connected ({len(JarvisBridge._all_clients)} total)")
        # Check bridge status
        bridge_ok = await asyncio.get_event_loop().run_in_executor(None, self._check_bridge)

        await websocket.send(json.dumps({
            "type": "status",
            "payload": {
                "ok": bridge_ok,
                "kernel": "online" if bridge_ok else "offline",
                "session": self.session_id,
                "bridge": self.bridge_url,
            },
        }))

    async def unregister(self, websocket):
        JarvisBridge._all_clients.discard(websocket)
        self.clients.discard(websocket)
        print(f"[BRIDGE] Client disconnected ({len(JarvisBridge._all_clients)} total)")

    async def handle_message(self, websocket, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.send(json.dumps({
                "type": "error",
                "payload": {"message": "Invalid JSON"},
            }))
            return

        msg_type = msg.get("type", "")
        payload = msg.get("payload", {})

        if msg_type == "chat_request":
            await self.handle_chat(websocket, payload)
        elif msg_type == "agent_task":
            await self.handle_agent_task(websocket, payload)
        elif msg_type == "status_request":
            await self.handle_status(websocket)
        else:
            print(f"[BRIDGE] Unknown message type: {msg_type}")

    async def handle_chat(self, websocket, payload: dict):
        """Stream chat to the browser as tokens arrive (not after full gen).

        The kernel's SSE deltas are forwarded live: each delta becomes a
        ``chat_reply`` with kind ``delta``; ``done`` carries the accumulated
        text. During first-token silence a single ``ack`` is emitted after
        ``_ACK_AFTER_S`` so the user sees pickup instead of a dead spinner.
        The blocking HTTP/SSE read runs in an executor; parsed events cross
        to this event loop through a thread-safe queue.
        """
        text = payload.get("text", "")
        session = payload.get("sessionId", self.session_id)
        ACK_AFTER_S = 1.5

        print(f"[BRIDGE] Chat: {text[:50]}...")

        await websocket.send(json.dumps({
            "type": "agent_event",
            "payload": {"state": "thinking"},
        }))

        if not self._bridge_ok:
            await asyncio.sleep(0.5)
            await websocket.send(json.dumps({
                "type": "agent_event",
                "payload": {"state": "planning"},
            }))
            await asyncio.sleep(0.5)
            await websocket.send(json.dumps({
                "type": "chat_reply",
                "payload": {
                    "kind": "done",
                    "text": (
                        "I'm JARVIS, your browser intelligence layer.\n\n"
                        "The JARVIS backend is not currently connected. "
                        "To enable full functionality:\n\n"
                        "1. Start the JARVIS kernel: `python -m cli`\n"
                        "2. Or run: `python jbrowser-bridge/server.py --backend kernel`\n\n"
                        "Once the backend is running, I can help you research, "
                        "summarize, remember, and act on web content."
                    ),
                    "session": session,
                },
            }))
            await websocket.send(json.dumps({
                "type": "agent_event",
                "payload": {"state": "idle"},
            }))
            return

        loop = asyncio.get_running_loop()
        events = asyncio.Queue()

        def _pump() -> None:
            """Blocking SSE read on a worker thread; posts events to the queue."""
            try:
                data = json.dumps({"text": text, "session": session}).encode()
                req = Request(
                    f"{self.bridge_url}/v1/chat",
                    data=data,
                    headers={"Content-Type": "application/json", **_bridge_headers()},
                    method="POST",
                )
                with urlopen(req, timeout=120) as resp:
                    buf = ""
                    while True:
                        chunk = resp.read(1024)
                        if not chunk:
                            break
                        buf += chunk.decode("utf-8", "replace")
                        while "\n" in buf:
                            line, buf = buf.split("\n", 1)
                            line = line.strip()
                            if not line.startswith("data: "):
                                continue
                            try:
                                ev = json.loads(line[6:])
                            except json.JSONDecodeError:
                                continue
                            loop.call_soon_threadsafe(events.put_nowait, ev)
                loop.call_soon_threadsafe(events.put_nowait, None)  # EOF
            except Exception as e:  # noqa: BLE001 - report to the client
                print(f"[BRIDGE] Chat error: {e}")
                loop.call_soon_threadsafe(events.put_nowait, {
                    "type": "__exc", "message": str(e),
                })

        async def _send(obj):
            try:
                await websocket.send(json.dumps(obj))
                return True
            except Exception:  # noqa: BLE001 - client vanished mid-stream
                return False

        loop.run_in_executor(None, _pump)

        parts = []
        failed = False
        client_gone = False
        ack_deadline = loop.time() + ACK_AFTER_S
        acked = False

        while True:
            timeout = max(ack_deadline - loop.time(), 0.01) if not acked else None
            try:
                ev = await asyncio.wait_for(events.get(), timeout=timeout)
            except asyncio.TimeoutError:
                # Deadline decision is over whether or not we acked — stop
                # computing short timeouts (a 10ms poll loop otherwise spins
                # between late deltas for the rest of the turn).
                acked = True
                if not parts:  # still no first token: acknowledge pickup once
                    client_gone = not await _send({
                        "type": "chat_reply",
                        "payload": {
                            "kind": "ack",
                            "text": "On it — working on that now…",
                            "session": session,
                        },
                    })
                    if client_gone:
                        break
                continue
            if ev is None:  # SSE EOF without an explicit done/error
                if not parts:
                    client_gone = not await _send({
                        "type": "chat_reply",
                        "payload": {
                            "kind": "error",
                            "error": {"message": "No response from JARVIS backend"},
                            "session": session,
                        },
                    })
                break
            et = ev.get("type")
            if et == "__exc":
                client_gone = not await _send({
                    "type": "chat_reply",
                    "payload": {
                        "kind": "error",
                        "error": {"message": ev.get("message", "backend error")},
                        "session": session,
                    },
                })
                failed = True
                break
            if et == "delta":
                parts.append(ev.get("text", ""))
                client_gone = not await _send({
                    "type": "chat_reply",
                    "payload": {"kind": "delta", "text": ev.get("text", ""), "session": session},
                })
                if client_gone:
                    break
            elif et == "done":
                break
            elif et == "error":
                client_gone = not await _send({
                    "type": "chat_reply",
                    "payload": {
                        "kind": "error",
                        "error": {"message": ev.get("message", "backend error")},
                        "session": session,
                    },
                })
                failed = True
                break
            # start/meta and any other event types are consumed silently

        if not client_gone:
            if parts and not failed:
                await _send({
                    "type": "agent_event",
                    "payload": {"state": "running"},
                })
                await _send({
                    "type": "chat_reply",
                    "payload": {"kind": "done", "text": "".join(parts), "session": session},
                })
            await _send({
                "type": "agent_event",
                "payload": {"state": "idle"},
            })

    async def handle_agent_task(self, websocket, payload: dict):
        """Forward agent task to the real JARVIS bridge."""
        goal = payload.get("goal", "")
        session = payload.get("sessionId", self.session_id)

        print(f"[BRIDGE] Agent task: {goal[:50]}...")

        if not self._bridge_ok:
            await websocket.send(json.dumps({
                "type": "chat_reply",
                "payload": {
                    "kind": "error",
                    "error": {"message": "JARVIS backend not connected"},
                    "session": session,
                },
            }))
            return

        # Forward to real bridge (blocking HTTP read runs off the event loop)
        try:
            events = await asyncio.get_event_loop().run_in_executor(
                None, self._forward_agent_task, goal, session
            )
            if events is None:
                await websocket.send(json.dumps({
                    "type": "chat_reply",
                    "payload": {
                        "kind": "error",
                        "error": {"message": "No response from JARVIS backend"},
                        "session": session,
                    },
                }))
                return
            for event in events:
                await websocket.send(json.dumps({
                    "type": "agent_event",
                    "payload": event,
                }))
        except Exception as e:
            print(f"[BRIDGE] Agent task error: {e}")
            await websocket.send(json.dumps({
                "type": "chat_reply",
                "payload": {
                    "kind": "error",
                    "error": {"message": str(e)},
                    "session": session,
                },
            }))

    def _forward_agent_task(self, goal: str, session: str) -> list | None:
        """Forward agent task to the real JARVIS bridge via HTTP POST.

        Contract (A-02): the kernel endpoint reads ``task``/``text`` and
        ``session_id`` — not the legacy ``goal``/``session`` pair.
        """
        try:
            data = json.dumps({
                "task": goal,
                "session_id": session,
            }).encode()

            req = Request(
                f"{self.bridge_url}/v1/agent",
                data=data,
                headers={"Content-Type": "application/json", **_bridge_headers()},
                method="POST",
            )

            events: list = []
            with urlopen(req, timeout=120) as resp:
                for line in resp.read().decode().split("\n"):
                    if line.startswith("data: "):
                        try:
                            events.append(json.loads(line[6:]))
                        except json.JSONDecodeError:
                            continue
            return events or None
        except Exception as e:
            print(f"[BRIDGE] Agent task HTTP error: {e}")
            return None

    async def handle_status(self, websocket):
        """Check and return bridge status."""
        bridge_ok = await asyncio.get_event_loop().run_in_executor(None, self._check_bridge)
        await websocket.send(json.dumps({
            "type": "status",
            "payload": {
                "ok": bridge_ok,
                "kernel": "online" if bridge_ok else "offline",
                "session": self.session_id,
                "bridge": self.bridge_url,
            },
        }))


def _bridge_headers() -> dict:
    """Outbound auth headers for kernel HTTP calls (canonical token)."""
    tok = _resolve_token()
    return {"Authorization": "Bearer " + tok} if tok else {}


async def handler(websocket):
    # ── handshake gate ─────────────────────────────────────────────
    origin = websocket.request.headers.get("Origin", "") if getattr(websocket, "request", None) else ""
    # The token rides as the WebSocket subprotocol. websockets 16.x strips
    # negotiated protocol headers from .request.headers during the handshake,
    # so read the NEGOTIATED protocol off the connection first and only fall
    # back to the raw header for servers that keep it.
    token = getattr(websocket, "subprotocol", None) or None
    if not token:
        try:
            token = websocket.request.headers.get("Sec-WebSocket-Protocol", "").split(",")[0].strip() or None
        except Exception:
            token = None
    expected = _resolve_token()
    if not expected:
        print("[BRIDGE] REJECTED: no auth token in environment or token file")
        await websocket.close(1008, "auth required")
        return
    if token != expected:
        print(f"[BRIDGE] REJECTED connection: bad/missing token (origin={origin!r})")
        await websocket.close(1008, "unauthorized")
        return
    if origin not in _ALLOWED_ORIGINS:
        print(f"[BRIDGE] REJECTED connection from origin: {origin!r}")
        await websocket.close(1008, "origin not allowed")
        return
    if len(JarvisBridge._all_clients) >= _MAX_CLIENTS:
        print("[BRIDGE] REJECTED: too many connections")
        await websocket.close(1013, "try again later")
        return

    bridge = JarvisBridge(f"http://{BRIDGE_HOST}:{BRIDGE_PORT}")
    await bridge.register(websocket)

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                await websocket.send(json.dumps({"type": "error", "payload": {"message": "binary frames not accepted"}}))
                continue
            if len(message) > _MAX_TEXT:
                await websocket.send(json.dumps({"type": "error", "payload": {"message": "message too large"}}))
                continue
            # Containment: one bad message/handler must not tear down the
            # connection — report the failure and keep serving the session.
            try:
                await bridge.handle_message(websocket, message)
            except websockets.exceptions.ConnectionClosed:
                raise
            except Exception as exc:  # noqa: BLE001 — funnel guard
                print(f"[BRIDGE] Handler error: {exc}")
                try:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "payload": {"message": f"Internal error: {exc}"},
                    }))
                except Exception:
                    pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        await bridge.unregister(websocket)


async def main(ws_host: str, ws_port: int, bridge_host: str, bridge_port: int):
    global BRIDGE_HOST, BRIDGE_PORT
    BRIDGE_HOST = bridge_host
    BRIDGE_PORT = bridge_port

    print("[BRIDGE] JARVIS Orbit WebSocket Bridge")
    print(f"[BRIDGE] WebSocket: ws://{ws_host}:{ws_port}")
    print(f"[BRIDGE] JARVIS Backend: http://{bridge_host}:{bridge_port}")
    print("[BRIDGE] Waiting for Electron browser to connect...")

    # Single process-wide status watchdog (NOT one per connection): polls the
    # kernel every _WATCHDOG_INTERVAL_S, pushes online/offline TRANSITIONS to
    # all clients. The renderer never polls at a fixed rate for kernel state
    # (spec rule: "Renderer does not poll JARVIS. Events only."). Skips the
    # probe entirely when no clients are connected.
    _watchdog = JarvisBridge(f"http://{BRIDGE_HOST}:{BRIDGE_PORT}")
    asyncio.ensure_future(_watchdog._status_watchdog())

    # The Electron WS client sends the auth token as its ONLY offered
    # subprotocol; the server must SELECT it in the response or the client
    # (correctly, per RFC 6455) fails the handshake with "Server sent no
    # subprotocol" and reconnect-loops forever (status flicker bug).
    _token = _resolve_token() or ""
    async with serve(handler, ws_host, ws_port, subprotocols=[_token] if _token else []):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS Orbit WebSocket Bridge")
    parser.add_argument("--host", default=WS_HOST, help="WebSocket bind host")
    parser.add_argument("--port", type=int, default=WS_PORT, help="WebSocket bind port")
    parser.add_argument("--bridge-host", default=BRIDGE_HOST, help="JARVIS bridge host")
    parser.add_argument("--bridge-port", type=int, default=BRIDGE_PORT, help="JARVIS bridge port")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.host, args.port, args.bridge_host, args.bridge_port))
    except KeyboardInterrupt:
        print("\n[BRIDGE] Shutting down")
    except Exception as exc:  # noqa: BLE001 — fail loudly, not silently
        print(f"[BRIDGE] Fatal error: {exc}")
        raise SystemExit(1)
