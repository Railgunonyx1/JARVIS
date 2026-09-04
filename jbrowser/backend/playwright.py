"""J-Browser — Playwright/Chromium backend.

A :class:`BrowserBackend` implementation over Playwright + Chromium. It
refactors the legacy single-page ``external.browser_agent.BrowserAgent`` into
a multi-tab, multi-session, persistent-profile capable backend while keeping
the two hard constraints:
  - lazy launch / never-resident (daemon-first, 512MB),
  - graceful WebScraper fallback when Playwright (or its binary) is absent.

Optimizations from :mod:`jbrowser.optimization` are applied to the Chromium
launch automatically.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from typing import Any

from jbrowser.backend.base import BrowserBackend, TabInfo
from jbrowser.optimization import build_launch_kwargs
from jbrowser.page_context import build_page_context
from jbrowser.tabs import TabContext, TabManager, new_tab_id

logger = logging.getLogger("jbrowser.backend.playwright")

_SCREENSHOT_DIR = os.path.join(tempfile.gettempdir(), "jbrowser_screenshots")


class PlaywrightBackend(BrowserBackend):
    """Playwright-backed, multi-tab, session-aware backend."""

    def __init__(self, *, headless: bool | None = None,
                 timeout_ms: int = 30_000,
                 preserve_tabs: bool = False) -> None:
        self.headless = (
            os.environ.get("JARVIS_BROWSER_HEADED", "0") != "0"
            if headless is None else headless
        )
        self.timeout_ms = timeout_ms
        self.preserve_tabs = preserve_tabs
        self.tabs = TabManager()
        self._pw = None
        self._browser = None
        self._context = None
        self._checked = False
        self._pages: dict[str, Any] = {}
        self._session_of: dict[str, str] = {}
        self._active_page: str | None = None
        # defer lazy import of playwright to keep module importable everywhere
        self._playwright_module = None
        self._chromium = None

    # ---------------------------------------------------------- lifecycle
    def _check_playwright(self) -> bool:
        if self._checked:
            return self._browser is not None or self._playwright_module is not None
        self._checked = True
        try:
            import playwright.sync_api as _p
            with _p.sync_playwright() as p:
                path = p.chromium.executable_path
                if path and os.path.exists(path):
                    self._playwright_module = _p.sync_playwright
                    self._chromium = p.chromium
                    return True
                logger.warning("Chromium not installed (run: playwright install chromium)")
        except Exception as exc:
            logger.warning("Playwright unavailable: %s", exc)
        self._playwright_module = None
        return False

    @property
    def available(self) -> bool:
        return self._check_playwright()

    def _ensure_browser(self) -> None:
        if self._context is not None:
            return
        if not self._check_playwright():
            raise RuntimeError(
                "Playwright browser not available. Install: pip install playwright "
                "&& playwright install chromium"
            )
        if self._pw is None:
            self._pw = self._playwright_module().start()
        if self._browser is None:
            launch_kwargs = build_launch_kwargs(preserve_tabs=self.preserve_tabs)
            self._browser = self._chromium.launch(
                headless=self.headless,
                args=launch_kwargs["args"],
            )
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 JBrowser"
            ),
        )

    # ------------------------------------------------------------ sessions
    def create_session(self, session_id: str, *, persistent: bool = False) -> None:
        # Today all tabs share one browser context (single engine process);
        # the session is tracked per-tab via TabContext.session_id. A future
        # engine (WebView2/CEF) can split genuine per-session contexts here.
        self._ensure_browser()

    def close_session(self, session_id: str | None = None) -> None:
        for page in list(self._pages.values()):
            try:
                page.close()
            except Exception:
                pass
        self._pages.clear()
        self._active_page = None

    def status(self) -> dict:
        return {
            "backend": "playwright" if self.available else "web_scraper",
            "available": self.available,
            "launched": self._context is not None,
            "headless": self.headless,
            "tabs": len(self.tabs),
            "active_tab": self._active_page,
            "preserve_tabs": self.preserve_tabs,
        }

    # --------------------------------------------------------------- tabs
    def create_tab(self, session_id: str, url: str = "") -> TabInfo:
        self._ensure_browser()
        page = self._context.new_page()
        page.set_default_timeout(self.timeout_ms)
        tab_id = new_tab_id()
        self._pages[tab_id] = page
        self._session_of[tab_id] = session_id
        info = TabInfo(
            tab_id=tab_id, session_id=session_id,
            url=url, title="", active=False,
        )
        self.tabs.register(TabContext(
            tab_id=tab_id, session_id=session_id,
            url=url, title="", active=False,
        ))
        self.switch_tab(tab_id)
        if url:
            self.navigate(url, tab_id=tab_id)
        return self.tabs.get(tab_id) if False else info

    def close_tab(self, tab_id: str) -> bool:
        page = self._pages.pop(tab_id, None)
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
        if self._active_page == tab_id:
            self._active_page = None
        return self.tabs.remove(tab_id)

    def list_tabs(self, session_id: str | None = None) -> list[TabInfo]:
        contexts = self.tabs.list(session_id)
        out: list[TabInfo] = []
        for c in contexts:
            page = self._pages.get(c.tab_id)
            out.append(TabInfo(
                tab_id=c.tab_id, session_id=c.session_id,
                url=getattr(page, "url", "") if page else c.url,
                title=_title(page) if page else c.title,
                active=c.active,
                created_at=c.created_at,
            ))
        return out

    def switch_tab(self, tab_id: str) -> TabInfo:
        ctx = self.tabs.activate(tab_id)
        if ctx is None:
            raise KeyError(f"tab not found: {tab_id}")
        self._active_page = tab_id
        return TabInfo(
            tab_id=ctx.tab_id, session_id=ctx.session_id,
            url=getattr(self._pages.get(tab_id), "url", ""),
            title=_title(self._pages.get(tab_id)),
            active=True, created_at=ctx.created_at,
        )

    def active_tab(self):
        return self.tabs.active()

    # ---------------------------------------------------------- navigation
    def _page_of(self, tab_id: str | None) -> Any:
        key = tab_id or self._active_page
        page = self._pages.get(key)
        if page is None:
            raise RuntimeError("No active tab; open one with browser.new_tab first.")
        return page

    def _normalize(self, url: str) -> str:
        url = str(url).strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    def navigate(self, url: str, tab_id: str | None = None) -> TabInfo:
        page = self._page_of(tab_id)
        key = tab_id or self._active_page
        page.goto(self._normalize(url), wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=5_000)
        except Exception:
            pass
        ctx = self.tabs.get(key)
        if ctx:
            ctx.url = page.url
            ctx.title = _title(page)
        return TabInfo(tab_id=key, session_id=ctx.session_id if ctx else "",
                       url=page.url, title=_title(page), active=True)

    def go_back(self, tab_id: str | None = None) -> None:
        try:
            self._page_of(tab_id).go_back()
        except Exception as exc:
            logger.debug("go_back failed: %s", exc)

    def go_forward(self, tab_id: str | None = None) -> None:
        try:
            self._page_of(tab_id).go_forward()
        except Exception as exc:
            logger.debug("go_forward failed: %s", exc)

    def reload(self, tab_id: str | None = None) -> None:
        try:
            self._page_of(tab_id).reload()
        except Exception as exc:
            logger.debug("reload failed: %s", exc)

    # -------------------------------------------------------- read/observe
    def get_url(self, tab_id: str | None = None) -> str:
        try:
            return self._page_of(tab_id).url
        except Exception:
            return ""

    def get_title(self, tab_id: str | None = None) -> str:
        try:
            return _title(self._page_of(tab_id))
        except Exception:
            return ""

    def get_page_text(self, tab_id: str | None = None) -> str:
        page = self._page_of(tab_id)
        try:
            return (page.evaluate("() => document.body.innerText") or "")[:20000]
        except Exception:
            return ""

    def get_dom_snapshot(self, tab_id: str | None = None) -> dict:
        page = self._page_of(tab_id)
        ctx = build_page_context(page)
        return {
            "url": ctx.url,
            "title": ctx.title,
            "interactives": ctx.interactives,
            "links": ctx.links,
            "forms": ctx.forms,
            "viewport": ctx.viewport,
        }

    def get_selector_text(self, selector: str | None = None,
                          tab_id: str | None = None) -> str:
        page = self._page_of(tab_id)
        if selector:
            el = page.query_selector(selector)
            return (el.inner_text() if el else "")[:5000]
        return (page.evaluate("() => document.body.innerText") or "")[:5000]

    def screenshot(self, path: str | None = None, tab_id: str | None = None) -> str:
        page = self._page_of(tab_id)
        if path is None:
            os.makedirs(_SCREENSHOT_DIR, exist_ok=True)
            path = os.path.join(_SCREENSHOT_DIR, f"jbrowser_{int(time.time()*1000)}.png")
        page.screenshot(path=path, full_page=False)
        return path

    # ---------------------------------------------------------------- act
    def _el(self, handle: str, page: Any) -> Any:
        idx = int(handle[len("el"):]) if handle.startswith("el") else -1
        try:
            elements = page.query_selector_all(
                "a[href], button, input, select, textarea, [role='button'], "
                "[role='link'], [role='textbox']"
            )
            return elements[idx] if 0 <= idx < len(elements) else None
        except Exception:
            return None

    def click(self, handle: str, tab_id: str | None = None) -> bool:
        page = self._page_of(tab_id)
        el = self._el(handle, page)
        if el is None:
            raise RuntimeError(f"element not found: {handle}")
        el.click()
        return True

    def type_text(self, handle: str, text: str, tab_id: str | None = None) -> bool:
        page = self._page_of(tab_id)
        el = self._el(handle, page)
        if el is None:
            raise RuntimeError(f"element not found: {handle}")
        el.fill(text)
        return True

    def click_selector(self, selector: str, tab_id: str | None = None) -> bool:
        page = self._page_of(tab_id)
        el = page.query_selector(selector)
        if el is None:
            raise RuntimeError(f"element not found: {selector}")
        el.click()
        return True

    def type_selector(self, selector: str, text: str, tab_id: str | None = None) -> bool:
        page = self._page_of(tab_id)
        el = page.query_selector(selector)
        if el is None:
            raise RuntimeError(f"element not found: {selector}")
        el.fill(text)
        return True

    def scroll(self, direction: str, amount: int = 500, tab_id: str | None = None) -> None:
        page = self._page_of(tab_id)
        if direction == "top":
            page.evaluate("() => window.scrollTo(0,0)")
        elif direction == "bottom":
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        elif direction == "up":
            page.evaluate("(a) => window.scrollBy(0, -a)", amount)
        elif direction == "down":
            page.evaluate("(a) => window.scrollBy(0, a)", amount)
        else:
            raise ValueError(f"direction must be up/down/top/bottom, got {direction}")

    def execute_script(self, script: str, tab_id: str | None = None) -> str:
        page = self._page_of(tab_id)
        try:
            result = page.evaluate(script)
        except Exception as exc:
            return f"<error: {exc}>"
        return str(result) if result is not None else ""


def _title(page: Any) -> str:
    if page is None:
        return ""
    try:
        return str(page.title() or "")
    except Exception:
        return ""
