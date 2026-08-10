"""WebSocket transport tests (Phase 1 — daemon WS gateway).

The daemon binds a WebSocket listener on a second port reusing the exact same
envelope protocol, auth handshake, dispatcher, and observer streaming as the
TCP transport — no duplicated business logic. These tests drive a raw
``websockets`` client against a stub-kernel daemon and prove the P0 gateway
guarantees: auth, ping, run streaming, request cancellation, malformed-frame
handling, and registry/status exposure of the WS port.

Servers run in-process against temp registry/state dirs; the user's real
``~/.jarvis`` is never touched.
"""

import asyncio
import json
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

pytest.importorskip("websockets")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from daemon.client import DaemonClient  # noqa: E402
from daemon.server import DaemonServer  # noqa: E402
from websockets.asyncio.client import connect  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


# ── stub kernel (mirrors tests/test_daemon.py) ─────────────────────────────


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
        self.run_count = 0

    async def run(self, goal):
        self.run_count += 1
        for i in range(self._events):
            self.observer.on_event("task.progress", {"i": i})
            if self._delay:
                await asyncio.sleep(self._delay)
        if self._duration:
            await asyncio.sleep(self._duration)
        return Result(marker=goal)


# ── fixture ────────────────────────────────────────────────────────────────


def _serve(srv: DaemonServer) -> None:
    async def _main() -> None:
        await srv.start()
        await srv.serve()

    asyncio.run(_main())


def _env(type_, payload=None, id_=""):
    return {
        "version": 1,
        "id": id_,
        "type": type_,
        "timestamp": time.time(),
        "payload": payload or {},
    }


@pytest.fixture
def server(tmp_path):
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
            target=_serve, args=(srv,), name="test-daemon-ws", daemon=True)
        thread.start()

        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            try:
                asyncio.run(_probe_ws(srv))
                break
            except Exception:
                time.sleep(0.05)
        else:
            raise AssertionError("daemon did not become reachable over WS")

        servers.append((srv, thread))
        return srv

    yield _make

    for srv, thread in servers:
        _send_shutdown(srv)
        thread.join(timeout=10.0)


async def _probe_ws(srv) -> None:
    async with connect(f"ws://127.0.0.1:{srv.ws_port}", max_size=4 * 1024 * 1024) as ws:
        await ws.send(json.dumps(_env("auth", {"token": srv.token}, "p")))
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=1.0))
        assert resp["type"] == "ok"


def _send_shutdown(srv: DaemonServer) -> None:
    try:
        import socket

        sock = socket.create_connection(("127.0.0.1", srv.port), timeout=2.0)
        sock.settimeout(2.0)
        sock.sendall((json.dumps(_env("auth", {"token": srv.token}, "sd")) + "\n").encode())
        sock.recv(4096)
        sock.sendall((json.dumps(_env("shutdown", {}, "sd")) + "\n").encode())
        sock.close()
    except OSError:
        pass


# ── WS helpers ─────────────────────────────────────────────────────────────


async def _recv_frame(ws, timeout=8.0):
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))


async def _recv_until(ws, rid, types, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        frame = await _recv_frame(ws, timeout=deadline - time.monotonic())
        if frame.get("id") == rid and frame.get("type") in types:
            return frame
    raise AssertionError(f"timed out waiting for id={rid!r} types={types!r}")


async def _connect_auth(srv):
    ws = await connect(f"ws://127.0.0.1:{srv.ws_port}", max_size=4 * 1024 * 1024)
    await ws.send(json.dumps(_env("auth", {"token": srv.token}, "a")))
    resp = await _recv_frame(ws)
    assert resp["type"] == "ok"
    return ws


# ── tests ──────────────────────────────────────────────────────────────────


def test_ws_rejects_bad_token(server):
    srv = server()

    async def scenario():
        async with connect(f"ws://127.0.0.1:{srv.ws_port}") as ws:
            await ws.send(json.dumps(_env("auth", {"token": "wrong"}, "x")))
            resp = await _recv_frame(ws)
            assert resp["type"] == "error"
            assert "unauthorized" in resp["payload"]["message"]

    asyncio.run(scenario())


def test_ws_ping_round_trip(server):
    srv = server()

    async def scenario():
        ws = await _connect_auth(srv)
        try:
            await ws.send(json.dumps(_env("ping", {}, "p1")))
            pong = await _recv_until(ws, "p1", {"pong"})
            assert pong["payload"]["project_id"] == srv.project_id
            assert pong["payload"]["ws_port"] == srv.ws_port
            assert pong["payload"]["port"] == srv.port
        finally:
            await ws.close()

    asyncio.run(scenario())


def test_ws_streams_run_events(server):
    """A run over WS emits the same observer events + terminal result as TCP."""
    srv = server(events=4, delay=0.01)

    async def scenario():
        ws = await _connect_auth(srv)
        try:
            run_id = uuid.uuid4().hex
            await ws.send(json.dumps(_env("run", {"goal": "ws-stream"}, run_id)))
            result = await _recv_until(ws, run_id, {"stream.result"})
            assert result["payload"]["result"]["success"] is True
            assert "ws-stream" in result["payload"]["result"]["trace_id"]
        finally:
            await ws.close()

    asyncio.run(scenario())


def test_ws_cancel_running_run(server):
    """MSG_CANCEL stops the in-flight kernel run; the run's connection receives
    a terminal stream.result with cancelled=True so run() returns cleanly."""
    srv = server(events=10, delay=0.02, duration=2.0)

    async def scenario():
        ws = await _connect_auth(srv)
        try:
            run_id = uuid.uuid4().hex
            await ws.send(json.dumps(_env("run", {"goal": "long"}, run_id)))
            await _recv_until(ws, run_id, {"stream.event"})
            await ws.send(json.dumps(_env("cancel", {"task_id": run_id}, "c1")))
            ok = await _recv_until(ws, "c1", {"ok", "error"})
            assert ok["type"] == "ok", ok
            result = await _recv_until(ws, run_id, {"stream.result"})
            payload = result["payload"]["result"]
            assert payload["cancelled"] is True
            assert payload["success"] is False
        finally:
            await ws.close()

    asyncio.run(scenario())


def test_ws_malformed_frame_closes_connection(server):
    """A non-JSON frame must be rejected without taking the daemon down."""
    srv = server()

    async def scenario():
        ws = await _connect_auth(srv)
        await ws.send("this is not json {{")
        with pytest.raises(Exception):
            await _recv_frame(ws, timeout=3.0)
        await ws.close()

    asyncio.run(scenario())


# ── Block 2: connection state, run-id idempotency, bootstrap ────────────────


def test_ws_broadcasts_connection_state(server):
    """WS peers see stream.conn frames when another peer opens/closes."""
    srv = server()

    async def scenario():
        a = await _connect_auth(srv)
        try:
            b = await _connect_auth(srv)
            try:
                opened = await _recv_until(a, "__broadcast__", {"stream.conn"}, timeout=3.0)
                assert opened["payload"]["event"] == "opened"
                assert opened["payload"]["clients"] == 2
            finally:
                await b.close()
            closed = await _recv_until(a, "__broadcast__", {"stream.conn"}, timeout=3.0)
            assert closed["payload"]["event"] == "closed"
            assert closed["payload"]["clients"] == 1
        finally:
            await a.close()

    asyncio.run(scenario())


def test_ws_run_id_dedupe_no_double_execution(server):
    """Two run requests with the same id execute the kernel exactly once."""
    srv = server(events=3, delay=0.05, duration=0.2)

    async def scenario():
        ws = await _connect_auth(srv)
        try:
            rid = uuid.uuid4().hex
            await ws.send(json.dumps(_env("run", {"goal": "dup"}, rid)))
            await asyncio.sleep(0.1)
            await ws.send(json.dumps(_env("run", {"goal": "dup"}, rid)))
            r1 = await _recv_until(ws, rid, {"stream.result"}, timeout=8.0)
            r2 = await _recv_until(ws, rid, {"stream.result"}, timeout=8.0)
            assert r1["payload"]["result"]["success"] is True
            assert r2["payload"]["result"]["success"] is True
            assert srv.kernel.run_count == 1
        finally:
            await ws.close()

    asyncio.run(scenario())


def test_ws_bootstrap_auth_is_single_use(server):
    """A bootstrap credential authenticates once, then is rejected."""
    srv = server()

    async def scenario():
        client = DaemonClient("127.0.0.1", srv.port, token=srv.token)
        await client.connect()
        try:
            cred = await client.issue_bootstrap()
        finally:
            await client.close()
        assert cred.get("bootstrap")
        assert cred.get("ws_port") == srv.ws_port

        async def try_auth(payload):
            ws = await connect(f"ws://127.0.0.1:{srv.ws_port}",
                               max_size=4 * 1024 * 1024)
            await ws.send(json.dumps(_env("auth", payload, "b")))
            resp = await _recv_frame(ws, timeout=3.0)
            await ws.close()
            return resp

        first = await try_auth({"bootstrap": cred["bootstrap"]})
        assert first["type"] == "ok"
        second = await try_auth({"bootstrap": cred["bootstrap"]})
        assert second["type"] == "error"
        assert "unauthorized" in second["payload"]["message"]

    asyncio.run(scenario())


def test_ws_bootstrap_rejects_expired_and_bad_token(server):
    srv = server()
    srv._bootstrap_tokens["stale-cred"] = time.time() - 10.0

    async def scenario():
        async def try_auth(payload):
            ws = await connect(f"ws://127.0.0.1:{srv.ws_port}",
                               max_size=4 * 1024 * 1024)
            await ws.send(json.dumps(_env("auth", payload, "b")))
            resp = await _recv_frame(ws, timeout=3.0)
            await ws.close()
            return resp

        stale = await try_auth({"bootstrap": "stale-cred"})
        assert stale["type"] == "error"
        unknown = await try_auth({"bootstrap": "never-issued"})
        assert unknown["type"] == "error"
        bad_token = await try_auth({"token": "wrong"})
        assert bad_token["type"] == "error"

    asyncio.run(scenario())


def test_ws_port_in_registry_and_status(server, tmp_path):
    from daemon.state import load_entry

    srv = server()
    assert srv.ws_port > 0
    assert srv.ws_port != srv.port

    entry = load_entry(srv.project_id, base_dir=tmp_path / "daemons")
    assert entry is not None
    assert entry["ws_port"] == srv.ws_port

    async def scenario():
        client = DaemonClient(host="127.0.0.1", port=srv.port, token=srv.token)
        await client.connect()
        try:
            status = await client.status()
            assert status["ws_port"] == srv.ws_port
        finally:
            await client.close()

    asyncio.run(scenario())


def test_daemon_client_cancel_over_tcp(server):
    """DaemonClient.cancel() stops the most recent run; run() returns the
    cancelled result instead of hanging until the idle timeout."""
    srv = server(events=100, delay=0.02, duration=2.0)

    async def scenario():
        a = DaemonClient(host="127.0.0.1", port=srv.port, token=srv.token)
        b = DaemonClient(host="127.0.0.1", port=srv.port, token=srv.token)
        await a.connect()
        await b.connect()
        started = asyncio.Event()
        events = []

        async def _run():
            return await a.run(
                "long", on_event=lambda n, d: (events.append(n), started.set()))

        run_fut = asyncio.ensure_future(_run())
        await asyncio.wait_for(started.wait(), timeout=5.0)
        await asyncio.sleep(0.2)

        ok = await b.cancel(task_id=a._last_run_id)
        assert ok["message"] == "cancel requested"

        result = await asyncio.wait_for(run_fut, timeout=5.0)
        assert result["cancelled"] is True
        assert result["success"] is False
        assert events, "expected observer events before cancellation"
        await a.close()
        await b.close()

    asyncio.run(scenario())
