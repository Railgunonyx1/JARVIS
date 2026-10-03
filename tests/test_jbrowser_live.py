"""J-Browser live smoke tests (OPT-IN; skipped by default).

These drive a real Chromium process end-to-end and are deliberately isolated
from the default suite:

  * Gated behind ``JARVIS_RUN_BROWSER_LIVE=1`` so a plain ``pytest`` run stays
    hermetic and never starts a Playwright driver that could disturb other
    asyncio-based provider/router tests in the same process.
  * Tagged ``@pytest.mark.browser`` so they can additionally be excluded by
    marker in CI.
  * The module-scoped fixture tears the backend down (pages/contexts/browser/
    driver) after the module so no native resources leak across files.
"""

from __future__ import annotations

import os

import pytest

from jbrowser.backend.playwright import PlaywrightBackend
from jbrowser.controller import BrowserController

_RUN_LIVE = os.environ.get("JARVIS_RUN_BROWSER_LIVE", "0") == "1"

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        not _RUN_LIVE,
        reason="set JARVIS_RUN_BROWSER_LIVE=1 to run live browser integration tests",
    ),
]


@pytest.fixture(scope="module")
def backend() -> PlaywrightBackend:
    b = PlaywrightBackend(headless=True, block_resources=True)
    if not b.available:
        pytest.skip(
            "Playwright Chromium not installed (pip install playwright && "
            "playwright install chromium)"
        )
    yield b
    b.shutdown()


def _ctrl(b: PlaywrightBackend) -> BrowserController:
    return BrowserController(backend=b)


class TestLiveNavigation:
    def test_open_read_screenshot(self, backend):
        ctrl = _ctrl(backend)
        tab = ctrl.new_tab("https://example.com")
        assert tab["tab_id"].startswith("tab_")
        ctx = ctrl.read()
        assert ctx.title == "Example Domain"
        assert "example" in (ctx.text or "").lower()
        assert any("iana.org" in lnk for lnk in ctx.links)
        shot = ctrl.screenshot()
        assert shot.endswith(".png")

    def test_page_state_persists_across_reads(self, backend):
        ctrl = _ctrl(backend)
        ctrl.new_tab("https://example.com")
        t1 = ctrl.read().title
        t2 = ctrl.read().title
        assert t1 == t2 == "Example Domain"

    def test_tab_listing_and_status(self, backend):
        ctrl = _ctrl(backend)
        before = len(ctrl.list_tabs())
        ctrl.new_tab("https://example.com")
        tabs = ctrl.list_tabs()
        assert len(tabs) == before + 1
        st = ctrl.status()
        assert st["backend"] == "playwright"
        assert st["available"] is True
        assert st["tabs"] == len(tabs)


class TestLiveSessionIsolation:
    def test_sessions_have_distinct_contexts(self, backend):
        ctrl = _ctrl(backend)
        s1 = ctrl.ensure_session("live_iso_a")
        s2 = ctrl.ensure_session("live_iso_b")
        ctrl.new_tab("https://example.com", session_id=s1)
        ctrl.new_tab("https://example.com", session_id=s2)
        assert s1 in backend._contexts
        assert s2 in backend._contexts
        assert backend._contexts[s1] is not backend._contexts[s2]

    def test_close_session_scoped(self, backend):
        ctrl = _ctrl(backend)
        s1 = ctrl.ensure_session("live_close_a")
        s2 = ctrl.ensure_session("live_close_b")
        ctrl.new_tab("https://example.com", session_id=s1)
        ctrl.new_tab("https://example.com", session_id=s2)
        backend.close_session(s1)
        assert s1 not in backend._contexts
        assert s2 in backend._contexts
