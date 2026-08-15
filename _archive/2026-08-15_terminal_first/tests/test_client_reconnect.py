"""DaemonClient reconnect behaviour (Block 2).

Covers bounded exponential-backoff reconnection and the same-id run resend:
when a connection drops mid-run, ``run()`` reconnects and resends the SAME
request id so the daemon's run-id dedupe resumes the kernel task instead of
executing it twice. All tests use fake transports — no daemon, no sockets.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from daemon.client import DaemonClient, DaemonDisconnected  # noqa: E402


class FakeTransport:
    def __init__(self, response=None):
        self.sent = []
        self.response = response or {"type": "ok", "id": "a", "payload": {}}

    async def send(self, message):
        self.sent.append(message)

    async def receive(self):
        return self.response

    async def close(self):
        pass


def test_connect_bounded_retries_then_succeeds(monkeypatch):
    from daemon import client as client_mod

    client = DaemonClient()
    state = {"calls": 0}

    async def flaky_open_connection(host, port):
        state["calls"] += 1
        if state["calls"] == 1:
            raise OSError("connection refused")
        return FakeTransport()

    monkeypatch.setattr(client_mod, "open_connection", flaky_open_connection)

    async def scenario():
        await client.connect_bounded(max_attempts=5, base_delay=0.0)
        assert client.connected
        assert state["calls"] == 2

    asyncio_run(scenario())


def test_connect_bounded_raises_after_exhausting_attempts(monkeypatch):
    from daemon import client as client_mod

    client = DaemonClient()
    state = {"calls": 0}

    async def always_fails(host, port):
        state["calls"] += 1
        raise OSError("connection refused")

    monkeypatch.setattr(client_mod, "open_connection", always_fails)

    async def scenario():
        with pytest.raises(OSError, match="connection refused"):
            await client.connect_bounded(max_attempts=3, base_delay=0.0)
        assert state["calls"] == 3
        assert not client.connected

    asyncio_run(scenario())


class RecordingClient(DaemonClient):
    def __init__(self):
        super().__init__()
        self.sent_rids = []
        self.attempts = 0
        self.reconnects = 0

    async def _run_once(self, rid, goal, mode, on_event):
        self.sent_rids.append(rid)
        self.attempts += 1
        if self.attempts == 1:
            raise DaemonDisconnected("dropped mid-run")
        return {"success": True, "trace_id": f"trace-{goal}"}

    async def connect_bounded(self, **kwargs):
        self.reconnects += 1


def test_run_resends_same_id_after_disconnect():
    client = RecordingClient()

    async def scenario():
        result = await client.run("hello")
        assert result["success"] is True
        assert client.attempts == 2
        assert client.reconnects == 1
        assert client.sent_rids[0] == client.sent_rids[1]
        assert client._last_run_id == client.sent_rids[0]

    asyncio_run(scenario())


def test_run_gives_up_after_max_retries():
    class FailingClient(RecordingClient):
        async def _run_once(self, rid, goal, mode, on_event):
            self.sent_rids.append(rid)
            self.attempts += 1
            raise DaemonDisconnected("dropped")

    client = FailingClient()

    async def scenario():
        with pytest.raises(DaemonDisconnected):
            await client.run("hello")
        assert client.attempts == client.RUN_MAX_RETRIES + 1
        assert len(set(client.sent_rids)) == 1

    asyncio_run(scenario())


def asyncio_run(coro):
    import asyncio

    asyncio.run(coro)
