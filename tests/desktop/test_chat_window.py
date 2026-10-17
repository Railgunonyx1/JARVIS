"""Chat window tests — hermetic, no GUI display needed."""

import os
import sys

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.join(_REPO_ROOT, "jarvis-desktop")
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)


def test_chat_window_constructs():
    """ChatWindow should construct without crashing."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.ui.chat_window import ChatWindow
    w = ChatWindow()
    assert w is not None
    w.close()


def test_settings_dialog_does_not_crash():
    """Settings dialog should open without AttributeError on _gesture_active."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.ui.chat_window import ChatWindow
    w = ChatWindow()
    # This used to crash with AttributeError on _gesture_active
    w._on_settings()
    w.close()


def test_settings_with_coordinator():
    """Settings dialog should work when coordinator is attached."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.ui.chat_window import ChatWindow
    from app.integration.coordinator import AppCoordinator

    w = ChatWindow()
    coord = AppCoordinator(mode="agent")
    w._coordinator = coord
    # This should not crash
    w._on_settings()
    w.close()
    coord.shutdown()


def test_mic_btn_enabled_after_start():
    """Mic button should be enabled after start_backend."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.ui.chat_window import ChatWindow
    w = ChatWindow()
    assert w.mic_btn.isEnabled() is False
    w.start_backend()
    assert w.mic_btn.isEnabled() is True
    w.close()
