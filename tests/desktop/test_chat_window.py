"""Chat window tests — hermetic, no GUI display needed."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.join(_REPO_ROOT, "dynamic-island")
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)


def test_chat_window_constructs():
    """ChatWindow should construct without crashing."""
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.ui.chat_window import ChatWindow
    w = ChatWindow()
    assert w is not None
    w.close()


def test_send_does_not_append_message_directly():
    """Regression: _on_send must not append the user message itself.

    The coordinator's chat_message signal owns display. A direct append in
    _on_send caused duplicate user messages in the chat area.
    """
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from unittest.mock import MagicMock

    from app.ui.chat_window import ChatWindow

    w = ChatWindow()
    w._coordinator = MagicMock()
    w.input_field.setText("hello jarvis")
    w._on_send()

    assert w.input_field.text() == ""
    w._coordinator.send_message.assert_called_once_with("hello jarvis")
    chat_html = w.chat_area.toHtml()
    assert "hello jarvis" not in chat_html
    w.close()


def test_settings_dialog_does_not_crash():
    """Settings dialog should open without AttributeError on _gesture_active."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.ui.chat_window import ChatWindow
    w = ChatWindow()

    def _close_dialog():
        d = QApplication.activeModalWidget()
        if d is not None:
            d.reject()

    QTimer.singleShot(100, _close_dialog)
    w._on_settings()
    w.close()


def test_settings_with_coordinator():
    """Settings dialog should work when coordinator is attached."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.integration.coordinator import AppCoordinator
    from app.ui.chat_window import ChatWindow

    w = ChatWindow()
    coord = AppCoordinator(mode="agent")
    w._coordinator = coord

    def _close_dialog():
        d = QApplication.activeModalWidget()
        if d is not None:
            d.reject()

    QTimer.singleShot(100, _close_dialog)
    w._on_settings()
    w.close()
    coord.shutdown()


def test_mic_btn_enabled_after_start():
    """Mic button should be enabled after start_backend."""
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.ui.chat_window import ChatWindow
    w = ChatWindow()
    assert w.mic_btn.isEnabled() is False
    w.start_backend()
    assert w.mic_btn.isEnabled() is True
    w.close()
