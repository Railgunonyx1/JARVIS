"""Async client for the JARVIS daemon.

Holds one persistent, authenticated connection to a :class:`DaemonServer`
and correlates responses to requests by envelope id. ``run`` streams task
observer events back through a callback, then returns the final result dict.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Callable, Dict, List, Optional

from daemon.state import PROTOCOL_VERSION
from runtime.transport.protocol import (
    MSG_AUTH,
    MSG_ERROR,
    MSG_EVENT,
    MSG_HISTORY,
    MSG_MEMORY_ADD,
    MSG_MEMORY_SEARCH,
    MSG_MODELS,
    MSG_OK,
    MSG_PING,
    MSG_PONG,
    MSG_RESULT,
    MSG_RUN,
    MSG_RUN_RESULT,
    MSG_SET_MODE,
    MSG_STATUS,
)
from runtime.transport.tcp import open_connection

__all__ = ["DaemonClient", "DaemonError", "DaemonDisconnected"]

EventCallback = Callable[[str, Dict], None]


class DaemonError(Exception):
    """The daemon replied with an error for a request."""


class DaemonDisconnected(Exception):
    """The daemon connection dropped or never authenticated."""


def _env(type_: str, payload: Optional[Dict] = None,
         id_: str = "") -> Dict:
    return {
        "version": PROTOCOL_VERSION,
        "id": id_,
        "type": type_,
        "timestamp": time.time(),
        "payload": payload or {},
    }


class DaemonClient:
    """Persistent connection to a single daemon."""

    #: Upper bound on a TCP connect + auth handshake.
    CONNECT_TIMEOUT = 5.0
    #: Max silence between frames while a request/run is in flight. Streams
    #: (run events) refresh far more often, so this only fires when the daemon
    #: is truly hung — turning a silent freeze into a visible error.
    IDLE_TIMEOUT = 120.0

    def __init__(self, host: str = "127.0.0.1", port: int = 0,
                 token: str = "", project_id: str = "") -> None:
        self.host = host
        self.port = port
        self.token = token
        self.project_id = project_id
        self._transport = None
        self._connected = False
        self.cached_status: Dict = {}
        self.last_connect_ms = 0.0
        self.last_request_ms = 0.0
        self.last_run_ms = 0.0

    @property
    def connected(self) -> bool:
        return self._connected

    # ── connection ───────────────────────────────────────────────────────

    async def connect(self) -> None:
        if self._connected:
            return
        t0 = time.perf_counter()
        transport = None
        try:
            transport = await asyncio.wait_for(
                open_connection(self.host, self.port), timeout=self.CONNECT_TIMEOUT)
            try:
                await transport.send(_env(MSG_AUTH, {"token": self.token}))
                response = await asyncio.wait_for(
                    transport.receive(), timeout=self.CONNECT_TIMEOUT)
            except asyncio.TimeoutError:
                raise DaemonDisconnected(
                    f"daemon {self.host}:{self.port} did not authenticate within "
                    f"{self.CONNECT_TIMEOUT:.0f}s") from None
            if response is None:
                raise DaemonDisconnected("daemon closed during auth handshake")
            if response.get("type") == MSG_ERROR:
                raise DaemonError(response.get("payload", {}).get("message", "auth failed"))
            if response.get("type") != MSG_OK:
                raise DaemonError(f"unexpected auth response: {response.get('type')}")
        except Exception:
            if transport is not None:
                await transport.close()
            raise
        self._transport = transport
        self._connected = True
        self.last_connect_ms = (time.perf_counter() - t0) * 1000.0

    async def close(self) -> None:
        if self._transport is not None:
            await self._transport.close()
        self._transport = None
        self._connected = False

    async def reconnect(self) -> None:
        await self.close()
        await self.connect()

    # ── low level ────────────────────────────────────────────────────────

    async def _send(self, type_: str, payload: Optional[Dict] = None,
                    id_: str = "") -> None:
        if self._transport is None:
            raise DaemonDisconnected("not connected")
        await self._transport.send(_env(type_, payload, id_))

    async def _recv(self) -> Dict:
        if self._transport is None:
            raise DaemonDisconnected("not connected")
        try:
            message = await asyncio.wait_for(
                self._transport.receive(), timeout=self.IDLE_TIMEOUT)
        except asyncio.TimeoutError:
            self._connected = False
            raise DaemonError(
                f"daemon unresponsive — no frame for {self.IDLE_TIMEOUT:.0f}s"
            ) from None
        if message is None:
            self._connected = False
            raise DaemonDisconnected("daemon connection lost")
        return message

    async def request(self, type_: str, payload: Optional[Dict] = None,
                      *, id_: str = "") -> Dict:
        """Send a request and await its terminal response payload."""
        t0 = time.perf_counter()
        try:
            rid = id_ or uuid.uuid4().hex
            await self._send(type_, payload, rid)
            while True:
                message = await self._recv()
                if message.get("id") != rid:
                    continue
                msg_type = message.get("type")
                if msg_type == MSG_ERROR:
                    raise DaemonError(message.get("payload", {}).get("message", "request failed"))
                if msg_type in (MSG_OK, MSG_RESULT, MSG_PONG):
                    return message.get("payload", {})
        finally:
            self.last_request_ms = (time.perf_counter() - t0) * 1000.0

    # ── convenience requests ─────────────────────────────────────────────

    async def ping(self) -> Dict:
        return await self.request(MSG_PING)

    async def status(self) -> Dict:
        payload = await self.request(MSG_STATUS)
        self.cached_status = payload
        return payload

    async def set_mode(self, mode: str) -> Dict:
        return await self.request(MSG_SET_MODE, {"mode": mode})

    async def memory_search(self, query: str, top_k: int = 5) -> List[Dict]:
        payload = await self.request(MSG_MEMORY_SEARCH, {"query": query, "top_k": top_k})
        return payload.get("hits", [])

    async def memory_add(self, key: str, value: str, category: str = "notes") -> str:
        payload = await self.request(
            MSG_MEMORY_ADD,
            {"key": key, "value": value, "category": category},
        )
        return payload.get("message", "")

    async def models(self) -> Dict:
        payload = await self.request(MSG_MODELS)
        return payload.get("data", {})

    async def history(self, task_id: str = "", limit: int = 10) -> Dict:
        payload = {"limit": limit}
        if task_id:
            payload["task_id"] = task_id
        return await self.request(MSG_HISTORY, payload)

    async def run(self, goal: str, mode: Optional[str] = None,
                  on_event: Optional[EventCallback] = None) -> Dict:
        """Run a goal; stream observer events via ``on_event``, return result dict."""
        t0 = time.perf_counter()
        try:
            rid = uuid.uuid4().hex
            payload: Dict = {"goal": goal}
            if mode:
                payload["mode"] = mode
            await self._send(MSG_RUN, payload, rid)
            while True:
                message = await self._recv()
                if message.get("id") != rid:
                    continue
                msg_type = message.get("type")
                if msg_type == MSG_EVENT:
                    if on_event is not None:
                        data = message.get("payload", {})
                        on_event(data.get("name", ""), data.get("payload", {}))
                elif msg_type == MSG_RUN_RESULT:
                    return message.get("payload", {}).get("result", {})
                elif msg_type == MSG_ERROR:
                    raise DaemonError(message.get("payload", {}).get("message", "run failed"))
        finally:
            self.last_run_ms = (time.perf_counter() - t0) * 1000.0
