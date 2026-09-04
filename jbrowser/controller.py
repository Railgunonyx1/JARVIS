"""J-Browser — controller facade.

A thin, high-level facade the tool handlers call. It owns the backend and the
session registry, resolves "active tab vs named tab", and emits browser
events on the EventBus so the rest of JARVIS observes browser activity.

Tools in ``jbrowser.tools`` AND the legacy ``tools/browser.py`` wrappers route
here so there is exactly one path from a tool call to the engine.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from jbrowser.backend.base import BrowserBackend
from jbrowser.backend.playwright import PlaywrightBackend
from jbrowser.events import (
    ACTION_COMPLETED,
    AGENT_ACTION,
    NAVIGATION_COMPLETED,
    NAVIGATION_STARTED,
    PAGE_LOADED,
    TAB_ACTIVATED,
    TAB_CLOSED,
    TAB_CREATED,
    emit_browser_event,
)
from jbrowser.page_context import PageContext
from jbrowser.sessions import SessionManager, new_session_id


class BrowserController:
    """Session-aware facade over a :class:`BrowserBackend`."""

    def __init__(self, backend: BrowserBackend | None = None,
                 profile_root: Path | None = None) -> None:
        self.backend = backend or PlaywrightBackend(profile_root=profile_root)
        self.sessions = SessionManager()
        self.profile_root = profile_root or Path(".")
        # RLock so public methods that call each other can re-enter while still
        # serializing concurrent tool-thread access to the (non-thread-safe)
        # Playwright engine.
        self._lock = threading.RLock()
        self._default_session: str = ""

    # ------------------------------------------------------------ sessions
    def ensure_session(self, session_id: str = "", *, persistent: bool = False) -> str:
        with self._lock:
            sid = session_id or self._default_session or new_session_id()
            if not self._default_session:
                self._default_session = sid
            session = self.sessions.get_or_create(
                sid, persistent=persistent, profile_root=self.profile_root)
            self.backend.create_session(sid, persistent=session.persistent)
            return sid

    def close_session(self, session_id: str = "") -> None:
        with self._lock:
            sid = session_id or self._default_session
            self.backend.close_session(sid or None)
            if self.sessions.get(sid) is not None:
                self.sessions.remove(sid)
            if self._default_session == sid:
                self._default_session = ""

    def shutdown(self) -> None:
        with self._lock:
            if hasattr(self.backend, "shutdown"):
                self.backend.shutdown()
            self.sessions = SessionManager()

    def session_info(self, session_id: str = "") -> dict:
        sid = session_id or self._default_session
        session = self.sessions.get(sid)
        return session.describe() if session else {}

    # ---------------------------------------------------------------- tabs
    def new_tab(self, url: str = "", session_id: str = "") -> dict:
        with self._lock:
            sid = self.ensure_session(session_id)
            info = self.backend.create_tab(sid, url)
            emit_browser_event(TAB_CREATED, {"tab_id": info.tab_id, "url": info.url},
                               session_id=sid)
            return {
                "tab_id": info.tab_id, "session_id": sid,
                "url": info.url, "title": info.title, "active": info.active,
            }

    def close_tab(self, tab_id: str) -> dict:
        with self._lock:
            sid = self._session_of(tab_id)
            ok = self.backend.close_tab(tab_id)
            if ok:
                emit_browser_event(TAB_CLOSED, {"tab_id": tab_id}, session_id=sid)
            return {"closed": ok, "tab_id": tab_id}

    def list_tabs(self) -> list[dict]:
        with self._lock:
            return [vars(t) if hasattr(t, "__dict__") else {
                "tab_id": t.tab_id, "session_id": t.session_id, "url": t.url,
                "title": t.title, "active": t.active} for t in self.backend.list_tabs()]

    def switch_tab(self, tab_id: str) -> dict:
        with self._lock:
            info = self.backend.switch_tab(tab_id)
            if hasattr(info, "tab_id"):
                emit_browser_event(TAB_ACTIVATED, {"tab_id": info.tab_id},
                                   session_id=self._session_of(info.tab_id))
                return {"tab_id": info.tab_id, "url": info.url, "title": info.title}
            return {"tab_id": tab_id}

    def _session_of(self, tab_id: str) -> str:
        for tab in self.backend.list_tabs():
            if getattr(tab, "tab_id", None) == tab_id:
                return getattr(tab, "session_id", "")
        return self._default_session

    # ---------------------------------------------------------- navigation
    def navigate(self, url: str, tab_id: str | None = None) -> dict:
        with self._lock:
            sid = self._default_session
            if tab_id is None:
                ensure = self.ensure_session()
                sid = ensure
                # ensure an active tab exists
                if not self.backend.active_tab():
                    self.new_tab(url="", session_id=sid)
            emit_browser_event(NAVIGATION_STARTED, {"url": url}, session_id=sid)
            try:
                info = self.backend.navigate(url, tab_id=tab_id)
            except Exception:
                emit_browser_event(NAVIGATION_COMPLETED,
                                   {"tab_id": "", "url": url, "error": True},
                                   session_id=sid)
                raise
            info_tab = getattr(info, "tab_id", "")
            info_url = getattr(info, "url", url)
            emit_browser_event(NAVIGATION_COMPLETED,
                               {"tab_id": info_tab, "url": info_url}, session_id=sid)
            emit_browser_event(PAGE_LOADED,
                               {"tab_id": info_tab, "url": info_url}, session_id=sid)
            return {"url": info_url, "title": getattr(info, "title", "")}

    def go_back(self, tab_id: str | None = None) -> None:
        with self._lock:
            self.ensure_session()
            self.backend.go_back(tab_id)

    def go_forward(self, tab_id: str | None = None) -> None:
        with self._lock:
            self.ensure_session()
            self.backend.go_forward(tab_id)

    def reload(self, tab_id: str | None = None) -> None:
        with self._lock:
            self.ensure_session()
            self.backend.reload(tab_id)

    def back(self, tab_id: str | None = None) -> None:
        self.go_back(tab_id)

    def forward(self, tab_id: str | None = None) -> None:
        self.go_forward(tab_id)

    def refresh(self, tab_id: str | None = None) -> None:
        self.reload(tab_id)

    # --------------------------------------------------------- read/observe
    def read(self, tab_id: str | None = None) -> PageContext:
        with self._lock:
            self.ensure_session()
            dom = self.backend.get_dom_snapshot(tab_id)
            text = self.backend.get_page_text(tab_id)
            url = self.backend.get_url(tab_id)
            title = self.backend.get_title(tab_id)
            return PageContext(
                url=url, title=title, text=text,
                interactives=dom.get("interactives", []),
                links=dom.get("links", []),
                forms=dom.get("forms", []),
                viewport=dom.get("viewport", {}),
            )

    def extract_text(self, selector: str | None = None,
                     tab_id: str | None = None) -> str:
        with self._lock:
            self.ensure_session()
            return self.backend.get_selector_text(selector, tab_id=tab_id)

    def current_url(self, tab_id: str | None = None) -> str:
        with self._lock:
            try:
                return self.backend.get_url(tab_id)
            except Exception:
                return ""

    def screenshot(self, tab_id: str | None = None) -> str:
        with self._lock:
            self.ensure_session()
            return self.backend.screenshot(tab_id=tab_id)

    def status(self) -> dict:
        with self._lock:
            base = self.backend.status()
            base["sessions"] = [s.describe() for s in self.sessions.list()]
            return base

    # ----------------------------------------------------------------- act
    def click(self, handle: str, tab_id: str | None = None) -> dict:
        with self._lock:
            self.ensure_session()
            self.emit_agent_action("click", {"handle": handle})
            ok = self.backend.click(handle, tab_id=tab_id)
            self.emit_action_completed("click", {"handle": handle})
            return {"clicked": ok, "handle": handle}

    def type_text(self, handle: str, text: str, tab_id: str | None = None) -> dict:
        with self._lock:
            self.ensure_session()
            self.emit_agent_action("type", {"handle": handle, "chars": len(text)})
            ok = self.backend.type_text(handle, text, tab_id=tab_id)
            self.emit_action_completed("type", {"handle": handle})
            return {"typed": ok, "handle": handle, "chars": len(text)}

    def click_selector(self, selector: str, tab_id: str | None = None) -> dict:
        with self._lock:
            self.ensure_session()
            self.emit_agent_action("click", {"selector": selector})
            ok = self.backend.click_selector(selector, tab_id=tab_id)
            self.emit_action_completed("click", {"selector": selector})
            return {"clicked": ok, "selector": selector}

    def type_selector(self, selector: str, text: str, tab_id: str | None = None) -> dict:
        with self._lock:
            self.ensure_session()
            self.emit_agent_action("type", {"selector": selector, "chars": len(text)})
            ok = self.backend.type_selector(selector, text, tab_id=tab_id)
            self.emit_action_completed("type", {"selector": selector})
            return {"typed": ok, "selector": selector, "chars": len(text)}

    def scroll(self, direction: str, amount: int = 500, tab_id: str | None = None) -> None:
        with self._lock:
            self.ensure_session()
            self.backend.scroll(direction, amount, tab_id=tab_id)

    def execute_script(self, script: str, tab_id: str | None = None) -> str:
        self.ensure_session()
        self.emit_agent_action("execute_script", {})
        return self.backend.execute_script(script, tab_id=tab_id)

    def emit_agent_action(self, name: str, payload: dict[str, Any]) -> None:
        emit_browser_event(AGENT_ACTION, {"action": name, **payload},
                           session_id=self._default_session)

    def emit_action_completed(self, name: str, payload: dict[str, Any]) -> None:
        emit_browser_event(ACTION_COMPLETED, {"action": name, **payload},
                           session_id=self._default_session)


_controller: BrowserController | None = None
_controller_lock = threading.Lock()


def get_controller() -> BrowserController:
    """Module-level singleton shared by all browser tools (one engine process)."""
    global _controller
    if _controller is None:
        with _controller_lock:
            if _controller is None:
                _controller = BrowserController()
    return _controller


def reset_controller() -> None:
    """Drop the singleton (for tests / shutdown)."""
    global _controller
    _controller = None
