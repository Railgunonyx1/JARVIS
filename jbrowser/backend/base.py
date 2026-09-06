"""J-Browser — backend abstraction.

The agent (and every browser tool) talks only to the :class:`BrowserBackend`
interface, never to a specific engine. This lets J-Browser swap engines
(Playwright/Chromium today, WebView2/CEF later) without touching the agent,
mirroring the Phase A provider-canonicalization discipline.

Dependency direction:
    tools -> jbrowser.controller -> jbrowser.backend.base -> PlaywrightBackend
                 (core/agent never imports an engine)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TabInfo:
    """Lightweight, immutable description of one tab."""

    tab_id: str
    session_id: str
    url: str = ""
    title: str = ""
    active: bool = False
    created_at: float = field(default_factory=lambda: __import__("time").time())


class BrowserBackend(ABC):
    """The engine-neutral contract the browser platform requires.

    All methods are synchronous; the tool executor invokes them via
    ``asyncio.to_thread`` (matching the rest of the tool layer).
    Implementations must be safe to call lazily and never retain native
    resources beyond an explicit lifecycle (daemon-first / 512MB constraint).
    """

    # --- Identity / lifecycle ------------------------------------------
    @abstractmethod
    def create_session(self, session_id: str, *, persistent: bool = False) -> None:
        """Open (or attach to) a browser session by id. Persistent sessions keep
        cookies/storage across runs (logged-in-site operation without passwords)."""

    @abstractmethod
    def close_session(self, session_id: str | None = None) -> None:
        """Close a session and release its resources."""

    @abstractmethod
    def status(self) -> dict:
        """Return backend availability/launch state."""

    # --- Tabs -----------------------------------------------------------
    @abstractmethod
    def create_tab(self, session_id: str, url: str = "") -> TabInfo:
        """Open a new tab; returns its stable identity."""

    @abstractmethod
    def close_tab(self, tab_id: str) -> bool:
        """Close a tab."""

    @abstractmethod
    def list_tabs(self, session_id: str | None = None) -> list[TabInfo]:
        """Return all tabs (optionally filtered by session)."""

    @abstractmethod
    def switch_tab(self, tab_id: str) -> TabInfo:
        """Make a tab the active target for subsequent operations."""

    @abstractmethod
    def active_tab(self) -> TabInfo | None:
        """Return the current active tab."""

    # --- Navigation ------------------------------------------------------
    @abstractmethod
    def navigate(self, url: str, tab_id: str | None = None) -> TabInfo:
        """Navigate the (active or named) tab to a URL."""

    @abstractmethod
    def go_back(self, tab_id: str | None = None) -> None:
        """Navigate back in history."""

    @abstractmethod
    def go_forward(self, tab_id: str | None = None) -> None:
        """Navigate forward in history."""

    @abstractmethod
    def reload(self, tab_id: str | None = None) -> None:
        """Reload the current page."""

    # --- Read / observe ----------------------------------------------------
    @abstractmethod
    def get_url(self, tab_id: str | None = None) -> str:
        """Return the current URL of a tab."""

    @abstractmethod
    def get_title(self, tab_id: str | None = None) -> str:
        """Return the page title of a tab."""

    @abstractmethod
    def get_page_text(self, tab_id: str | None = None) -> str:
        """Return the visible text of the page."""

    @abstractmethod
    def get_dom_snapshot(self, tab_id: str | None = None) -> dict:
        """Return a structured page context (interactive elements, links, forms)."""

    @abstractmethod
    def get_selector_text(self, selector: str | None = None,
                          tab_id: str | None = None) -> str:
        """Return visible text from the whole page or a single CSS selector."""

    @abstractmethod
    def screenshot(self, path: str | None = None, tab_id: str | None = None) -> str:
        """Capture a screenshot; returns the file path."""

    # --- Act (structured, auditable actions) -----------------------------
    @abstractmethod
    def click(self, handle: str, tab_id: str | None = None) -> bool:
        """Click an interactive element by its stable handle."""

    @abstractmethod
    def type_text(self, handle: str, text: str, tab_id: str | None = None) -> bool:
        """Type text into an input identified by its handle."""

    @abstractmethod
    def click_selector(self, selector: str, tab_id: str | None = None) -> bool:
        """Click the first element matching a CSS selector (selector-based API)."""

    @abstractmethod
    def type_selector(self, selector: str, text: str, tab_id: str | None = None) -> bool:
        """Fill the first element matching a CSS selector (selector-based API)."""

    @abstractmethod
    def scroll(self, direction: str, amount: int = 500, tab_id: str | None = None) -> None:
        """Scroll a tab ('up' | 'down' | 'top' | 'bottom')."""

    @abstractmethod
    def execute_script(self, script: str, tab_id: str | None = None) -> str:
        """Run JavaScript in the page. High-risk; gated by permissions."""
