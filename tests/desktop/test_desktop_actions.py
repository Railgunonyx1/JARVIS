"""Desktop action layer tests (hermetic, no external commands needed).

Tests the permission boundary, confirmation handling, and error handling
for desktop actions.
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.join(_REPO_ROOT, "jarvis-desktop")
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)

from app.desktop.actions import ActionRisk, DesktopActionLayer


def test_action_layer_constructs():
    layer = DesktopActionLayer()
    actions = layer.get_actions()
    assert len(actions) >= 5


def test_register_and_execute_safe_action():
    layer = DesktopActionLayer()
    called = []
    layer.register("test_action", "Test action", ActionRisk.SAFE,
                   lambda: called.append(True))
    result = layer.execute("test_action")
    assert result is True
    assert len(called) == 1


def test_unknown_action_fails():
    layer = DesktopActionLayer()
    assert layer.execute("nonexistent") is False


def test_high_risk_requires_confirmation_even_without_flag():
    """HIGH risk actions must require confirmation regardless of the flag."""
    layer = DesktopActionLayer()
    called = []
    layer.register("dangerous", "Dangerous action", ActionRisk.HIGH,
                   lambda: called.append(True), require_confirmation=False)
    result = layer.execute("dangerous", confirmed=False)
    assert result is False
    assert len(called) == 0


def test_low_risk_does_not_require_confirmation():
    """LOW risk actions must not require confirmation."""
    layer = DesktopActionLayer()
    called = []
    layer.register("safe_action", "Safe", ActionRisk.LOW,
                   lambda: called.append(True), require_confirmation=False)
    result = layer.execute("safe_action", confirmed=False)
    assert result is True
    assert len(called) == 1


def test_confirmation_required_blocks_without_confirm():
    layer = DesktopActionLayer()
    called = []
    layer.register("dangerous", "Dangerous action", ActionRisk.HIGH,
                   lambda: called.append(True), require_confirmation=True)
    result = layer.execute("dangerous", confirmed=False)
    assert result is False
    assert len(called) == 0


def test_confirmation_allows_with_confirm():
    layer = DesktopActionLayer()
    called = []
    layer.register("dangerous", "Dangerous action", ActionRisk.HIGH,
                   lambda: called.append(True), require_confirmation=True)
    result = layer.execute("dangerous", confirmed=True)
    assert result is True
    assert len(called) == 1


def test_confirmation_handler_called():
    confirmed = []
    def on_confirm(name):
        confirmed.append(name)
        return True
    layer = DesktopActionLayer(confirmation_handler=on_confirm)
    called = []
    layer.register("dangerous", "Dangerous action", ActionRisk.HIGH,
                   lambda: called.append(True), require_confirmation=True)
    result = layer.execute("dangerous")
    assert result is True
    assert "dangerous" in confirmed


def test_confirmation_handler_denies():
    def on_confirm(name):
        return False
    layer = DesktopActionLayer(confirmation_handler=on_confirm)
    called = []
    layer.register("dangerous", "Dangerous action", ActionRisk.HIGH,
                   lambda: called.append(True), require_confirmation=True)
    result = layer.execute("dangerous")
    assert result is False
    assert len(called) == 0


def test_handler_exception_is_caught():
    layer = DesktopActionLayer()
    def failing_action():
        raise RuntimeError("something broke")
    layer.register("failing", "Failing action", ActionRisk.SAFE, failing_action)
    result = layer.execute("failing")
    assert result is False


def test_command_not_found_returns_false():
    """A command that doesn't exist should be reported as failed."""
    layer = DesktopActionLayer()
    layer.register("nonexistent_cmd", "Nonexistent", ActionRisk.SAFE,
                   lambda: layer._wmctrl("--nonexistent-flag"))
    result = layer.execute("nonexistent_cmd")
    assert result is False


def test_action_history_logged():
    layer = DesktopActionLayer()
    layer.register("hist_test", "Test action", ActionRisk.SAFE, lambda: None)
    layer.execute("hist_test")
    history = layer.get_history()
    assert len(history) >= 1
    assert history[-1]["action"] == "hist_test"


def test_get_actions_by_category():
    layer = DesktopActionLayer()
    media = layer.get_actions("media")
    assert len(media) >= 3
    assert all(a.category == "media" for a in media)
