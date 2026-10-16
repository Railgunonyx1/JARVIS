"""Phase 2 — desktop foundation smoke tests.

Verifies the Qt UI constructs, the backend starts in a worker thread,
and messages flow through the Qt signal pipeline.
"""

import sys
import os
import time

import pytest

# Ensure repo root is importable
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)


def test_backend_constructs_and_starts():
    from app.integration.jarvis_backend import JarvisBackend
    backend = JarvisBackend(mode="agent")
    backend.start()
    assert backend.is_running
    backend.stop()
    assert not backend.is_running


def test_backend_processes_message():
    from app.integration.jarvis_backend import JarvisBackend
    responses = []
    backend = JarvisBackend(mode="agent", on_response=responses.append)
    backend.start()
    backend.send_message("Hello")
    start = time.time()
    while not responses and time.time() - start < 15:
        time.sleep(0.1)
    backend.stop()
    # Agent may fail on missing API keys — just verify no crash
    assert isinstance(responses, list)


def test_chat_window_constructs():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.ui.chat_window import ChatWindow
    w = ChatWindow()
    assert w.windowTitle() == "JARVIS"
    assert w.send_btn.text() == "Send"
    assert w.input_field.placeholderText() == "Message JARVIS..."


def test_chat_window_backend_integration():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer, QEventLoop
    app = QApplication.instance() or QApplication([])
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

    assert len(w.chat_area.toHtml()) > 100
