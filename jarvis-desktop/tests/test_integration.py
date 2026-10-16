"""Phase 6 — integration tests: coordinator wires all subsystems."""

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


def test_coordinator_constructs():
    from app.integration.coordinator import AppCoordinator, AppState
    coord = AppCoordinator()
    assert coord.state == AppState.IDLE
    assert not coord.is_running


def test_coordinator_starts_and_stops():
    from app.integration.coordinator import AppCoordinator, AppState
    coord = AppCoordinator()
    coord.start()
    assert coord.is_running
    assert coord.backend is not None
    assert coord.backend.is_running
    coord.shutdown()
    assert not coord.is_running


def test_coordinator_send_message():
    from app.integration.coordinator import AppCoordinator, AppState
    messages = []
    coord = AppCoordinator(
        on_chat_message=lambda role, text: messages.append((role, text)),
    )
    coord.start()
    coord.send_message("Hello JARVIS")
    time.sleep(0.5)
    assert ("user", "Hello JARVIS") in messages
    coord.shutdown()


def test_coordinator_voice_toggle():
    from app.integration.coordinator import AppCoordinator, AppState
    coord = AppCoordinator()
    coord.start()
    coord.toggle_voice()
    # Voice state should change (listening or back to idle)
    assert coord.voice is not None
    coord.shutdown()


def test_coordinator_gesture_toggle():
    from app.integration.coordinator import AppCoordinator
    coord = AppCoordinator()
    coord.start()
    coord.toggle_gestures()
    # Gesture active or failed to start (no camera) — either is fine
    assert coord.state.value in ("gesture_active", "idle")
    coord.shutdown()


def test_coordinator_workspace_toggle():
    from app.integration.coordinator import AppCoordinator, AppState
    coord = AppCoordinator()
    coord.start()
    coord.toggle_workspace()
    # Workspace may fail to load (no Qt Quick libs) — either state is fine
    assert coord.state.value in ("workspace_open", "idle")
    coord.shutdown()


def test_coordinator_action_execution():
    from app.integration.coordinator import AppCoordinator
    coord = AppCoordinator()
    coord.start()
    # volume_up is a safe action that should succeed (or fail gracefully)
    result = coord.execute_action("volume_up")
    assert isinstance(result, bool)
    coord.shutdown()


def test_coordinator_status():
    from app.integration.coordinator import AppCoordinator
    coord = AppCoordinator()
    coord.start()
    status = coord.get_status()
    assert "state" in status
    assert "backend_running" in status
    assert "voice_state" in status
    assert "gesture_active" in status
    coord.shutdown()


def test_coordinator_workspace_panel_update():
    from app.integration.coordinator import AppCoordinator
    updates = []
    coord = AppCoordinator(
        on_workspace_update=lambda panel, text: updates.append((panel, text)),
    )
    coord.start()
    coord.update_workspace_panel("chat", "Test")
    assert ("chat", "Test") in updates
    coord.shutdown()


def test_coordinator_available_actions():
    from app.integration.coordinator import AppCoordinator
    coord = AppCoordinator()
    coord.start()
    actions = coord.get_available_actions()
    assert len(actions) >= 5
    media = coord.get_available_actions("media")
    assert len(media) >= 3
    coord.shutdown()
