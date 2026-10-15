"""BrowserAgent — deprecated compatibility adapter over the J-Browser engine.

This module was the original single-page Playwright wrapper. J-Browser's
``jbrowser.controller.BrowserController`` + ``jbrowser.backend.playwright``
is now the single engine path; every tool routes through it.

This adapter is kept so older callers of ``get_browser_agent()`` (scripts,
notebooks, external integrations) keep working without change. It delegates
to :func:`jbrowser.controller.get_controller` — the same backend as the tools
— so there is still exactly one Playwright process. It is deprecated; prefer
the ``jbrowser`` API directly.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from jbrowser.controller import get_controller

logger = logging.getLogger("external.browser_agent")


class BrowserAgent:
    """Backwards-compatible facade over the J-Browser controller/backend."""

    def __init__(self, *, headless: bool = True, timeout_ms: int = 30_000):  # noqa: ARG002
        self.timeout_ms = timeout_ms

    @property
    def available(self) -> bool:
        return get_controller().status().get("available", False)

    @property
    def backend(self):
        return get_controller().backend

    def _info(self) -> dict[str, Any]:
        return get_controller().status()

    def open(self, url: str) -> dict[str, Any]:
        url = str(url).strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        nav = get_controller().navigate(url)
        page = get_controller().read()
        st = self._info()
        return {
            "url": page.url or url,
            "title": page.title,
            "text": page.text[:5000],
            "links": page.links[:50],
            "fetch_ms": None,
            "backend": st.get("backend", "?"),
            "url_from_nav": nav.get("url", url),
        }

    def screenshot(self, path: str | None = None) -> str:
        if path is None:
            return get_controller().screenshot()
        return get_controller().backend.screenshot(path=path)

    def click(self, selector: str) -> bool:
        return get_controller().click_selector(selector)["clicked"]

    def type_text(self, selector: str, text: str) -> bool:
        return get_controller().type_selector(selector, text)["typed"]

    def extract_text(self, selector: str | None = None) -> str:
        return get_controller().extract_text(selector)

    def current_url(self) -> str:
        return get_controller().current_url()

    def wait(self, ms: int) -> None:
        time.sleep(ms / 1000.0)

    def close(self) -> None:
        try:
            get_controller().backend.close_session()
        except Exception as exc:  # pragma: no cover - engine teardown
            logger.debug("close failed: %s", exc)

    def status(self) -> dict[str, Any]:
        return self._info()

    def __enter__(self) -> BrowserAgent:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


_agent: BrowserAgent | None = None


def get_browser_agent() -> BrowserAgent:
    """Deprecated: reuse one engine process (the same one the tools use)."""
    global _agent
    if _agent is None:
        _agent = BrowserAgent()
    return _agent


def close_browser_agent() -> None:
    """Deprecated: close the adapter's engine (if it is the shared one)."""
    global _agent
    if _agent is not None:
        _agent.close()
        _agent = None


__all__ = ["BrowserAgent", "get_browser_agent", "close_browser_agent"]
