"""J-Browser — JARVIS's optimized agent browser platform.

A Chromium-based browser capability that carries JARVIS's full agent stack:
tools route through ToolExecutionService, page state is typed/structured,
tab & session identity are first-class, and every action is observable via
the EventBus. The engine is swappable behind :class:`BrowserBackend`.
"""

from jbrowser.backend.base import BrowserBackend, TabInfo
from jbrowser.controller import BrowserController, get_controller, reset_controller
from jbrowser.page_context import PageContext, build_page_context
from jbrowser.permissions import Risk, requires_approval, risk_for_tool
from jbrowser.sessions import BrowserSession, SessionManager, new_session_id
from jbrowser.tabs import TabContext, TabManager, new_tab_id

__all__ = [
    "BrowserBackend",
    "TabInfo",
    "BrowserController",
    "get_controller",
    "reset_controller",
    "TabContext",
    "TabManager",
    "new_tab_id",
    "BrowserSession",
    "SessionManager",
    "new_session_id",
    "PageContext",
    "build_page_context",
    "Risk",
    "risk_for_tool",
    "requires_approval",
]
