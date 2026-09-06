#!/usr/bin/env python3
"""JARVIS Orbit — WebSocket Bridge Server.

Bridges the Electron browser to the JARVIS backend via WebSocket.
This server:
1. Starts the real JARVIS bridge (HTTP/SSE on port 8170)
2. Runs a WebSocket server (port 8171) for the Electron browser
3. Translates between WebSocket ↔ HTTP/SSE

Usage:
    python orbit-browser/python/server.py
    python orbit-browser/python/server.py --port 8171 --bridge-port 8170
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import threading
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

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


class JarvisBridge:
    """WebSocket bridge between Electron and JARVIS backend."""

    def __init__(self, bridge_url: str):
        self.bridge_url = bridge_url
        self.clients: set = set()
        self.session_id: str = f"orbit-{int(time.time())}"
        self._bridge_ok = False

    def _check_bridge(self) -> bool:
        """Check if the JARVIS bridge is running."""
        try:
            req = urlopen(f"{self.bridge_url}/status", timeout=2)
            data = json.loads(req.read())
            self._bridge_ok = data.get("ok", False)
            return self._bridge_ok
        except Exception:
            self._bridge_ok = False
            return False

    async def register(self, websocket):
        self.clients.add(websocket)
        print(f"[BRIDGE] Client connected ({len(self.clients)} total)")

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
        self.clients.discard(websocket)
        print(f"[BRIDGE] Client disconnected ({len(self.clients)} total)")

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
        """Forward chat to the real JARVIS bridge via HTTP/SSE."""
        text = payload.get("text", "")
        session = payload.get("sessionId", self.session_id)

        print(f"[BRIDGE] Chat: {text[:50]}...")

        # Send thinking state
        await websocket.send(json.dumps({
            "type": "agent_event",
            "payload": {"state": "thinking"},
        }))

        if not self._bridge_ok:
            # Bridge not available — generate offline response
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

        # Forward to real bridge via HTTP
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._forward_chat, text, session
            )

            if result:
                await websocket.send(json.dumps({
                    "type": "agent_event",
                    "payload": {"state": "running"},
                }))
                await asyncio.sleep(0.3)

                await websocket.send(json.dumps({
                    "type": "chat_reply",
                    "payload": {
                        "kind": "done",
                        "text": result,
                        "session": session,
                    },
                }))
            else:
                await websocket.send(json.dumps({
                    "type": "chat_reply",
                    "payload": {
                        "kind": "error",
                        "error": {"message": "No response from JARVIS backend"},
                        "session": session,
                    },
                }))
        except Exception as e:
            print(f"[BRIDGE] Chat error: {e}")
            await websocket.send(json.dumps({
                "type": "chat_reply",
                "payload": {
                    "kind": "error",
                    "error": {"message": str(e)},
                    "session": session,
                },
            }))

        await websocket.send(json.dumps({
            "type": "agent_event",
            "payload": {"state": "idle"},
        }))

    def _forward_chat(self, text: str, session: str) -> str | None:
        """Forward chat to the real JARVIS bridge via HTTP POST."""
        try:
            data = json.dumps({
                "text": text,
                "session": session,
            }).encode()

            req = Request(
                f"{self.bridge_url}/v1/chat",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urlopen(req, timeout=30) as resp:
                # Parse SSE response
                full_response = ""
                for line in resp.read().decode().split("\n"):
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            if chunk.get("kind") == "delta":
                                full_response += chunk.get("text", "")
                            elif chunk.get("kind") == "done":
                                return full_response or chunk.get("text", "")
                        except json.JSONDecodeError:
                            continue
                return full_response or None
        except Exception as e:
            print(f"[BRIDGE] HTTP error: {e}")
            return None

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

        # Forward to real bridge
        try:
            data = json.dumps({
                "goal": goal,
                "session": session,
            }).encode()

            req = Request(
                f"{self.bridge_url}/v1/agent",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urlopen(req, timeout=120) as resp:
                for line in resp.read().decode().split("\n"):
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            await websocket.send(json.dumps({
                                "type": "agent_event",
                                "payload": chunk,
                            }))
                        except json.JSONDecodeError:
                            continue
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


async def handler(websocket):
    bridge = JarvisBridge(f"http://{BRIDGE_HOST}:{BRIDGE_PORT}")
    await bridge.register(websocket)

    try:
        async for message in websocket:
            await bridge.handle_message(websocket, message)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        await bridge.unregister(websocket)


async def main(ws_host: str, ws_port: int, bridge_host: str, bridge_port: int):
    global BRIDGE_HOST, BRIDGE_PORT
    BRIDGE_HOST = bridge_host
    BRIDGE_PORT = bridge_port

    print(f"[BRIDGE] JARVIS Orbit WebSocket Bridge")
    print(f"[BRIDGE] WebSocket: ws://{ws_host}:{ws_port}")
    print(f"[BRIDGE] JARVIS Backend: http://{bridge_host}:{bridge_port}")
    print(f"[BRIDGE] Waiting for Electron browser to connect...")

    async with serve(handler, ws_host, ws_port):
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
