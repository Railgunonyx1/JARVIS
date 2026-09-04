"""J-Browser platform tests.

Covers the browser platform units without requiring Playwright: optimization
profile, risk classification, tab/session identity, page-context extraction
(via a fake page), and the controller facade with a fake backend verifying
event emission on the EventBus.
"""

from __future__ import annotations

from jbrowser.controller import BrowserController, get_controller, reset_controller
from jbrowser.optimization import as_chromium_args, build_launch_kwargs
from jbrowser.page_context import build_page_context
from jbrowser.permissions import (
    describe_permissions,
    permission_key_for_tool,
    requires_approval,
    risk_for_tool,
)
from jbrowser.sessions import SessionManager
from jbrowser.tabs import TabContext, TabManager, new_tab_id
from runtime.event_bus import get_event_bus

# ---------------------------------------------------------------------------
# Optimization profile
# ---------------------------------------------------------------------------

class TestOptimizationProfile:
    def test_launch_args_include_optimized_flags(self):
        args = as_chromium_args()
        assert "--enable-gpu-rasterization" in args
        assert "--enable-quic" in args
        assert any(a.startswith("--num-raster-threads=") for a in args)

    def test_preserve_tabs_drops_memory_saver(self):
        slim = as_chromium_args(preserve_tabs=False)
        alive = as_chromium_args(preserve_tabs=True)
        assert "--freeze-background-tabs" in slim
        assert "--freeze-background-tabs" not in alive

    def test_launch_kwargs_shape(self):
        kwargs = build_launch_kwargs()
        assert isinstance(kwargs["args"], list)
        assert all(isinstance(a, str) for a in kwargs["args"])

    def test_memory_and_startup_flags_present(self):
        joined = " ".join(as_chromium_args())
        for flag in ("mute-audio", "disable-extensions", "no-first-run",
                     "disable-background-networking", "hide-scrollbars",
                     "disable-background-timer-throttling"):
            assert f"--{flag}" in joined, flag

    def test_occlusion_flags_present(self):
        args = as_chromium_args()
        assert "--disable-backgrounding-occluded-windows" in args
        assert "CalculateNativeWinOcclusion" in " ".join(args)

    def test_screenshot_kinds_keep_layout(self):
        from jbrowser.optimization import (
            RESOURCE_BLOCK_KEEP_FOR_SCREENSHOT,
            RESOURCE_BLOCK_KINDS,
        )
        kept = RESOURCE_BLOCK_KEEP_FOR_SCREENSHOT
        assert kept < RESOURCE_BLOCK_KINDS
        assert "image" in kept and "stylesheet" in kept

    def test_tab_limit_math(self):
        from jbrowser.optimization import DEFAULT_TAB_LIMIT, enforce_tab_limit
        assert enforce_tab_limit(5) == 0
        assert enforce_tab_limit(DEFAULT_TAB_LIMIT) == 0
        assert enforce_tab_limit(DEFAULT_TAB_LIMIT + 3) == 3


# ---------------------------------------------------------------------------
# Risk permissions
# ---------------------------------------------------------------------------

class TestPermissions:
    def test_low_risk(self):
        assert risk_for_tool("browser.read").value == "low"
        assert risk_for_tool("browser.navigate").value == "low"
        assert risk_for_tool("browser.tabs").value == "low"

    def test_medium_risk(self):
        assert risk_for_tool("browser.click").value == "medium"

    def test_high_risk_requires_approval(self):
        assert requires_approval("browser.submit")
        assert requires_approval("browser.execute_script")
        assert requires_approval("browser.delete")
        assert not requires_approval("browser.read")

    def test_permission_key_tiered(self):
        assert permission_key_for_tool("browser.submit") == "browser.high"
        assert permission_key_for_tool("browser.open") == "browser.low"

    def test_describe_permissions_has_all_tiers(self):
        perms = describe_permissions()
        assert set(perms) == {"low", "medium", "high"}
        assert "browser.read" in perms["low"]
        assert "browser.click" in perms["medium"]
        assert "browser.execute_script" in perms["high"]


# ---------------------------------------------------------------------------
# Tab identity
# ---------------------------------------------------------------------------

class TestTabManager:
    def test_stable_ids_not_indices(self):
        tm = TabManager()
        a = new_tab_id()
        b = new_tab_id()
        assert a != b
        tm.register(TabContext(tab_id=a, session_id="s1"))
        tm.register(TabContext(tab_id=b, session_id="s1"))
        assert len(tm) == 2
        # removing then re-adding a different id must not confuse lookups
        tm.remove(a)
        assert tm.get(b) is not None

    def test_activate_sets_active_flags(self):
        tm = TabManager()
        a = new_tab_id()
        b = new_tab_id()
        tm.register(TabContext(tab_id=a, session_id="s1"))
        tm.register(TabContext(tab_id=b, session_id="s1"))
        tm.activate(b)
        assert tm.active().tab_id == b
        assert tm.get(a).active is False
        assert tm.get(b).active is True

    def test_active_refills_after_remove(self):
        tm = TabManager()
        a = new_tab_id()
        b = new_tab_id()
        tm.register(TabContext(tab_id=a, session_id="s1"))
        tm.register(TabContext(tab_id=b, session_id="s1"))
        tm.activate(a)
        tm.remove(a)
        assert tm.active() is not None

    def test_list_filters_by_session(self):
        tm = TabManager()
        a = new_tab_id()
        b = new_tab_id()
        tm.register(TabContext(tab_id=a, session_id="s1"))
        tm.register(TabContext(tab_id=b, session_id="s2"))
        assert {t.session_id for t in tm.list("s1")} == {"s1"}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

class TestSessions:
    def test_get_or_create_deduplicates(self):
        sm = SessionManager()
        s1 = sm.get_or_create("abc")
        s2 = sm.get_or_create("abc")
        assert s1 is s2

    def test_persistent_session_gets_user_data_dir(self):
        sm = SessionManager()
        s = sm.get_or_create(persistent=True)
        assert s.user_data_dir is not None
        assert s.persistent is True


# ---------------------------------------------------------------------------
# Page context
# ---------------------------------------------------------------------------

class _FakeEl:
    def __init__(self, tag, text="", href=None, label="", name=""):
        self.tag = tag
        self.text = text
        self.href = href
        self.label = label
        self.name = name

    def evaluate(self, js):  # noqa: ARG002
        return self.tag

    def get_attribute(self, name):
        return {
            "href": self.href, "aria-label": self.label, "name": self.name,
        }.get(name)

    def inner_text(self):
        return self.text


class _FakePage:
    url = "https://example.com"
    body = "Hello world\nSome link text here"

    def title(self):
        return "Example Title"

    def evaluate(self, js, arg=None):  # noqa: ARG002
        if "innerText" in js:
            return self.body
        if "tagName" in js:
            return self.tag
        if "innerWidth" in js:
            return {"w": 1000, "h": 800}
        if "scrollTo" in js:
            return None
        return None

    def eval_on_selector_all(self, sel, js):  # noqa: ARG002
        if "href" in js:
            return ["https://a.com", "https://b.com"]
        return []

    def query_selector_all(self, sel):  # noqa: ARG002
        return [
            _FakeEl("A", "Docs", href="https://docs.example.com"),
            _FakeEl("BUTTON", "Go"),
            _FakeEl("INPUT", "", name="q"),
        ]


class TestPageContext:
    def test_builds_structured_context(self):
        ctx = build_page_context(_FakePage())
        assert ctx.url == "https://example.com"
        assert ctx.title == "Example Title"
        assert ctx.text == "Hello world\nSome link text here"
        assert len(ctx.interactives) == 3
        assert ctx.interactives[0]["handle"] == "el0"
        assert ctx.interactives[0]["tag"] == "a"
        assert ctx.interactives[2]["tag"] == "input"
        assert ctx.links == ["https://a.com", "https://b.com"]

    def test_prompt_block_renders(self):
        ctx = build_page_context(_FakePage())
        block = ctx.to_prompt_block()
        assert "https://example.com" in block
        assert "[el0]" in block
        assert "Links" in block


# ---------------------------------------------------------------------------
# Controller facade + EventBus
# ---------------------------------------------------------------------------

class _FakeBackend:
    """Minimal BrowserBackend duck-type for exercising the controller."""

    def __init__(self):
        from jbrowser.tabs import TabManager
        self.tabs = TabManager()
        self.sessions = set()
        self._active = None

    def create_session(self, session_id, *, persistent=False):
        self.sessions.add(session_id)

    def close_session(self, session_id=None):
        self.sessions.discard(session_id)

    def status(self):
        return {"backend": "fake", "available": True, "launched": True,
                "headless": True, "tabs": len(self.tabs), "active_tab": self._active}

    def create_tab(self, session_id, url=""):
        from jbrowser.tabs import TabContext, new_tab_id
        tab_id = new_tab_id()
        self.tabs.register(TabContext(tab_id=tab_id, session_id=session_id, url=url))
        self.tabs.activate(tab_id)
        self._active = tab_id
        from jbrowser.backend.base import TabInfo
        return TabInfo(tab_id=tab_id, session_id=session_id, url=url)

    def close_tab(self, tab_id):
        self.tabs.remove(tab_id)
        return True

    def list_tabs(self, session_id=None):
        return [self._to_info(t) for t in self.tabs.list(session_id)]

    def _to_info(self, ctx):
        from jbrowser.backend.base import TabInfo
        return TabInfo(tab_id=ctx.tab_id, session_id=ctx.session_id,
                       url=ctx.url, title=ctx.title, active=ctx.active)

    def switch_tab(self, tab_id):
        ctx = self.tabs.activate(tab_id)
        self._active = tab_id
        return self._to_info(ctx)

    def active_tab(self):
        return self.tabs.active()

    def navigate(self, url, tab_id=None):
        tab_id = tab_id or self._active
        ctx = self.tabs.get(tab_id)
        if ctx:
            ctx.url = url
            ctx.title = "FakeTitle"
        return self._to_info(ctx) if ctx else None

    def go_back(self, tab_id=None): pass
    def go_forward(self, tab_id=None): pass
    def reload(self, tab_id=None): pass
    def get_url(self, tab_id=None):
        ctx = self.tabs.active()
        return ctx.url if ctx else ""
    def get_title(self, tab_id=None):
        return "FakeTitle"
    def get_page_text(self, tab_id=None):
        return "page text"
    def get_dom_snapshot(self, tab_id=None):
        return {"url": "u", "title": "t", "interactives": [], "links": [],
                "forms": [], "viewport": {"w": 1000, "h": 800}}
    def get_selector_text(self, selector=None, tab_id=None):
        return "selector text" if selector else "page text"
    def screenshot(self, path=None, tab_id=None):
        return "/tmp/fake.png"
    def click(self, handle, tab_id=None): return True
    def type_text(self, handle, text, tab_id=None): return True
    def click_selector(self, selector, tab_id=None): return True
    def type_selector(self, selector, text, tab_id=None): return True
    def scroll(self, direction, amount=500, tab_id=None): pass
    def execute_script(self, script, tab_id=None): return "42"


class TestController:
    def test_new_tab_emits_event(self):
        reset_controller()
        bus = get_event_bus()
        bus.clear()
        controller = BrowserController(backend=_FakeBackend())
        controller.new_tab("https://ex.com")
        names = [e.name for e in bus.recent(50)]
        assert "browser.tab.created" in names

    def test_navigate_sets_active_tab_and_status(self):
        controller = BrowserController(backend=_FakeBackend())
        controller.ensure_session()
        controller.new_tab("")
        controller.navigate("https://example.org")
        assert controller.status()["backend"] == "fake"
        assert controller.status()["tabs"] >= 1

    def test_read_returns_page_context(self):
        controller = BrowserController(backend=_FakeBackend())
        controller.new_tab("https://ex.com")
        ctx = controller.read()
        assert ctx.url == "https://ex.com"

    def test_tab_listing(self):
        controller = BrowserController(backend=_FakeBackend())
        controller.new_tab("https://a.com")
        controller.new_tab("https://b.com")
        tabs = controller.list_tabs()
        assert len(tabs) >= 2

    def test_singleton_shared(self):
        reset_controller()
        c1 = get_controller()
        c2 = get_controller()
        assert c1 is c2
        reset_controller()


class TestToolRegistryIntegration:
    def test_jbrowser_tools_registered(self):
        from tools import build_default_registry
        names = {t.name for t in build_default_registry().list()}
        for expected in ("browser.read", "browser.tabs", "browser.new_tab",
                         "browser.switch_tab", "browser.find", "browser.scroll",
                         "browser.profile", "browser.permissions", "browser.close_tab"):
            assert expected in names, expected


class TestSkillsTransfer:
    def test_skills_inherited_from_jarvis(self):
        from jbrowser.skills import inherited_skills
        skills = inherited_skills()
        assert len(skills) >= 10
        by_name = {s.name: s for s in skills}
        assert "browser_automation" in by_name
        assert "web_research" in by_name

    def test_browser_skills_subset(self):
        from jbrowser.skills import browser_skills
        names = {s.name for s in browser_skills()}
        assert "browser_automation" in names
        assert "web_research" in names
        # every browser skill must also appear in the inherited set
        inherited = {s.name for s in __import__("jbrowser.skills", fromlist=["inherited_skills"]).inherited_skills()}
        assert names <= inherited


class TestLegacyBrowserCompatibility:
    """Legacy tools/browser.py handlers must route through the controller."""

    def _controller_with_fake(self) -> BrowserController:
        reset_controller()
        import jbrowser.controller as jbc
        with jbc._controller_lock:
            jbc._controller = BrowserController(backend=_FakeBackend())
        return jbc.get_controller()

    def test_open_delegates_to_controller(self):
        from tools.browser import browser_open
        self._controller_with_fake()
        res = browser_open({"url": "example.com"})
        assert res.success is True
        assert res.output
        assert res.metadata["url"]

    def test_open_requires_url(self):
        from tools.browser import browser_open
        self._controller_with_fake()
        res = browser_open({"url": "  "})
        assert res.success is False

    def test_click_selector_delegates(self):
        from tools.browser import browser_click
        self._controller_with_fake()
        res = browser_click({"selector": "#btn"})
        assert res.success is True
        assert res.metadata["selector"] == "#btn"

    def test_click_requires_selector(self):
        from tools.browser import browser_click
        self._controller_with_fake()
        res = browser_click({"selector": ""})
        assert res.success is False

    def test_type_delegates(self):
        from tools.browser import browser_type
        self._controller_with_fake()
        res = browser_type({"selector": "#q", "text": "hello"})
        assert res.success is True
        assert res.metadata["chars"] == 5

    def test_extract_delegates(self):
        from tools.browser import browser_extract
        self._controller_with_fake()
        res = browser_extract({"selector": "#content"})
        assert res.success is True
        assert res.metadata["chars"] >= 0

    def test_status_delegates(self):
        from tools.browser import browser_status
        self._controller_with_fake()
        res = browser_status({})
        assert res.success is True
        assert "backend" in res.output

    def test_screenshot_delegates(self):
        from tools.browser import browser_screenshot
        self._controller_with_fake()
        res = browser_screenshot({})
        assert res.success is True
        assert res.metadata["path"]

    def test_browser_agent_adapter_delegates(self):
        from external.browser_agent import BrowserAgent
        self._controller_with_fake()
        agent = BrowserAgent()
        assert agent.open("example.org")["backend"] == "fake"
        assert agent.click("#b") is True
        assert agent.type_text("#q", "x") is True
        assert agent.extract_text("#c") == "selector text"
        assert agent.status()["backend"] == "fake"


class _FakeRoute:
    def __init__(self, resource_type):
        self.request = type("R", (), {"resource_type": resource_type})()
        self.aborted = False
        self.continued = False

    def abort(self):
        self.aborted = True

    def continue_(self):
        self.continued = True


class TestResourceBlocking:
    def test_handler_aborts_blocked_kinds(self):
        from jbrowser.optimization import build_resource_blocking
        cfg = build_resource_blocking()
        route = _FakeRoute("image")
        cfg["handler"](route)
        assert route.aborted is True

    def test_handler_continues_other_kinds(self):
        from jbrowser.optimization import build_resource_blocking
        cfg = build_resource_blocking()
        route = _FakeRoute("script")
        cfg["handler"](route)
        assert route.continued is True

    def test_custom_kinds_respected(self):
        from jbrowser.optimization import build_resource_blocking
        cfg = build_resource_blocking(frozenset({"font"}))
        assert cfg["kinds"] == frozenset({"font"})
        blocked = _FakeRoute("font")
        cfg["handler"](blocked)
        assert blocked.aborted is True
        passed = _FakeRoute("image")
        cfg["handler"](passed)
        assert passed.continued is True

    def test_playwright_backend_installs_routing(self):
        from jbrowser.backend.playwright import PlaywrightBackend
        backend = PlaywrightBackend(block_resources=True)
        assert backend._blocking is not None
        assert backend._blocking["kinds"]  # default kinds populated


class TestToolExecutionServiceIntegration:
    """J-Browser tools must execute through the single boundary (no bypass)."""

    def _svc_with_fake(self):
        import asyncio

        from core.agent.tool_service import ToolExecutionService
        from tools import build_default_registry
        reset_controller()
        import jbrowser.controller as jbc
        with jbc._controller_lock:
            jbc._controller = BrowserController(backend=_FakeBackend())
        return asyncio, ToolExecutionService(registry=build_default_registry())

    def _run(self, svc, asyncio, name, arguments, tool_id):
        from providers.types import ToolCall
        return asyncio.run(svc.execute_tool(ToolCall(
            name=name, arguments=arguments, id=tool_id)))

    def test_status_through_boundary(self):
        asyncio, svc = self._svc_with_fake()
        res = self._run(svc, asyncio, "browser.status", {}, "jb1")
        assert res.success is True
        assert "Browser backend" in res.output
        assert "fake" in res.output

    def test_new_tab_through_boundary(self):
        asyncio, svc = self._svc_with_fake()
        res = self._run(svc, asyncio, "browser.new_tab",
                        {"url": "https://ex.com"}, "jb2")
        assert res.success is True
        assert res.metadata["tab_id"].startswith("tab_")

    def test_tabs_listing_through_boundary(self):
        asyncio, svc = self._svc_with_fake()
        self._run(svc, asyncio, "browser.new_tab", {"url": "https://a.com"}, "jb3")
        res = self._run(svc, asyncio, "browser.tabs", {}, "jb4")
        assert res.success is True
        assert len(res.metadata["tabs"]) >= 1

    def test_read_through_boundary(self):
        asyncio, svc = self._svc_with_fake()
        self._run(svc, asyncio, "browser.new_tab", {"url": "https://ex.com"}, "jb5")
        res = self._run(svc, asyncio, "browser.read", {}, "jb6")
        assert res.success is True
        assert res.metadata["url"]

    def test_unknown_tool_still_rejected(self):
        asyncio, svc = self._svc_with_fake()
        res = self._run(svc, asyncio, "browser.not_a_tool", {}, "jb7")
        assert res.success is False


class TestSessionPersistence:
    def test_persistent_profile_roundtrip(self):
        import tempfile
        from pathlib import Path

        from jbrowser.sessions import BrowserSession, SessionManager, profile_dir
        root = Path(tempfile.mkdtemp())
        sid = "sess_persist"
        session = BrowserSession(sid, persistent=True, profile_root=root)
        expected = profile_dir(root, sid)
        assert session.user_data_dir == expected
        assert expected.exists()
        manager = SessionManager()
        again = manager.get_or_create(sid, persistent=True, profile_root=root)
        assert again is not session  # new manager instance
        assert again.user_data_dir == expected
        assert expected.exists()

    def test_ephemeral_session_no_profile_dir(self):
        from jbrowser.sessions import BrowserSession
        session = BrowserSession(persistent=False)
        assert session.user_data_dir is None
        assert session.persistent is False

    def test_session_describe(self):
        from jbrowser.sessions import BrowserSession
        session = BrowserSession("s1")
        desc = session.describe()
        assert desc["session_id"] == "s1"
        assert desc["persistent"] is False


