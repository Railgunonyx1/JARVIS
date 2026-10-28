"""Tests for the JARVIS Desktop Dynamic Island overlay."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.join(_REPO_ROOT, "dynamic-island")
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)

os.environ.setdefault("JARVIS_DESKTOP_HOME", "/tmp/jarvis-island-test")

from app.ui.overlay_window import IslandState  # noqa: E402
from PySide6.QtCore import QRect

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_island_constructs_idle(qapp):
    from app.ui.overlay_window import IslandWindow
    island = IslandWindow()
    island.show()
    qapp.processEvents()
    assert island._state is IslandState.IDLE
    assert island._card.width() == 186
    island.close()


def test_island_expanded_state(qapp):
    from app.ui.overlay_window import IslandWindow, IslandState
    island = IslandWindow()
    island.show()
    qapp.processEvents()
    assert island._state is IslandState.IDLE
    island.expand()
    qapp.processEvents()
    assert island._state is IslandState.EXPANDED
    assert island._card.height() > 100
    island.close()
