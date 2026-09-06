#!/usr/bin/env python3
"""JARVIS Orbit — WebSocket Bridge Server.

Connects the Electron browser to the JARVIS Python backend via WebSocket.
The browser sends chat messages and receives streaming responses, agent
events, and approval requests.

Usage:
    python orbit-browser/python/server.py
    python orbit-browser/python/server.py --port 8171
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

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
HOST = "127.0.0.1"
PORT = 8171


# ── JARVIS Bridge ──────────────────────────────────────────────────
class JarvisBridge:
    """WebSocket bridge between Electron and JARVIS backend."""

    def __init__(self):
        self.clients: set = set()
        self.session_id: str = f"orbit-{int(time.time())}"

    async def register(self, websocket):
        """Register a new client connection."""
        self.clients.add(websocket)
        print(f"[BRIDGE] Client connected ({len(self.clients)} total)")

        # Send initial status
        await websocket.send(json.dumps({
            "type": "status",
            "payload": {"ok": True, "kernel": "online", "session": self.session_id},
        }))

    async def unregister(self, websocket):
        """Unregister a client connection."""
        self.clients.discard(websocket)
        print(f"[BRIDGE] Client disconnected ({len(self.clients)} total)")

    async def handle_message(self, websocket, raw: str):
        """Handle incoming message from Electron."""
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
        elif msg_type == "status_request":
            await self.handle_status(websocket)
        elif msg_type == "agent_action":
            await self.handle_agent_action(websocket, payload)
        else:
            print(f"[BRIDGE] Unknown message type: {msg_type}")

    async def handle_chat(self, websocket, payload: dict):
        """Handle chat message from browser."""
        text = payload.get("text", "")
        session = payload.get("sessionId", self.session_id)

        print(f"[BRIDGE] Chat: {text[:50]}...")

        # Send thinking state
        await websocket.send(json.dumps({
            "type": "agent_event",
            "payload": {"state": "thinking"},
        }))

        # Simulate JARVIS response (replace with real agent call)
        await asyncio.sleep(0.5)

        # Send planning state
        await websocket.send(json.dumps({
            "type": "agent_event",
            "payload": {"state": "planning"},
        }))

        await asyncio.sleep(0.5)

        # Send running state
        await websocket.send(json.dumps({
            "type": "agent_event",
            "payload": {"state": "running"},
        }))

        # Generate response
        response = self.generate_response(text)

        # Send completion
        await websocket.send(json.dumps({
            "type": "chat_reply",
            "payload": {
                "kind": "done",
                "text": response,
                "session": session,
            },
        }))

        # Reset to idle
        await websocket.send(json.dumps({
            "type": "agent_event",
            "payload": {"state": "idle"},
        }))

    def generate_response(self, text: str) -> str:
        """Generate a JARVIS response. Replace with real agent integration."""
        # This is a placeholder — integrate with the actual JARVIS agent loop
        return (
            f"I received your message: \"{text}\"\n\n"
            "I'm JARVIS, your browser intelligence layer. "
            "I can help you research, summarize, remember, and act on web content.\n\n"
            "To enable full functionality, connect me to the JARVIS agent backend."
        )

    async def handle_status(self, websocket):
        """Handle status request."""
        await websocket.send(json.dumps({
            "type": "status",
            "payload": {
                "ok": True,
                "kernel": "online",
                "session": self.session_id,
                "version": "0.1.0",
            },
        }))

    async def handle_agent_action(self, websocket, payload: dict):
        """Handle agent action request."""
        action = payload.get("action", "")
        print(f"[BRIDGE] Agent action: {action}")

        # Request approval for high-risk actions
        if action in ("upload", "download", "execute", "navigate"):
            await websocket.send(json.dumps({
                "type": "approval_request",
                "payload": {
                    "title": f"JARVIS wants to {action}",
                    "description": f"This action requires your approval.",
                    "details": {
                        "Action": action,
                        "Target": payload.get("target", "unknown"),
                        "Risk": "HIGH" if action in ("execute", "upload") else "MEDIUM",
                    },
                },
            }))


# ── WebSocket Server ───────────────────────────────────────────────
async def handler(websocket):
    """Handle a WebSocket connection."""
    bridge = JarvisBridge()
    await bridge.register(websocket)

    try:
        async for message in websocket:
            await bridge.handle_message(websocket, message)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        await bridge.unregister(websocket)


async def main(host: str, port: int):
    """Start the WebSocket server."""
    print(f"[BRIDGE] Starting JARVIS WebSocket bridge on {host}:{port}")

    async with serve(handler, host, port):
        print(f"[BRIDGE] Server running on ws://{host}:{port}")
        print("[BRIDGE] Waiting for Electron browser to connect...")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS Orbit WebSocket Bridge")
    parser.add_argument("--host", default=HOST, help="Bind host")
    parser.add_argument("--port", type=int, default=PORT, help="Bind port")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.host, args.port))
    except KeyboardInterrupt:
        print("\n[BRIDGE] Shutting down")
