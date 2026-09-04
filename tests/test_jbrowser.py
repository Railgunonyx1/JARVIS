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
    def screenshot(self, path=None, tab_id=None):
        return "/tmp/fake.png"
    def click(self, handle, tab_id=None): return True
    def type_text(self, handle, text, tab_id=None): return True
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
