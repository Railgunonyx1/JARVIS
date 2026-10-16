"""Hermetic tests for Orbit CDP request-boundary interception (audit P1).

CDPBackend must enforce BrowserNetworkPolicy on EVERY request the page makes —
redirects, subresources, XHR, WebSockets — not just the initial navigation URL.
Enforcement is wired as Fetch.enable + Fetch.requestPaused handled from the
connection's receive loop; these tests drive that handler with a recording
fake connection, so no Chromium, driver, or network access is involved.

Rerun-audit regressions: create_tab must initialize targets at about:blank and
enable interception before the first external navigation, and a DNS answer
that flips between validation and the connection attempt must be denied at
the request boundary.
"""

from __future__ import annotations

import socket

import pytest

from core.locks import OWNER_SYSTEM
from jbrowser.network import NetworkPolicyError
from orbit.cdp import CDPBackend, CDPError


class RecordingConn:
    """Duck-typed CDPConnection: records calls/notifies, stores the handler."""

    def __init__(self, *, enable_error: Exception | None = None,
                 responses: dict | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.notifies: list[tuple[str, dict]] = []
        self.handler = None
        self.closed = False
        self._closed = False
        self._enable_error = enable_error
        self._responses = dict(responses or {})

    def set_event_handler(self, handler) -> None:
        self.handler = handler

    def call(self, method: str, params: dict | None = None) -> dict:
        self.calls.append((method, params or {}))
        if method == "Fetch.enable" and self._enable_error is not None:
            raise self._enable_error
        return dict(self._responses.get(method, {}))

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


def _live_transport(monkeypatch, page_conn: RecordingConn):
    """Backend wired for create_tab: page connections come from ``page_conn``,
    Target.* calls hit a recording browser transport, nothing is launched."""
    created: list[RecordingConn] = []

    def conn_factory(ws, timeout=20.0):
        created.append(page_conn)
        return page_conn

    monkeypatch.setattr("orbit.cdp.CDPConnection", conn_factory)
    backend = CDPBackend(chrome="fake-chrome", auto_launch=False)
    backend.launch = lambda launch_url="about:blank": None
    browser = RecordingConn(responses={
        "Target.createTarget": {"targetId": "target-1"},
    })
    backend._browser_conn = browser
    backend._target_ws = lambda target_id: "ws://fake-target"
    return backend, browser, created


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

    def test_continue_failure_keeps_request_paused_without_crashing(
            self, monkeypatch):
        conn = RecordingConn()
        backend, tab = _backend_with_page(monkeypatch, conn)
        backend._page_conn(tab.tab_id)

        def failing_notify(method, params=None):
            conn.notifies.append((method, params or {}))
            if method == "Fetch.continueRequest":
                raise CDPError("transport closed")

        conn.notify = failing_notify
        _pause(conn, "https://93.184.216.34/app.js")  # must not raise
        assert conn.notifies[-1][0] == "Fetch.continueRequest"


class TestInitialNavigationOrdering:
    """Audit rerun: the first navigation must never start before per-request
    interception is active, and targets must be born at about:blank."""

    @staticmethod
    def _page():
        return RecordingConn(responses={
            "Runtime.evaluate": {"result": {"value": "complete"}},
        })

    def test_target_is_blank_and_interception_precedes_navigation(
            self, monkeypatch):
        conn = self._page()
        backend, browser, created = _live_transport(monkeypatch, conn)
        info = backend.create_tab("sess-1", url="https://93.184.216.34/home")

        targets = [p for m, p in browser.calls if m == "Target.createTarget"]
        assert len(targets) == 1
        assert targets[0]["url"] == "about:blank"
        assert all("93.184.216.34" not in str(p) for _, p in browser.calls)

        methods = [m for m, _ in conn.calls]
        assert methods.index("Fetch.enable") < methods.index("Page.navigate")
        nav = [p for m, p in conn.calls if m == "Page.navigate"][0]
        assert nav["url"] == "https://93.184.216.34/home"
        assert info.url == "https://93.184.216.34/home"
        assert created == [conn]

    def test_private_url_denied_without_any_navigation(self, monkeypatch):
        conn = self._page()
        backend, browser, created = _live_transport(monkeypatch, conn)
        with pytest.raises(NetworkPolicyError):
            backend.create_tab("sess-1", url="http://192.168.1.10/admin")
        assert created == []            # no page connection was ever built
        assert conn.calls == []         # nothing was sent on it
        assert "Target.closeTarget" in [m for m, _ in browser.calls]
        assert backend.list_tabs() == []

    def test_interception_failure_is_fail_closed_and_removes_tab(
            self, monkeypatch):
        conn = RecordingConn(enable_error=CDPError("method not found"))
        backend, browser, _ = _live_transport(monkeypatch, conn)
        with pytest.raises(NetworkPolicyError):
            backend.create_tab("sess-1", url="https://93.184.216.34/")
        assert "Page.navigate" not in [m for m, _ in conn.calls]
        assert conn.closed is True
        assert "Target.closeTarget" in [m for m, _ in browser.calls]
        assert backend.list_tabs() == []

    def test_url_less_tab_stays_blank_and_lazy(self, monkeypatch):
        conn = self._page()
        backend, browser, created = _live_transport(monkeypatch, conn)
        info = backend.create_tab("sess-1")
        targets = [p for m, p in browser.calls if m == "Target.createTarget"]
        assert targets[0]["url"] == "about:blank"
        assert created == []
        assert conn.calls == []
        assert info.url == "about:blank"

    def test_launch_refuses_live_initial_url(self):
        backend = CDPBackend(chrome="fake-chrome", auto_launch=False)
        with pytest.raises(ValueError):
            backend.launch("https://example.com")


class TestDnsRebindingAtRequestBoundary:
    """A DNS answer can change between navigation validation and the actual
    connection attempt; the per-request boundary re-resolves and must deny
    the flip (the residual pause->connect window is documented in
    jbrowser/network.py)."""

    @staticmethod
    def _resolver(monkeypatch, ips: list[str]) -> None:
        calls = {"n": 0}

        def fake_getaddrinfo(host, *args, **kwargs):
            idx = min(calls["n"], len(ips) - 1)
            calls["n"] += 1
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ips[idx], 0))]

        monkeypatch.setattr("jbrowser.network.socket.getaddrinfo", fake_getaddrinfo)

    def test_flip_to_loopback_after_validation_denied_at_boundary(
            self, monkeypatch):
        self._resolver(monkeypatch, ["93.184.216.34", "127.0.0.1"])
        conn = RecordingConn()
        backend, tab = _backend_with_page(monkeypatch, conn)
        # Navigation-time validation saw a public address and allowed it ...
        backend._network.validate("https://flip.example.com/")
        backend._page_conn(tab.tab_id)
        # ... but by request time the name has been rebound to loopback.
        _pause(conn, "https://flip.example.com/asset.js")
        assert conn.notifies[-1] == (
            "Fetch.failRequest",
            {"requestId": "req-1", "errorReason": "BlockedByClient"})

    def test_stable_public_resolution_continues(self, monkeypatch):
        self._resolver(monkeypatch, ["93.184.216.34"])
        conn = RecordingConn()
        backend, tab = _backend_with_page(monkeypatch, conn)
        backend._network.validate("https://stable.example.com/")
        backend._page_conn(tab.tab_id)
        _pause(conn, "https://stable.example.com/asset.js")
        assert conn.notifies[-1] == (
            "Fetch.continueRequest", {"requestId": "req-1"})
