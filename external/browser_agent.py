"""BrowserAgent — Playwright-backed browser automation for JARVIS MK-X.

Pattern extracted from browser-use/browser-use (the standard AI browser-agent
library): keep the automation layer thin and let the agent drive it. Per the
research principle we do NOT install browser-use itself — Playwright is the
backend, JARVIS provides the agent loop.

Design honors the 512 MB daemon-first constraint:
  - The browser is launched lazily on first use and closed on ``close()``
    / process exit — never resident.
  - When Playwright (or its browser binary) is unavailable, operations fall
    back to the HTTP-based WebScraper so the tool never hard-fails.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from typing import Any

logger = logging.getLogger("external.browser_agent")

_HEADLESS = os.environ.get("JARVIS_BROWSER_HEADLESS", "1") != "0"
_TIMEOUT_MS = 30_000
_SCREENSHOT_DIR = os.path.join(tempfile.gettempdir(), "jarvis_screenshots")


class BrowserAgent:
    """Thin Playwright wrapper with graceful degradation to WebScraper."""

    def __init__(self, *, headless: bool = _HEADLESS, timeout_ms: int = _TIMEOUT_MS):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._page = None
        self._context = None
        self._checked = False
        self._backend = "playwright"

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def _check_playwright(self) -> bool:
        """True when Playwright is importable and its browser exists on disk."""
        if self._checked:
            return self._browser is not None or self._playwright is not None
        self._checked = True
        try:
            import playwright  # noqa: F401
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                path = p.chromium.executable_path
                if path and os.path.exists(path):
                    self._playwright_module = sync_playwright
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

    def _ensure_browser(self):
        """Launch chromium if not already running (lazy, never resident)."""
        if self._page is not None:
            return
        if not self._check_playwright():
            raise RuntimeError(
                "Playwright browser not available. Install with: "
                "pip install playwright && playwright install chromium"
            )
        if self._playwright is None:
            self._playwright = self._playwright_module().start()
        if self._browser is None:
            self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 JARVIS"
            ),
        )
        self._page = self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def open(self, url: str) -> dict[str, Any]:
        """Navigate to a URL and return title/text/url. Falls back to scraping."""
        url = str(url).strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        if not self.available:
            return self._fallback_open(url)

        start = time.time()
        self._ensure_browser()
        page = self._page
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=5_000)
        title = page.title()
        text = page.evaluate("() => document.body.innerText") or ""
        links = page.eval_on_selector_all(
            "a[href^='http']", "els => els.map(e => e.href)"
        )
        return {
            "url": page.url,
            "title": title,
            "text": text[:5000],
            "links": links[:50],
            "fetch_ms": round((time.time() - start) * 1000, 1),
            "backend": "playwright",
        }

    def screenshot(self, path: str | None = None) -> str:
        """Capture a screenshot. Returns the file path (saved to temp by default)."""
        if not self.available:
            raise RuntimeError("Screenshots require Playwright (browser not available)")
        self._ensure_browser()
        if path is None:
            os.makedirs(_SCREENSHOT_DIR, exist_ok=True)
            path = os.path.join(
                _SCREENSHOT_DIR, f"jarvis_{int(time.time() * 1000)}.png"
            )
        self._page.screenshot(path=path, full_page=False)
        return path

    def click(self, selector: str) -> bool:
        """Click the first element matching a CSS selector."""
        if not self.available:
            raise RuntimeError("Clicking requires Playwright")
        self._ensure_browser()
        self._page.click(selector)
        return True

    def type_text(self, selector: str, text: str) -> bool:
        """Type into the first element matching a CSS selector."""
        if not self.available:
            raise RuntimeError("Typing requires Playwright")
        self._ensure_browser()
        self._page.fill(selector, text)
        return True

    def extract_text(self, selector: str | None = None) -> str:
        """Return visible text from the whole page or a single selector."""
        if not self.available:
            raise RuntimeError("Extraction requires Playwright")
        self._ensure_browser()
        if selector:
            el = self._page.query_selector(selector)
            return (el.inner_text() if el else "")[:5000]
        return (self._page.evaluate("() => document.body.innerText") or "")[:5000]

    def current_url(self) -> str:
        if self._page is None:
            return ""
        return self._page.url

    def wait(self, ms: int) -> None:
        if self._page is not None:
            self._page.wait_for_timeout(ms)

    # ------------------------------------------------------------------
    # Fallback (no Playwright)
    # ------------------------------------------------------------------

    def _fallback_open(self, url: str) -> dict[str, Any]:
        from external.web_scraper import get_web_scraper

        page = get_web_scraper().scrape(url)
        self._backend = "web_scraper"
        return {
            "url": page.url,
            "title": page.title,
            "text": page.text[:5000],
            "links": page.links[:50],
            "fetch_ms": round(page.fetch_ms, 1),
            "status_code": page.status_code,
            "backend": "web_scraper",
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the browser and release resources."""
        for closer in (self._context, self._browser, self._playwright):
            try:
                if closer is not None:
                    closer.close()
            except Exception:
                pass
        self._context = None
        self._browser = None
        self._playwright = None
        self._page = None
        logger.info("Browser closed")

    def status(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "backend": "playwright" if self.available else "web_scraper",
            "launched": self._page is not None,
            "url": self.current_url(),
            "headless": self.headless,
        }

    def __enter__(self) -> BrowserAgent:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


_agent: BrowserAgent | None = None


def get_browser_agent() -> BrowserAgent:
    """Module-level singleton so a session reuses one browser process."""
    global _agent
    if _agent is None:
        _agent = BrowserAgent()
    return _agent


def close_browser_agent() -> None:
    """Close and drop the singleton (call on shutdown)."""
    global _agent
    if _agent is not None:
        _agent.close()
        _agent = None


__all__ = ["BrowserAgent", "get_browser_agent", "close_browser_agent"]
