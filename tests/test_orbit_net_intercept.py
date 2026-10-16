"""Hermetic tests for Orbit CDP request-boundary interception (audit P1).

CDPBackend must enforce BrowserNetworkPolicy on EVERY request the page makes —
redirects, subresources, XHR, WebSockets — not just the initial navigation URL.
Enforcement is wired as Fetch.enable + Fetch.requestPaused handled from the
connection's receive loop; these tests drive that handler with a recording
fake connection, so no Chromium, driver, or network access is involved.
"""

from __future__ import annotations

import pytest

from core.locks import OWNER_SYSTEM
from jbrowser.network import NetworkPolicyError
from orbit.cdp import CDPBackend, CDPError


class RecordingConn:
    """Duck-typed CDPConnection: records calls/notifies, stores the handler."""

    def __init__(self, *, enable_error: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.notifies: list[tuple[str, dict]] = []
        self.handler = None
        self.closed = False
        self._closed = False
        self._enable_error = enable_error

    def set_event_handler(self, handler) -> None:
        self.handler = handler

    def call(self, method: str, params: dict | None = None) -> dict:
        self.calls.append((method, params or {}))
        if method == "Fetch.enable" and self._enable_error is not None:
            raise self._enable_error
        return {}

    def notify(self, method: str, params: dict | None = None) -> None:
        self.notifies.append((method, params or {}))

    def close(self) -> None:
        self.closed = True
        self._closed = True


def _backend_with_page(monkeypatch, conn: RecordingConn):
    monkeypatch.setattr("orbit.cdp.CDPConnection", lambda ws, timeout=20.0: conn)
    backend = CDPBackend(chrome="fake-chrome", auto_launch=False)
    tab = backend._registry.register("target-1", "sess-1", OWNER_SYSTEM)
    tab.ws_url = "ws://fake-target"
    return backend, tab


def _pause(conn: RecordingConn, url: str, request_id: str = "req-1") -> None:
    conn.handler("Fetch.requestPaused",
                 {"requestId": request_id, "request": {"url": url}})


class TestInterceptionEnablement:
    def test_page_conn_enables_request_interception(self, monkeypatch):
        conn = RecordingConn()
        backend, tab = _backend_with_page(monkeypatch, conn)
        page = backend._page_conn(tab.tab_id)
        assert page is conn
        methods = [m for m, _ in conn.calls]
        assert "Fetch.enable" in methods
        params = dict(conn.calls)["Fetch.enable"]
        assert params["patterns"][0]["requestStage"] == "Request"
        assert tab.started_ws is True
        assert conn.handler is not None

    def test_enable_failure_is_fail_closed(self, monkeypatch):
        conn = RecordingConn(enable_error=CDPError("method not found"))
        backend, tab = _backend_with_page(monkeypatch, conn)
        with pytest.raises(NetworkPolicyError):
            backend._page_conn(tab.tab_id)
        assert conn.closed is True
        assert tab.tab_id not in backend._pages

    def test_each_tab_gets_its_own_intercepted_connection(self, monkeypatch):
        conns: list[RecordingConn] = []

        def factory(ws, timeout=20.0):
            c = RecordingConn()
            c.ws = ws
            conns.append(c)
            return c

        monkeypatch.setattr("orbit.cdp.CDPConnection", factory)
        backend = CDPBackend(chrome="fake-chrome", auto_launch=False)
        for i in (1, 2):
            t = backend._registry.register(f"target-{i}", "s", OWNER_SYSTEM)
            t.ws_url = f"ws://fake-{i}"
            backend._page_conn(t.tab_id)
        assert len(conns) == 2
        for c in conns:
            assert [m for m, _ in c.calls].count("Fetch.enable") == 1
            assert c.handler is not None


class TestPausedRequestDecisions:
    @pytest.fixture()
    def wired(self, monkeypatch):
        conn = RecordingConn()
        backend, tab = _backend_with_page(monkeypatch, conn)
        backend._page_conn(tab.tab_id)
        return backend, conn

    def test_public_request_continues(self, wired):
        _, conn = wired
        _pause(conn, "https://93.184.216.34/app.js")
        assert conn.notifies[-1] == (
            "Fetch.continueRequest", {"requestId": "req-1"})

    def test_private_subresource_blocked(self, wired):
        _, conn = wired
        _pause(conn, "http://192.168.1.10/admin")
        method, params = conn.notifies[-1]
        assert method == "Fetch.failRequest"
        assert params["errorReason"] == "BlockedByClient"

    def test_redirect_target_to_loopback_blocked(self, wired):
        _, conn = wired
        _pause(conn, "http://127.0.0.1:8080/internal", request_id="req-redir")
        assert conn.notifies[-1] == (
            "Fetch.failRequest",
            {"requestId": "req-redir", "errorReason": "BlockedByClient"})

    def test_malformed_url_blocked(self, wired):
        _, conn = wired
        _pause(conn, "http://example.com:notaport/")
        assert conn.notifies[-1][0] == "Fetch.failRequest"

    def test_websocket_to_loopback_blocked(self, wired):
        _, conn = wired
        _pause(conn, "ws://127.0.0.1:9222/devtools/browser")
        assert conn.notifies[-1][0] == "Fetch.failRequest"

    def test_inert_scheme_passes_through(self, wired):
        _, conn = wired
        _pause(conn, "data:text/plain,hello", request_id="req-data")
        assert conn.notifies[-1] == (
            "Fetch.continueRequest", {"requestId": "req-data"})

    def test_request_without_url_blocked(self, wired):
        _, conn = wired
        conn.handler("Fetch.requestPaused",
                     {"requestId": "req-nourl", "request": {}})
        assert conn.notifies[-1] == (
            "Fetch.failRequest",
            {"requestId": "req-nourl", "errorReason": "BlockedByClient"})
