"""WebSocket server — streams telemetry, voice, LLM events to frontend.

Runs alongside JARVIS kernel, broadcasting system status and events
to connected HUD clients (React/Tauri).

Hardened: ping/pong keepalive, per-client send isolation (a slow client
cannot block the broadcast), send timeouts, max payload size, automatic
cleanup of dead connections, and a shutdown path.
"""

import asyncio
import json
import logging
import time

import psutil

try:
    import websockets
    from websockets.server import serve
except ImportError:
    websockets = None

from core.json_fast import dumps as fast_dumps

logger = logging.getLogger("jarvis.api.ws_server")

WS_PORT = 8766  # must not collide with Flask (JARVIS_PORT=8765)
_HEARTBEAT_INTERVAL = 2.0
_PING_INTERVAL = 10.0
_SEND_TIMEOUT = 3.0
_MAX_CLIENTS = 64
_MAX_MSG_SIZE = 2 ** 20  # 1 MiB
_AUTH_TIMEOUT = 5.0


class WSServer:
    """Broadcasts JARVIS events to connected frontend clients."""

    def __init__(self, host: str = "0.0.0.0", port: int = WS_PORT, auth_token: str = None):
        self.host = host
        self.port = port
        self._auth_token = auth_token
        self._clients: set = set()
        self._client_tasks: dict = {}
        self._start_time = time.time()
        self._process = psutil.Process()
        self._running = False
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._loop = None

    # ── Per-client handling ────────────────────────────────

    async def _send(self, websocket, msg: str) -> bool:
        """Send with timeout; returns False if the client is gone/stuck."""
        try:
            await asyncio.wait_for(websocket.send(msg), timeout=_SEND_TIMEOUT)
            return True
        except (TimeoutError, websockets.exceptions.ConnectionClosed, OSError):
            return False

    async def _handler(self, websocket):
        """Register client, process inbound messages, and keepalive via ping/pong."""
        if len(self._clients) >= _MAX_CLIENTS:
            await self._send(websocket, json.dumps({"type": "error", "error": "too many clients"}))
            await websocket.close(code=1013)
            return
        if self._auth_token and not await self._authenticate(websocket):
            await self._send(websocket, json.dumps({"type": "error", "error": "unauthorized"}))
            await websocket.close(code=1008)
            return
        self._clients.add(websocket)
        try:
            # Consume inbound messages (subscribe commands, heartbeats) concurrently
            # with a ping loop that prunes dead sockets.
            inbound = asyncio.create_task(self._read_loop(websocket))
            keepalive = asyncio.create_task(self._ping_loop(websocket))
            done, pending = await asyncio.wait(
                {inbound, keepalive},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        finally:
            self._clients.discard(websocket)
            self._client_tasks.pop(websocket, None)

    async def _read_loop(self, websocket):
        """Read inbound messages; register subscriptions, handle pings."""
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("type") == "subscribe":
                    channels = data.get("channels", [])
                    logger.info("Client subscribed: %s", channels)
                elif data.get("type") == "ping":
                    await self._send(websocket, json.dumps({"type": "pong", "ts": time.time()}))
            except json.JSONDecodeError:
                pass

    async def _authenticate(self, websocket) -> bool:
        """Require the first message to be an auth token (when configured)."""
        if not self._auth_token:
            return True
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout=_AUTH_TIMEOUT)
            data = json.loads(message)
            if data.get("type") == "auth" and data.get("token") == self._auth_token:
                return True
        except (TimeoutError, websockets.exceptions.ConnectionClosed, json.JSONDecodeError, KeyError, ValueError):
            pass
        except Exception:
            pass
        return False

    async def _ping_loop(self, websocket):
        """Send application-level pings and rely on the protocol keepalive."""
        try:
            while True:
                await asyncio.sleep(_PING_INTERVAL)
                if not await self._send(websocket, json.dumps({"type": "ping", "ts": time.time()})):
                    logger.info("Client not responding, dropping connection")
                    return
        except (asyncio.CancelledError, websockets.exceptions.ConnectionClosed):
            return

    # ── Broadcast ─────────────────────────────────────────

    async def _broadcast(self, data: dict):
        msg = fast_dumps(data, default=str)
        dead = set()
        sends = []
        for ws in list(self._clients):
            sends.append(asyncio.ensure_future(self._send(ws, msg)))
        if not sends:
            return
        results = await asyncio.gather(*sends, return_exceptions=True)
        for ws, ok in zip(list(self._clients), results):
            if ok is not True:
                dead.add(ws)
        self._clients -= dead

    # ── Background loops ──────────────────────────────────

    async def _heartbeat(self):
        while self._running:
            mem = self._process.memory_info()
            status_data = {
                "type": "status",
                "timestamp": time.time(),
                "payload": {
                    "status": "running",
                    "uptime": time.time() - self._start_time,
                    "memory": {
                        "rss_mb": mem.rss,
                        "vms_mb": mem.vms,
                        "percent": psutil.virtual_memory().percent,
                    },
                    "cpu_percent": psutil.cpu_percent(interval=None),
                },
            }
            await self._broadcast(status_data)
            await asyncio.sleep(_HEARTBEAT_INTERVAL)

    async def _drain_queue(self):
        while self._running:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                await self._broadcast(event)
            except TimeoutError:
                pass

    def publish(self, event_type: str, message: str = "", payload: dict = None):
        """Thread-safe publish (called from any thread)."""
        coro = self._event_queue.put({
            "type": event_type,
            "message": message,
            "payload": payload or {},
            "timestamp": time.time(),
        })
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except (RuntimeError, Exception):
            pass

    # ── Lifecycle ─────────────────────────────────────────

    async def start(self):
        if websockets is None:
            logger.error("websockets not installed. Run: pip install websockets")
            return
        self._running = True
        self._loop = asyncio.get_running_loop()
        async with serve(self._handler, self.host, self.port, max_size=_MAX_MSG_SIZE):
            logger.info("WS server on ws://%s:%s (max clients=%d)", self.host, self.port, _MAX_CLIENTS)
            try:
                await asyncio.gather(
                    self._heartbeat(),
                    self._drain_queue(),
                )
            finally:
                self._running = False

    def stop(self):
        self._running = False
        loop = self._loop
        if loop is not None and not loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(self._shutdown(), loop)
            except (RuntimeError, Exception):
                pass

    async def _shutdown(self):
        """Close all client sockets and stop background loops."""
        self._running = False
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._clients.clear()


# ── Standalone entry ──

async def main():
    logging.basicConfig(level=logging.INFO)
    server = WSServer()
    await server.start()


def start_ws_server(host: str = "0.0.0.0", port: int = WS_PORT, auth_token: str = None):
    """Start the WS server in a background thread (non-blocking).

    Safe to call from Flask's run_server(). Returns the WSServer instance.
    """
    import threading

    server = WSServer(host=host, port=port, auth_token=auth_token)

    def _run():
        try:
            asyncio.run(server.start())
        except Exception as exc:
            logger.error("WS server thread exited: %s", exc)

    t = threading.Thread(target=_run, daemon=True, name="jarvis-ws-server")
    t.start()
    return server


if __name__ == "__main__":
    asyncio.run(main())
