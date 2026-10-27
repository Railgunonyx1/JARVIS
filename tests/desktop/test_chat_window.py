"""Chat window tests — hermetic, no GUI display needed."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.join(_REPO_ROOT, "dynamic-island")
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_chat_window_is_deprecated_stub(qapp):
    """ChatWindow is a deprecated stub; real chat lives in the island overlay."""
    from app.ui.chat_window import ChatWindow

    w = ChatWindow()
    assert w.windowTitle().startswith("JARVIS Chat")
    w.close()


def test_chat_window_has_no_mic_button(qapp):
    """ChatWindow should not expose a mic button; the island handles voice."""
    from app.ui.chat_window import ChatWindow

    w = ChatWindow()
    assert not hasattr(w, "mic_btn")
    w.close()
