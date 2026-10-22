"""Tests for the JARVIS Desktop Dynamic Island overlay."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.join(_REPO_ROOT, "jarvis-desktop")
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)

os.environ.setdefault("JARVIS_DESKTOP_HOME", "/tmp/jarvis-island-test")

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_island_constructs_idle(qapp):
    from app.ui.overlay_window import IslandState, IslandWindow
    island = IslandWindow()
    assert island._state is IslandState.IDLE
    assert island.width() == 180
    island.close()


def test_island_expand_collapse(qapp):
    from app.ui.overlay_window import IslandState, IslandWindow
    island = IslandWindow()
    island.expand()
    assert island._state is IslandState.EXPANDED
    island.collapse()
    assert island._state is IslandState.IDLE
    island.close()


def test_island_status_update(qapp):
    from app.ui.overlay_window import IslandWindow
    island = IslandWindow()
    island.set_status("Listening", "#FF3B30")
    assert island._status.text() == "Listening"
    island.close()


def test_island_centered_top(qapp):
    from app.ui.overlay_window import IslandWindow
    island = IslandWindow()
    screen = qapp.primaryScreen()
    geo = screen.availableGeometry()
    expected_x = geo.left() + (geo.width() - island.width()) // 2
    assert abs(island.x() - expected_x) <= 1
    assert island.y() == geo.top() + 8
    island.close()


def test_autostart_enable_disable(tmp_path, monkeypatch):
    from app import autostart
    monkeypatch.setattr(autostart, "AUTOSTART_DIR", tmp_path / "autostart")
    monkeypatch.setattr(autostart, "ENTRY_FILE", tmp_path / "autostart" / "jarvis-desktop.desktop")
    assert autostart.is_enabled() is False
    assert autostart.enable("echo hi") is True
    assert autostart.is_enabled() is True
    assert autostart.disable() is True
    assert autostart.is_enabled() is False
