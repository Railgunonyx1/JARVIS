"""Phase 2 — desktop foundation smoke tests.

Verifies the Qt UI constructs, the backend starts in a worker thread,
and messages flow through the Qt signal pipeline.

Tests marked @pytest.mark.e2e require API keys and a live model.
"""

import os
import sys

import pytest

# Ensure repo root is importable
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.join(_REPO_ROOT, "jarvis-desktop")
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)


def test_chat_window_constructs():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.ui.chat_window import ChatWindow
    w = ChatWindow()
    assert w.windowTitle() == "JARVIS"
    assert w.send_btn.text() == "Send"
    assert w.input_field.placeholderText() == "Message JARVIS..."


def test_chat_window_backend_integration():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.ui.chat_window import ChatWindow
    w = ChatWindow()
    w.show()
    w.start_backend()

    loop = QEventLoop()
    QTimer.singleShot(2000, loop.quit)
    loop.exec()

    assert w._coordinator is not None
    assert w._coordinator.backend is not None
    assert w._coordinator.backend.is_running

    w.input_field.setText("Hello")
    w._on_send()

    loop2 = QEventLoop()
    QTimer.singleShot(5000, loop2.quit)
    loop2.exec()

    # Verify a message was added to the chat area (user message at minimum)
    html = w.chat_area.toHtml()
    assert "Hello" in html


@pytest.mark.e2e
def test_chat_window_end_to_end():
    """End-to-end: send a message through the UI and get a response.

    Requires API keys configured in config/.env. Skipped if no keys present.
    """
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.ui.chat_window import ChatWindow
    w = ChatWindow()
    w.show()
    w.start_backend()

    loop = QEventLoop()
    QTimer.singleShot(2000, loop.quit)
    loop.exec()

    assert w._coordinator.backend.is_running

    w.input_field.setText("Say hello in one short sentence.")
    w._on_send()

    # Wait up to 10s for a response
    loop2 = QEventLoop()
    QTimer.singleShot(10000, loop2.quit)
    loop2.exec()

    html = w.chat_area.toHtml()
    # Verify the user message was rendered
    assert "Say hello" in html or "hello" in html.lower()
    # Verify the agent responded (either with text or an error, but not a crash)
    assert "JARVIS:" in html
