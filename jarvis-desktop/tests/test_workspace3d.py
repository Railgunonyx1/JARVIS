"""Phase 5 — 3D workspace tests (hermetic, offscreen)."""

import sys
import os
import time

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)


def test_workspace3d_constructs():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.workspace3d.workspace3d import Workspace3D
    ws = Workspace3D()
    assert not ws.is_loaded
    assert not ws.is_visible


def _qquickwidget_available():
    try:
        from PySide6.QtQuickWidgets import QQuickWidget  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _qquickwidget_available(), reason="Qt Quick system libs unavailable")
def test_workspace3d_loads_qml():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.workspace3d.workspace3d import Workspace3D
    ws = Workspace3D()
    result = ws.load()
    assert result is True
    assert ws.is_loaded
    ws.shutdown()


def test_workspace3d_panel_text():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.workspace3d.workspace3d import Workspace3D
    ws = Workspace3D()
    ws.set_panel_text("chat", "Test message")
    assert "Test message" in ws.get_panel_text("chat")
    ws.shutdown()


@pytest.mark.skipif(not _qquickwidget_available(), reason="Qt Quick system libs unavailable")
def test_workspace3d_show_hide():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.workspace3d.workspace3d import Workspace3D
    ws = Workspace3D()
    ws.load()
    ws.show()
    assert ws.is_visible
    ws.hide()
    assert not ws.is_visible
    ws.shutdown()


def test_workspace3d_system_stats():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.workspace3d.workspace3d import Workspace3D
    ws = Workspace3D()
    ws.update_system_stats(45.0, 60.0, 30.0)
    text = ws.get_panel_text("system")
    assert "45%" in text
    assert "60%" in text
    ws.shutdown()


def test_workspace3d_voice_status():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.workspace3d.workspace3d import Workspace3D
    ws = Workspace3D()
    ws.update_voice_status("Listening")
    assert "Listening" in ws.get_panel_text("voice")
    ws.shutdown()


def test_workspace3d_tasks():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.workspace3d.workspace3d import Workspace3D
    ws = Workspace3D()
    ws.update_tasks(["Task 1", "Task 2"])
    text = ws.get_panel_text("tasks")
    assert "Task 1" in text
    assert "Task 2" in text
    ws.shutdown()


def test_workspace3d_chat():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.workspace3d.workspace3d import Workspace3D
    ws = Workspace3D()
    ws.update_chat(["Hello", "How are you?"])
    text = ws.get_panel_text("chat")
    assert "Hello" in text
    ws.shutdown()
