"""Hermetic tests for the JARVIS Orbit CDP subsystem (G4).

The whole suite is safe in the default (no-browser) pipeline: Chromium launching
is avoided by a fake CDP transport, so CDPBackend/registry/ownership/tools can
be verified without any Playwright driver or Chrome binary.
"""

from __future__ import annotations

import asyncio
import json
import time
import types
from pathlib import Path

import pytest

from core.locks import OWNER_AGENT, OWNER_SYSTEM, OWNER_USER, get_resource_lock
from jbrowser.controller import BrowserController
from orbit.cdp import CDPBackend, NetworkPolicyError
from orbit.registry import TargetRegistry
from orbit.tools import build_orbit_tools


# ---------------------------------------------------------------------------
# Fake CDP transport: an in-memory connection that answers CDP commands and
# exposes a tiny page model so evaluate/click/type behave like a mini browser.
# ---------------------------------------------------------------------------

class FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.title = "Fake"
        self.body = "hello from the fake page"
        self.interactives_json = [
            {
                "handle": "el0", "tag": "a", "kind": "link",
                "label": "Example", "text": "Example", "href": "https://example.com",
                "visible": True,
            },
            {
                "handle": "el1", "tag": "input", "kind": "input",
                "label": "Search", "text": "Search", "href": "",
                "visible": True,
            },
        ]
        self.clicked: list[str] = []
        self.typed: list[str] = []

    def snapshot(self) -> dict:
        return {
            "url": self.url, "title": self.title,
            "interactives": self.interactives_json,
            "links": ["https://example.com"],
            "forms": [{"action": self.url, "method": "get"}],
            "viewport": {"w": 800, "h": 600},
            "total": 2,
        }


class FakeConn:
    """In-memory CDP connection (browser-level OR page-level) over FakePage."""

    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.calls: list[tuple[str, dict]] = []
        self._closed = False
        self._next_target = 1

    # ---- CDPConnection surface ---------------------------------------
    def call(self, method: str, params: dict | None = None) -> dict:
        params = params or {}
        self.calls.append((method, params))
        return self._handle(method, params)

    def close(self) -> None:
        self._closed = True

    def wait_for_event(self, method_prefix: str, *, timeout: float = 10.0,
                       predicate=None):
        return None

    def consume_events(self, method_prefix: str) -> list:
        return []

    # ---- CDP command routing -----------------------------------------
    def _handle(self, method: str, params: dict) -> dict:
        if method == "Runtime.evaluate":
            return self._evaluate(params.get("expression", ""))
        if method == "Page.navigate":
            self.page.url = params.get("url", self.page.url)
            return {}
        if method == "Page.captureScreenshot":
            return {"data": "aGVsbG8="}
        if method == "Target.createTarget":
            tid = f"target-fake-{self._next_target}"
            self._next_target += 1
            return {"targetId": tid}
        if method == "Target.closeTarget":
            return {}
        if method == "Target.getTargets":
            return {"targetInfos": [{
                "type": "page", "id": "target-fake-1",
                "url": self.page.url, "title": self.page.title,
            }]}
        if method in ("Page.enable", "DOM.enable", "Runtime.enable"):
            return {}
        if method == "Page.getNavigationHistory":
            return {"currentIndex": 0, "entries": [{"id": 1, "url": self.page.url}]}
        if method == "Page.navigateToHistoryEntry":
            return {}
        if method == "Page.reload":
            return {}
        return {}

    def _evaluate(self, expr: str) -> dict:
        if "location.href" in expr and "querySelectorAll" not in expr:
            return {"result": {"type": "string",
                               "value": json.dumps(
                                   {"url": self.page.url, "title": self.page.title})}}
        if "innerText" in expr and "querySelectorAll" not in expr:
            return {"result": {"type": "string", "value": self.page.body}}
        if "document.readyState" in expr:
            return {"result": {"type": "string", "value": "complete"}}
        if "return JSON.stringify({ok:" in expr:
            return {"result": {"type": "string",
                               "value": json.dumps({"ok": True, "tag": "A"})}}
        if ".click()" in expr or "scrollIntoView" in expr:
            self.page.clicked.append(expr)
            return {"result": {"type": "boolean", "value": True}}
        if "value=" in expr or "dispatchEvent" in expr:
            self.page.typed.append(expr)
            return {"result": {"type": "boolean", "value": True}}
        if "scrollTo" in expr or "scrollBy" in expr:
            return {"result": {"type": "undefined", "value": None}}
        if "querySelectorAll" in expr:
            return {"result": {"type": "string",
                               "value": json.dumps(self.page.snapshot())}}
        if "return false" in expr:
            return {"result": {"type": "boolean", "value": False}}
        if "location.href" in expr:
            return {"result": {"type": "string", "value": self.page.url}}
        if "document.title" in expr:
            return {"result": {"type": "string", "value": self.page.title}}
        return {"result": {"type": "undefined", "value": None}}


def make_backend(page: FakePage | None = None) -> CDPBackend:
    """Build a CDPBackend with a fake transport, never touching a real browser."""
    page = page or FakePage()
    conn = FakeConn(page)
    backend = CDPBackend(chrome="fake-chrome", headless=True, auto_launch=True)

    def fake_launch(self, launch_url="about:blank"):
        self._started = True
        self._launched = True
        self._base = "http://127.0.0.1:0"

    def fake_page_conn(self, tab_id: str):
        return conn

    backend.launch = types.MethodType(fake_launch, backend)
    backend._page_conn = types.MethodType(fake_page_conn, backend)
    backend._browser_conn = conn
    return backend


# ---------------------------------------------------------------------------
# CDPConnection-ish transport behaviour
# ---------------------------------------------------------------------------

class TestFakeTransport:
    def test_evaluate_reads_page(self):
        page = FakePage()
        conn = FakeConn(page)
        res = conn.call("Runtime.evaluate", {"expression": "location.href"})
        assert "about:blank" in res["result"]["value"]
        assert conn.call("Page.navigate", {"url": "https://example.com/"}) == {}

    def test_snapshot_shape(self):
        ctx = FakePage().snapshot()
        assert {"interactives", "links", "forms", "viewport"} <= set(ctx)


# ---------------------------------------------------------------------------
# TargetRegistry + ownership (G4 core)
# ---------------------------------------------------------------------------

class TestTargetRegistry:
    def test_register_and_stable_ids(self):
        reg = TargetRegistry(locks=get_resource_lock())
        t1 = reg.register("tgt-1", "sess", OWNER_USER)
        t2 = reg.register("tgt-2", "sess", OWNER_AGENT)
        assert t1.tab_id != t2.tab_id
        assert t1.tab_id.startswith("tab_")
        assert reg.by_target("tgt-1").tab_id == t1.tab_id
        assert reg.active().tab_id == t1.tab_id
        assert reg.status()["targets"] == 2

    def test_reregister_same_target_is_idempotent(self):
        reg = TargetRegistry(locks=get_resource_lock())
        a = reg.register("tgt-x", "s", OWNER_USER)
        b = reg.register("tgt-x", "s", OWNER_USER)
        assert a.tab_id == b.tab_id

    def test_ownership_conflict_is_locked(self):
        from core.locks import ResourceLockedError
        reg = TargetRegistry(locks=get_resource_lock())
        t = reg.register("tgt-1", "s", OWNER_USER)
        reg.own(t.tab_id, OWNER_USER)
        with pytest.raises(ResourceLockedError):
            reg.own(t.tab_id, OWNER_AGENT)
        assert reg.owner_of(t.tab_id) == OWNER_USER
        reg.release(t.tab_id, OWNER_USER)
        assert reg.owner_of(t.tab_id) == OWNER_SYSTEM

    def test_remove_active_repairs_pointer(self):
        reg = TargetRegistry(locks=get_resource_lock())
        a = reg.register("tgt-a", "s", OWNER_USER)
        reg.register("tgt-b", "s", OWNER_AGENT)
        assert reg.remove(a.tab_id)
        assert reg.by_target("tgt-a") is None
        assert reg.active() and reg.active().target_id == "tgt-b"


# ---------------------------------------------------------------------------
# CDPBackend lifecycle / navigation / read / act (hermetic via fake transport)
# ---------------------------------------------------------------------------

class TestCDPBackend:
    def test_create_tab_navigates_then_reads(self):
        page = FakePage()
        backend = make_backend(page)

        info = backend.create_tab("sess-1", url="https://example.com")
        assert info.tab_id.startswith("tab_")
        tab = backend.registry.lookup(info.tab_id)
        assert tab.target_id == "target-fake-1"
        assert backend.registry.is_owned_by(info.tab_id, OWNER_SYSTEM)

        page.url = "https://example.com/docs"
        page.body = "the docs page says hello orbit"
        nav = backend.navigate("https://example.com/docs", tab_id=info.tab_id)
        assert nav.url == "https://example.com/docs"
        text = backend.get_page_text(tab_id=info.tab_id)
        assert "docs" in text
        snap = backend.get_dom_snapshot(tab_id=info.tab_id)
        assert snap["interactives"][0]["handle"] == "el0"
        assert snap["links"] == ["https://example.com"]
        assert snap["viewport"] == {"w": 800, "h": 600}
        assert snap["forms"][0]["method"] == "get"

        title = backend.get_title(tab_id=info.tab_id)
        assert title  # Fake page reports "Fake"—updated via JS title read
        backend.shutdown()

    def test_tab_lifecycle_and_active(self):
        backend = make_backend()
        a = backend.create_tab("s")
        b = backend.create_tab("s")
        assert len(backend.list_tabs()) == 2
        assert backend.registry.active().tab_id == b.tab_id
        backend.switch_tab(a.tab_id)
        assert backend.active_tab().tab_id == a.tab_id
        assert backend.close_tab(a.tab_id)
        assert backend.close_tab(a.tab_id) is False
        backend.shutdown()

    def test_network_policy_denies_loopback(self):
        backend = make_backend()
        with pytest.raises(NetworkPolicyError):
            backend._network.validate("http://127.0.0.1:3000/x")
        with pytest.raises(NetworkPolicyError):
            backend._network.validate("http://localhost/x")
        with pytest.raises(NetworkPolicyError):
            backend._network.validate("http://192.168.1.10/x")
        assert backend._network.validate("https://example.com") == "https://example.com"
        backend.shutdown()

    def test_click_and_type_route_through_backend(self):
        page = FakePage()
        backend = make_backend(page)
        info = backend.create_tab("s")
        assert backend.click("el0", tab_id=info.tab_id) is True
        assert backend.type_text("el1", "orbit", tab_id=info.tab_id) is True
        assert page.clicked and page.typed
        backend.shutdown()


# ---------------------------------------------------------------------------
# Orbit tools + classification
# ---------------------------------------------------------------------------

class TestOrbitTools:
    def test_catalog_is_classified_and_complete(self):
        tools = {t.name: t for t in build_orbit_tools()}
        assert "orbit.navigate" in tools
        assert "orbit.read" in tools
        # Browser mutations must be high + destructive (approval-gated)
        assert tools["orbit.execute_script"].risk in ("high", "critical")
        assert tools["orbit.execute_script"].is_destructive
        assert tools["orbit.execute_script"].side_effects == ("network_egress",)
        assert tools["orbit.navigate"].risk == "low"
        assert tools["orbit.navigate"].is_destructive is False
        assert tools["orbit.navigate"].permission == "orbit.browser.open"

    def test_registry_register_many(self):
        from tools.registry import ToolRegistry
        reg = ToolRegistry()
        reg.register_many(build_orbit_tools())
        assert reg.get("orbit.navigate") is not None
        assert len(reg.list()) == len(build_orbit_tools())


# ---------------------------------------------------------------------------
# Vertical slice: DSH request -> ToolExecutionService -> tool -> CDP -> read
# ---------------------------------------------------------------------------

class TestOrbitRuntimeSlice:
    def test_vertical_slice_via_tool_service(self, monkeypatch):
        from orbit import tools as orbit_tools_mod
        from orbit.runtime import OrbitRuntime

        page = FakePage()
        page.body = "the docs page says hello orbit"
        backend = make_backend(page)
        ctl = BrowserController(backend=backend, profile_root=Path("."))
        monkeypatch.setattr(orbit_tools_mod, "get_orbit_controller", lambda *a, **k: ctl)

        runtime = OrbitRuntime()

        async def run():
            first = await runtime.handle_command(
                {"action": "browse", "tool": "orbit.navigate",
                 "arguments": {"url": "https://example.com/docs"}},
                trace_id="tr-1", session_id="sess-1",
            )
            read = await runtime.handle_command(
                {"tool": "orbit.read"},
                trace_id="tr-1", session_id="sess-1",
            )
            return first, read

        first, read = asyncio.run(run())
        assert first["success"] is True
        assert first["permission_denied"] is False
        assert first["output"].startswith("Title:")
        assert read["success"] is True
        assert "docs page" in read["output"]
        assert "URL:" in read["output"]

    def test_browse_action_enriches_with_readback(self, monkeypatch):
        from orbit import tools as orbit_tools_mod
        from orbit.runtime import OrbitRuntime

        page = FakePage()
        page.url = "https://example.com/app"
        page.body = "welcome to the orbit dashboard"
        backend = make_backend(page)
        ctl = BrowserController(backend=backend, profile_root=Path("."))
        monkeypatch.setattr(orbit_tools_mod, "get_orbit_controller", lambda *a, **k: ctl)

        runtime = OrbitRuntime()

        async def run():
            return await runtime.handle_command(
                {"action": "browse", "tool": "orbit.navigate",
                 "arguments": {"url": "https://example.com/app"}},
                trace_id="tr-1", session_id="sess-1",
            )

        payload = asyncio.run(run())
        assert payload["success"] is True
        assert payload["readback"]["page"]["title"] == "Fake"
        assert "dashboard" in payload["readback"]["page"]["text_preview"]

    def test_command_requires_tool(self):
        from orbit.runtime import OrbitRuntime
        runtime = OrbitRuntime()

        async def run():
            return await runtime.handle_command({}, trace_id="t", session_id="s")

        res = asyncio.run(run())
        assert res["success"] is False
        assert "command" in res["error"]

    def test_unregistered_tool_reports_malformed(self):
        from orbit.runtime import OrbitRuntime
        runtime = OrbitRuntime()

        async def run():
            return await runtime.handle_command(
                {"tool": "orbit.does_not_exist"}, trace_id="t", session_id="s")

        res = asyncio.run(run())
        assert res["success"] is False
        assert "not registered" in res["error"]

    def test_session_cleanup_releases_controller(self, monkeypatch):
        from orbit import tools as orbit_tools_mod
        from orbit.runtime import OrbitRuntime

        page = FakePage()
        backend = make_backend(page)
        ctl = BrowserController(backend=backend, profile_root=Path("."))
        monkeypatch.setattr(orbit_tools_mod, "get_orbit_controller", lambda *a, **k: ctl)
        runtime = OrbitRuntime()

        async def run():
            return await runtime.handle_command({"action": "cleanup"},
                                                trace_id="t", session_id="s")

        res = asyncio.run(run())
        assert res["success"] is True