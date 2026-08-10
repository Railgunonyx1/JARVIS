"""WebSocket transport for JARVIS daemon IPC.

Implements the same :class:`Transport` interface as the TCP and named-pipe
transports (see ``runtime.transport.base``) on top of the ``websockets``
library, so browser and terminal clients can drive the daemon over ``ws://``.

Each protocol envelope is one JSON text frame. Connection hygiene matches the
TCP transport: a closed or reset peer surfaces as ``None`` from ``receive()``,
and a dead client must never raise into the daemon's dispatch loop — so any
transport-level failure is translated to :class:`ConnectionError`, which
``daemon.server._safe_send`` already swallows.

Only the server side is started by the daemon. The asyncio client keeps using
``runtime.transport.tcp``; the browser client uses the platform WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from runtime.transport.base import Transport
from runtime.transport.protocol import MAX_FRAME_SIZE

try:  # pragma: no cover - guarded import
    from websockets.protocol import State

    _HAS_WEBSOCKETS = True
except Exception:  # pragma: no cover - websockets missing
    _HAS_WEBSOCKETS = False
    State = None

__all__ = ["WebSocketTransport", "start_ws_server"]

logger = logging.getLogger("jarvis.transport.ws")

ServerHandler = Callable[[Transport], Awaitable[None]]


class WebSocketTransport(Transport):
    """One envelope-framed JSON WebSocket connection."""

    #: The daemon broadcasts peer connection-state frames only to transports
    #: that can tolerate unsolicited frames (browsers). TCP/pipe clients match
    #: every frame to a request id and would misread a broadcast.
    kind = "ws"

    def __init__(self, ws) -> None:
        self._ws = ws
        self._closed = False

    async def send(self, message: dict[str, Any]) -> None:
        if self._closed:
            raise ConnectionError("transport is closed")
        try:
            await self._ws.send(json.dumps(message, default=str))
        except Exception as exc:
            # ConnectionClosed, OSError, or any websockets-level failure mean
            # the peer is gone; translate to ConnectionError so the daemon's
            # _safe_send treats it as an ordinary disconnect.
            self._closed = True
            raise ConnectionError(str(exc)) from exc

    async def receive(self) -> dict[str, Any] | None:
        if self._closed:
            return None
        try:
            frame = await self._ws.recv()
        except Exception:
            # ConnectionClosed (OK or error), reset, oversized frame — all are
            # ordinary disconnects, never daemon-fatal.
            await self.close()
            return None
        if frame is None:
            await self.close()
            return None
        try:
            if isinstance(frame, (bytes, bytearray)):
                data = json.loads(frame.decode("utf-8"))
            else:
                data = json.loads(frame)
        except (ValueError, UnicodeDecodeError):
            # Malformed frame: drop the connection (matches TCP's behaviour
            # where a bad NDJSON line kills the client connection).
            await self.close()
            return None
        return data if isinstance(data, dict) else None

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._ws.close()
        except Exception:
            pass

    @property
    def is_closing(self) -> bool:
        if self._closed:
            return True
        if _HAS_WEBSOCKETS and State is not None:
            try:
                return self._ws.state in (State.CLOSING, State.CLOSED)
            except Exception:
                return True
        return False


async def start_ws_server(handler: ServerHandler, host: str = "127.0.0.1",
                          port: int = 0):
    """Start a WebSocket server whose handler receives a ``WebSocketTransport``.

    Returns the ``websockets`` ``Server`` object (``close()`` /
    ``wait_closed()`` / ``sockets``), mirroring ``runtime.transport.tcp``.
    """
    from websockets.asyncio.server import serve

    async def _on_connection(connection) -> None:
        transport = WebSocketTransport(connection)
        try:
            await handler(transport)
        except asyncio.CancelledError:
            raise
        except BaseException:
            # An exception escaping the handler must never take the server
            # down — log it and drop just this connection (mirrors tcp.py).
            logger.exception("websocket handler failed")
        finally:
            try:
                await transport.close()
            except BaseException:  # pragma: no cover - defensive
                pass

    return await serve(
        _on_connection,
        host,
        port,
        max_size=MAX_FRAME_SIZE,
        ping_interval=20.0,
        ping_timeout=20.0,
    )
