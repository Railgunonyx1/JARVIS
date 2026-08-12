"""Synchronous, stdlib-only daemon client for the fast CLI path.

The full CLI imports typer+rich (~260ms) before it can even ask a question.
This module connects straight to a resident daemon with plain sockets so a
warm daemon turns ``jarvis "goal"`` into: interpreter start + one loopback
round trip. It mirrors the async :class:`daemon.client.DaemonClient` wire
format exactly (auth handshake, envelope framing, ``run`` event streaming).

Only the standard library is imported here so the fast path stays cheap.
"""

from __future__ import annotations

import json
import socket
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from daemon.project import project_id
from daemon.state import PROTOCOL_VERSION, load_entry

__all__ = ["FastClient", "FastError", "find_entry"]

EventCallback = Callable[[str, dict], None]


class FastError(Exception):
    """A daemon connection or protocol error on the fast path."""


def _env(type_: str, payload: dict | None = None, id_: str = "") -> dict:
    return {
        "version": PROTOCOL_VERSION,
        "id": id_,
        "type": type_,
        "timestamp": time.time(),
        "payload": payload or {},
    }


def _encode(msg: dict) -> bytes:
    return (json.dumps(msg) + "\n").encode("utf-8")


def find_entry(project_dir: str) -> dict | None:
    """Load the registry entry for a project, or None."""
    pid = project_id(Path(project_dir).resolve())
    entry = load_entry(pid)
    if entry is None:
        return None
    return entry


class FastClient:
    """One authenticated socket session to a daemon (stdlib only)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0,
                 token: str = "") -> None:
        self.host = host
        self.port = port
        self.token = token
        self._sock: socket.socket | None = None
        self._buffer = b""

    # ── connection ────────────────────────────────────────────────────────

    def connect(self, timeout: float = 5.0) -> None:
        try:
            sock = socket.create_connection((self.host, self.port), timeout=timeout)
        except OSError as exc:
            raise FastError(f"cannot connect to daemon: {exc}") from exc
        sock.settimeout(timeout)
        self._sock = sock
        self._buffer = b""
        try:
            sock.sendall(_encode(_env("auth", {"token": self.token})))
            response = self._recv_line()
            if response.get("type") != "ok":
                raise FastError(
                    response.get("payload", {}).get("message", "auth failed"))
        except Exception:
            try:
                sock.close()
            except OSError:
                pass
            self._sock = None
            raise

    def _recv_line(self) -> dict:
        """Read exactly one NDJSON envelope, keeping any surplus buffered.

        The server can coalesce several frames into one TCP segment (events +
        result during a run); discarding the surplus would deadlock the client.
        """
        sock = self._sock
        assert sock is not None
        while b"\n" not in self._buffer:
            try:
                chunk = sock.recv(4096)
            except OSError as exc:
                raise FastError(f"connection lost: {exc}") from exc
            if not chunk:
                raise FastError("daemon closed the connection")
            self._buffer += chunk
            if len(self._buffer) > (1 << 20):
                break
        line, _, self._buffer = self._buffer.partition(b"\n")
        try:
            return json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise FastError(f"malformed envelope: {exc}") from exc

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._buffer = b""

    def __enter__(self) -> FastClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ── requests ──────────────────────────────────────────────────────────

    def request(self, type_: str, payload: dict | None = None,
                timeout: float = 5.0) -> dict:
        rid = uuid.uuid4().hex
        assert self._sock is not None
        self._sock.settimeout(timeout)
        self._sock.sendall(_encode(_env(type_, payload, rid)))
        while True:
            response = self._recv_line()
            if response.get("id") != rid:
                continue
            if response.get("type") == "error":
                raise FastError(
                    response.get("payload", {}).get("message", "request failed"))
            return response.get("payload", {})

    def ping(self) -> dict:
        return self.request("ping", timeout=2.0)

    def status(self) -> dict:
        return self.request("status")

    def skills(self, query: str = "", mode: str | None = None,
               max_risk: str | None = None) -> dict:
        """Query the skill registry; returns ``{total, catalog, skills, ...}``."""
        payload: dict = {}
        if query:
            payload["query"] = query
        if mode:
            payload["mode"] = mode
        if max_risk:
            payload["max_risk"] = max_risk
        return self.request("skills", payload)

    def run(self, goal: str, mode: str | None = None,
            on_event: EventCallback | None = None) -> dict:
        """Run a goal; stream observer events via ``on_event``; return result dict."""
        rid = uuid.uuid4().hex
        payload: dict = {"goal": goal}
        if mode:
            payload["mode"] = mode
        assert self._sock is not None
        self._sock.settimeout(None)
        self._sock.sendall(_encode(_env("run", payload, rid)))
        while True:
            response = self._recv_line()
            if response.get("id") != rid:
                continue
            msg_type = response.get("type")
            if msg_type == "stream.event":
                data = response.get("payload", {})
                if on_event is not None:
                    on_event(data.get("name", ""), data.get("payload", {}))
            elif msg_type == "stream.result":
                return response.get("payload", {}).get("result", {})
            elif msg_type == "error":
                raise FastError(
                    response.get("payload", {}).get("message", "run failed"))
