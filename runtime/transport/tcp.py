"""TCP loopback transport for JARVIS daemon IPC.

Wraps asyncio stream pairs in the :class:`Transport` interface with NDJSON
framing (see ``runtime.transport.protocol``). Loopback TCP is sub-millisecond
per round trip on Windows and is asyncio-native, which keeps the kernel's
event loop free of thread bridges.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from runtime.transport.base import Transport
from runtime.transport.protocol import MAX_FRAME_SIZE, decode_line, encode_line

__all__ = ["TCPTransport", "open_connection", "start_server"]

logger = logging.getLogger("jarvis.transport.tcp")

Address = str | bytes | int
ServerHandler = Callable[[Transport], Awaitable[None]]


class TCPTransport(Transport):
    """NDJSON-framed duplex stream over an asyncio reader/writer pair."""

    def __init__(self, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer
        self._closed = False

    async def send(self, message: dict[str, Any]) -> None:
        if self._closed:
            raise ConnectionError("transport is closed")
        self._writer.write(encode_line(_envelope_from_dict(message)))
        await self._writer.drain()

    async def receive(self) -> dict[str, Any] | None:
        if self._closed:
            return None
        line = await self._reader.readline()
        if not line:
            await self.close()
            return None
        return _envelope_to_dict(decode_line(line))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._writer.close()
        # On Windows the Proactor loop can surface a pending read as
        # ConnectionResetError (WinError 64) from wait_closed() when the peer
        # disconnects mid-frame. A close must never raise: a client disconnect
        # is an ordinary event, not a daemon-fatal condition.
        try:
            await asyncio.wait_for(self._writer.wait_closed(), timeout=2.0)
        except Exception:
            pass

    @property
    def is_closing(self) -> bool:
        return self._closed or self._writer.is_closing()


def _envelope_from_dict(message: dict[str, Any]) -> Any:
    from runtime.transport.protocol import Envelope

    return Envelope(
        type=str(message.get("type", "")),
        id=str(message.get("id", "")),
        payload=dict(message.get("payload", {}) or {}),
        version=int(message.get("version", 1)),
        timestamp=float(message.get("timestamp", 0.0) or 0.0),
    )


def _envelope_to_dict(env) -> dict[str, Any]:
    return {
        "version": env.version,
        "id": env.id,
        "type": env.type,
        "timestamp": env.timestamp,
        "payload": env.payload,
    }


async def open_connection(host: str = "127.0.0.1", port: int = 0) -> TCPTransport:
    reader, writer = await asyncio.open_connection(host, port)
    return TCPTransport(reader, writer)


async def start_server(handler: ServerHandler, host: str = "127.0.0.1",
                       port: int = 0) -> asyncio.AbstractServer:
    """Start an asyncio server whose handler receives a ``TCPTransport``."""

    async def _on_client(reader: asyncio.StreamReader,
                         writer: asyncio.StreamWriter) -> None:
        transport = TCPTransport(reader, writer)
        try:
            await handler(transport)
        except asyncio.CancelledError:
            raise
        except BaseException:
            # An exception escaping here becomes "Unhandled exception in
            # client_connected_cb", which tears down the whole asyncio server
            # (and with it the daemon). Log it and drop just this connection.
            logger.exception("connection handler failed")
        finally:
            try:
                await transport.close()
            except BaseException:  # pragma: no cover - defensive
                pass

    return await asyncio.start_server(_on_client, host, port, limit=MAX_FRAME_SIZE)
