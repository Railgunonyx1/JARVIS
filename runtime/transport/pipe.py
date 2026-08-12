from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from runtime.transport.base import Transport
from runtime.transport.protocol import MAX_FRAME_SIZE, decode_line, encode_line

logger = logging.getLogger("jarvis.transport.pipe")

class PipeProtocol(asyncio.Protocol):
    def __init__(self, on_connect: asyncio.Future[PipeProtocol]) -> None:
        self.transport: asyncio.WriteTransport | None = None
        self.queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.buffer = b""
        self._on_connect = on_connect

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport # type: ignore
        self._on_connect.set_result(self)

    def data_received(self, data: bytes) -> None:
        if len(self.buffer) + len(data) > MAX_FRAME_SIZE:
            logger.error(
                "Pipe frame exceeds MAX_FRAME_SIZE (%s bytes); closing connection",
                MAX_FRAME_SIZE,
            )
            self.buffer = b""
            if self.transport is not None:
                self.transport.close()
            self.queue.put_nowait(None)
            return
        self.buffer += data
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            if not line:
                continue
            try:
                decoded = decode_line(line + b"\n")
                env_dict = {
                    "version": decoded.version,
                    "id": decoded.id,
                    "type": decoded.type,
                    "timestamp": decoded.timestamp,
                    "payload": decoded.payload,
                }
                self.queue.put_nowait(env_dict)
            except Exception as e:
                logger.error("Failed to decode pipe frame: %s", e)

    def connection_lost(self, exc: Exception | None) -> None:
        self.queue.put_nowait(None)


class NamedPipeTransport(Transport):
    def __init__(self, protocol: PipeProtocol) -> None:
        self._protocol = protocol
        self._closed = False

    async def send(self, message: dict[str, Any]) -> None:
        if self._closed or not self._protocol.transport:
            raise ConnectionError("transport is closed")

        from runtime.transport.protocol import Envelope
        env = Envelope(
            type=str(message.get("type", "")),
            id=str(message.get("id", "")),
            payload=dict(message.get("payload", {}) or {}),
            version=int(message.get("version", 1)),
            timestamp=float(message.get("timestamp", 0.0) or 0.0),
        )
        data = encode_line(env)
        self._protocol.transport.write(data)

    async def receive(self) -> dict[str, Any] | None:
        if self._closed:
            return None
        return await self._protocol.queue.get()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._protocol.transport:
            self._protocol.transport.close()

    @property
    def is_closing(self) -> bool:
        return self._closed or (self._protocol.transport is None)


class PipeServer:
    def __init__(self, servers: list[Any]) -> None:
        self._servers = servers

    def close(self) -> None:
        for s in self._servers:
            try:
                s.close()
            except Exception:
                pass

    async def wait_closed(self) -> None:
        for s in self._servers:
            try:
                await s.wait_closed()
            except Exception:
                pass


async def start_pipe_server(
    handler: Callable[[Transport], Any],
    pipe_name: str
) -> PipeServer:
    """Start serving a Windows Named Pipe. Handler receives NamedPipeTransport."""
    loop = asyncio.get_running_loop()

    def protocol_factory():
        future = loop.create_future()

        async def run_handler(f):
            try:
                protocol = await f
                transport = NamedPipeTransport(protocol)
                await handler(transport)
            except Exception:
                logger.exception("Error in pipe server handler")

        asyncio.create_task(run_handler(future))
        return PipeProtocol(future)

    server = await loop.start_serving_pipe(protocol_factory, pipe_name)
    servers = server if isinstance(server, (list, tuple)) else [server]
    return PipeServer(servers)
