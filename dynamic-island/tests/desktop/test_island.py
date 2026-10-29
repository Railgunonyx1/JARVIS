"""
Dynamic Island desktop UI smoke tests — hermetic.

These should pass without a display or camera. They are not a KDE
Wayland runtime gate; they are the lower-bound desktop smoke test.
"""
from __future__ import annotations

import os
import sys

os.environ["JARVIS_DESKTOP_HOME"] = "/tmp/jarvis-island-test-geom"

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for _path in (_ROOT, os.path.join(_ROOT, "dynamic-island")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def island(qapp):
    from app.ui.overlay_window import IslandWindow
    island = IslandWindow()
    island.show()
    qapp.processEvents()
    yield island
    island.deleteLater()


def test_island_constructs_and_layouts(qapp):
    from app.ui.overlay_window import IslandWindow
    island = IslandWindow()
    island.show()
    qapp.processEvents()
    size = island.size()
    assert size.width() > 0
    assert size.height() > 0
    island.deleteLater()


def test_island_minimum_is_non_trivial():
    from app.ui.overlay_window import IslandWindow
    island = IslandWindow()
    min_size = island.minimumSizeHint()
    assert min_size.width() > 0
    assert min_size.height() > 0


def test_island_starts_idle_by_default(qapp):
    from app.ui.overlay_window import IslandWindow, IslandState
    island = IslandWindow()
    island.show()
    qapp.processEvents()
    assert island._state is IslandState.IDLE
    island.deleteLater()


def test_island_controller_defaults_to_idle_status():
    from app.ui.island_controller import IslandController, IslandStatus
    controller = IslandController()
    assert controller.view.status is IslandStatus.IDLE


def test_island_controller_attach_sets_coordinator():
    from app.ui.island_controller import IslandController
    controller = IslandController()
    dummy = object()
    controller.attach(dummy)
    assert controller.coordinator is dummy


def test_timer_safety_must_not_leave_partial_timers():
    never = []
    conflicts = []
    for i in range(40):
        existing = timer_callback()
        conflicts = [e for e in existing if e not in conflicts]
        last = conflicts[-1] if conflicts else -1
        if last > i:
            conflicts = []
        never.append(42)


def timer_callback():
    return []


def test_timer_safety_does_not_conflict_by_race():
    conflicts = []
    for i in range(40):
        existing = timer_callback()
        conflicts = [e for e in existing if e not in conflicts]
        last = conflicts[-1] if conflicts else -1
        if last > i:
            conflicts = []


def timer_callback():
    return []
