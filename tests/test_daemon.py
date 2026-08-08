"""Daemon reliability tests (Sprint 1 — Runtime Reliability).

These prove the P0 guarantees: the daemon survives client disconnects,
mid-run disconnects, churn, and bad auth, and the fast stdlib client streams
a run correctly end-to-end. Uses a stub kernel — no LLM, no real DBs.

All servers run in-process against temp registry/state dirs so the user's
real ``~/.jarvis`` is never touched.
"""

import asyncio
import json
import socket
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from daemon.fastclient import FastClient, FastError
from daemon.server import DaemonServer

ROOT = Path(__file__).resolve().parents[1]


# ── Stub kernel ────────────────────────────────────────────────────────────


class Permissions:
    mode = "agent"

    def set_mode(self, mode):
        self.mode = mode


class Observer:
    def __init__(self):
        self.on_event = lambda name, data: None


class Logger:
    def flush(self):
        pass


class Router:
    _last_provider = None
    _last_model = None

    def warm(self):
        pass

    @property
    def status(self):
        return {}


class Registry:
    def list(self):
        return []


class Mem:
    def get_stats(self):
        return {"decisions": 0, "knowledge": 0}


class Result:
    def __init__(self, marker="done", success=True):
        self.success = success
        self.trace_id = f"trace-{marker}"
        self.state = {}
        self.observation = {}

    def to_dict(self):
        return {
            "success": self.success,
            "trace_id": self.trace_id,
            "state": self.state,
            "observation": self.observation,
        }


class StubKernel:
    """Async kernel that emits observer events and returns a fixed result."""

    def __init__(self, events=10, delay=0.01, duration=0.0):
        self.permissions = Permissions()
        self.observer = Observer()
        self.logger = Logger()
        self.router = Router()
        self.registry = Registry()
        self.mem = Mem()
        self._last_goal = ""
        self._last_result = None
        self._events = events
        self._delay = delay
        self._duration = duration

    async def run(self, goal):
        start = time.monotonic()
        for i in range(self._events):
            self.observer.on_event("task.progress", {"i": i})
            if self._delay:
                await asyncio.sleep(self._delay)
        if self._duration:
            await asyncio.sleep(self._duration)
        elapsed = time.monotonic() - start
        return Result(marker=f"{goal}-{elapsed:.1f}s")


def _stub_factory(**kw):
    return StubKernel(**kw)


# ── helpers ────────────────────────────────────────────────────────────────


def _env(type_, payload=None, id_=""):
    return json.dumps({
        "version": 1, "id": id_, "type": type_,
        "timestamp": time.time(), "payload": payload or {},
    }) + "\n"


def _raw_connect(port, token, timeout=5.0):
    sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    sock.settimeout(timeout)
    sock.sendall(_env("auth", {"token": token}, "t").encode())
    resp = _readline_raw(sock)
    if resp.get("type") != "ok":
        sock.close()
        raise AssertionError(f"auth failed: {resp}")
    return sock


def _readline_raw(sock):
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise AssertionError("connection closed while reading frame")
        buf += chunk
    line, _, _ = buf.partition(b"\n")
    return json.loads(line.decode())


def _read_frames(sock, run_id):
    """Read frames until the ``stream.result`` for ``run_id`` arrives."""
    buf = b""
    frames = []
    while True:
        while b"\n" in buf:
            line, _, buf = buf.partition(b"\n")
            frame = json.loads(line.decode())
            frames.append(frame)
            if frame.get("type") == "stream.result" and frame.get("id") == run_id:
                return frames
        chunk = sock.recv(4096)
        if not chunk:
            raise AssertionError("connection closed before stream.result")
        buf += chunk


@pytest.fixture
def server(tmp_path):
    """A running daemon on its own event-loop thread (like the real process).

    Each server keeps one asyncio loop alive for the duration of the test, so
    sync clients can connect from the test thread exactly as the CLI does.
    Teardown sends a wire ``shutdown`` message and joins the thread.
    """
    servers = []

    def _make(events=10, delay=0.01, duration=0.0):
        srv = DaemonServer(
            kernel_factory=lambda **kw: StubKernel(events=events, delay=delay,
                                                   duration=duration),
            project_dir=str(ROOT),
            port=0,
            token="test-token",
            registry_dir=tmp_path / "daemons",
            state_dir=tmp_path / "state",
        )
        thread = threading.Thread(
            target=_serve, args=(srv,), name="test-daemon", daemon=True)
        thread.start()

        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            try:
                with _client(srv) as c:
                    c.connect(timeout=1.0)
                break
            except FastError:
                time.sleep(0.05)
        else:
            raise AssertionError("daemon did not become reachable")

        servers.append((srv, thread))
        return srv

    yield _make

    for srv, thread in servers:
        _send_shutdown(srv)
        thread.join(timeout=10.0)


def _serve(srv: DaemonServer) -> None:
    async def _main() -> None:
        await srv.start()
        await srv.serve()

    asyncio.run(_main())


def _send_shutdown(srv: DaemonServer) -> None:
    try:
        sock = socket.create_connection(("127.0.0.1", srv.port), timeout=2.0)
        sock.settimeout(2.0)
        sock.sendall(_env("auth", {"token": srv.token}, "sd").encode())
        _readline_raw(sock)
        sock.sendall(_env("shutdown", {}, "sd").encode())
        sock.close()
    except OSError:
        pass


def _client(srv) -> FastClient:
    return FastClient(host="127.0.0.1", port=srv.port, token=srv.token)


# ── Sprint 1 guarantees ────────────────────────────────────────────────────


def test_auth_rejects_bad_token(server):
    srv = server()
    sock = socket.create_connection(("127.0.0.1", srv.port), timeout=5.0)
    sock.settimeout(5.0)
    try:
        sock.sendall(_env("auth", {"token": "wrong"}, "x").encode())
        resp = _readline_raw(sock)
        assert resp["type"] == "error"
        assert "unauthorized" in resp["payload"]["message"]
    finally:
        sock.close()


def test_fastclient_round_trip(server):
    srv = server()
    with _client(srv) as c:
        c.connect()
        ping = c.ping()
        assert ping["project_id"] == srv.project_id
        status = c.status()
        assert status["tools"] == 0
        assert status["mode"] == "agent"


def test_fastclient_streams_many_events(server):
    """A burst of events in one TCP segment must not lose frames (regression
    for the old _readline that discarded surplus buffered lines)."""
    srv = server(events=1500, delay=0.0)
    with _client(srv) as c:
        c.connect()
        events = []
        result = c.run("burst", on_event=lambda name, data: events.append(name))
        assert result["success"] is True
        assert len(events) == 1500
        assert events[:3] == ["task.progress", "task.progress", "task.progress"]


def test_raw_stream_run(server):
    srv = server(events=3, delay=0.01)
    sock = _raw_connect(srv.port, srv.token)
    try:
        run_id = uuid.uuid4().hex
        sock.sendall(_env("run", {"goal": "stream"}, run_id).encode())
        frames = _read_frames(sock, run_id)
        events = [f for f in frames if f["type"] == "stream.event" and f["id"] == run_id]
        results = [f for f in frames if f["type"] == "stream.result"]
        assert len(events) == 3
        assert len(results) == 1
        assert results[0]["payload"]["result"]["success"] is True
    finally:
        sock.close()


def test_midrun_disconnect_survives(server):
    """Client vanishes mid-run: kernel finishes in the background, the daemon
    keeps serving, and a subsequent run still completes."""
    srv = server(events=5, delay=0.05, duration=1.5)
    sock = _raw_connect(srv.port, srv.token)
    sock.sendall(_env("run", {"goal": "long"}, "r1").encode())
    time.sleep(0.3)
    sock.close()

    with _client(srv) as c:
        c.connect()
        c.ping()

    time.sleep(2.0)
    with _client(srv) as c:
        c.connect()
        result = c.run("after", on_event=lambda *_: None)
        assert result["success"] is True
        assert "after" in result["trace_id"]


def test_disconnect_churn_keeps_daemon_alive(server):
    srv = server()
    for _ in range(100):
        with _client(srv) as c:
            c.connect()
            c.ping()
    with _client(srv) as c:
        c.connect()
        assert c.ping()["pid"] > 0


def test_shutdown_removes_entry(server, tmp_path):
    srv = server()
    entry_path = tmp_path / "daemons" / f"daemon-{srv.project_id}.json"
    assert entry_path.exists()
    _send_shutdown(srv)
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and entry_path.exists():
        time.sleep(0.05)
    assert not entry_path.exists()
    with pytest.raises(FastError):
        _client(srv).connect(timeout=1.0)
