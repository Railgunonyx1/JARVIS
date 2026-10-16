"""Phase 4 — gesture recognition + desktop action tests (hermetic)."""

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


def _make_hand(landmarks: list[tuple[float, float, float]], handedness: str = "Right",
               confidence: float = 0.9):
    from app.gestures.tracking import HandLandmarks
    return HandLandmarks(landmarks=landmarks, handedness=handedness,
                         confidence=confidence, timestamp=time.time())


def _default_landmarks() -> list[tuple[float, float, float]]:
    """Generate 21 landmarks in a neutral open-palm pose."""
    # Wrist at origin, fingers extended upward
    lm = [(0.5, 0.5, 0.0)]  # wrist
    # Thumb
    lm.extend([(0.4, 0.4, 0.0), (0.35, 0.35, 0.0), (0.3, 0.3, 0.0), (0.25, 0.25, 0.0)])
    # Index finger (extended)
    lm.extend([(0.5, 0.4, 0.0), (0.5, 0.3, 0.0), (0.5, 0.2, 0.0), (0.5, 0.1, 0.0)])
    # Middle finger (extended)
    lm.extend([(0.55, 0.4, 0.0), (0.55, 0.3, 0.0), (0.55, 0.2, 0.0), (0.55, 0.1, 0.0)])
    # Ring finger (extended)
    lm.extend([(0.6, 0.4, 0.0), (0.6, 0.3, 0.0), (0.6, 0.2, 0.0), (0.6, 0.1, 0.0)])
    # Pinky (extended)
    lm.extend([(0.65, 0.4, 0.0), (0.65, 0.3, 0.0), (0.65, 0.2, 0.0), (0.65, 0.1, 0.0)])
    return lm


def _pinch_landmarks() -> list[tuple[float, float, float]]:
    """Generate landmarks in a pinch pose (thumb touching index)."""
    lm = _default_landmarks()
    # Move thumb tip close to index tip
    lm[4] = (0.5, 0.12, 0.0)  # thumb tip near index tip
    return lm


class TestGestureRecognition:
    def test_open_palm_detected(self):
        from app.gestures.recognition import GestureRecognizer, GestureType
        rec = GestureRecognizer()
        hand = _make_hand(_default_landmarks())
        events = rec.process([hand])
        gestures = [e.gesture for e in events if e.gesture != GestureType.NONE]
        assert GestureType.OPEN_PALM in gestures

    def test_pinch_detected(self):
        from app.gestures.recognition import GestureRecognizer, GestureType
        rec = GestureRecognizer()
        hand = _make_hand(_pinch_landmarks())
        events = rec.process([hand])
        gestures = [e.gesture for e in events if e.gesture != GestureType.NONE]
        assert GestureType.PINCH in gestures

    def test_no_gesture_for_empty_hands(self):
        from app.gestures.recognition import GestureRecognizer, GestureType
        rec = GestureRecognizer()
        events = rec.process([])
        assert all(e.gesture == GestureType.NONE for e in events)

    def test_debounce_prevents_repeats(self):
        from app.gestures.recognition import GestureRecognizer, GestureType
        rec = GestureRecognizer(debounce_seconds=1.0)
        hand = _make_hand(_default_landmarks())
        events1 = rec.process([hand])
        events2 = rec.process([hand])  # immediately after
        # Second call should be debounced
        assert all(e.gesture == GestureType.NONE for e in events2)

    def test_reset_clears_state(self):
        from app.gestures.recognition import GestureRecognizer, GestureType
        rec = GestureRecognizer()
        hand = _make_hand(_default_landmarks())
        rec.process([hand])
        rec.reset()
        # After reset, same gesture should fire again
        events = rec.process([hand])
        gestures = [e.gesture for e in events if e.gesture != GestureType.NONE]
        assert len(gestures) > 0


class TestGestureMapping:
    def test_default_mappings_exist(self):
        from app.gestures.mappings import GestureMapper, DEFAULT_MAPPINGS, GestureType
        mapper = GestureMapper()
        assert len(DEFAULT_MAPPINGS) >= 5
        assert GestureType.PINCH in DEFAULT_MAPPINGS
        assert GestureType.OPEN_PALM in DEFAULT_MAPPINGS

    def test_handler_called_on_gesture(self):
        from app.gestures.mappings import GestureMapper
        from app.gestures.recognition import GestureEvent, GestureType
        called = []
        mapper = GestureMapper()
        mapper.set_handler("select", lambda e: called.append(e))
        event = GestureEvent(GestureType.PINCH, 0.9, "Right", (0.5, 0.5), time.time())
        mapper.handle(event)
        assert len(called) == 1

    def test_disabled_gesture_not_handled(self):
        from app.gestures.mappings import GestureMapper
        from app.gestures.recognition import GestureEvent, GestureType
        called = []
        mapper = GestureMapper()
        mapper.set_handler("select", lambda e: called.append(e))
        mapper.enable_gesture(GestureType.PINCH, False)
        event = GestureEvent(GestureType.PINCH, 0.9, "Right", (0.5, 0.5), time.time())
        mapper.handle(event)
        assert len(called) == 0


class TestDesktopActions:
    def test_action_layer_constructs(self):
        from app.desktop.actions import DesktopActionLayer, ActionRisk
        layer = DesktopActionLayer()
        actions = layer.get_actions()
        assert len(actions) >= 5

    def test_register_and_execute_safe_action(self):
        from app.desktop.actions import DesktopActionLayer, ActionRisk
        layer = DesktopActionLayer()
        called = []
        layer.register("test_action", "Test", ActionRisk.SAFE, lambda: called.append(True))
        result = layer.execute("test_action")
        assert result is True
        assert len(called) == 1

    def test_unknown_action_fails(self):
        from app.desktop.actions import DesktopActionLayer
        layer = DesktopActionLayer()
        assert layer.execute("nonexistent") is False

    def test_confirmation_required_blocks_without_confirm(self):
        from app.desktop.actions import DesktopActionLayer, ActionRisk
        layer = DesktopActionLayer()
        called = []
        layer.register("dangerous", "Dangerous", ActionRisk.HIGH,
                       lambda: called.append(True), require_confirmation=True)
        result = layer.execute("dangerous", confirmed=False)
        assert result is False
        assert len(called) == 0

    def test_confirmation_allows_with_confirm(self):
        from app.desktop.actions import DesktopActionLayer, ActionRisk
        layer = DesktopActionLayer()
        called = []
        layer.register("dangerous", "Dangerous", ActionRisk.HIGH,
                       lambda: called.append(True), require_confirmation=True)
        result = layer.execute("dangerous", confirmed=True)
        assert result is True
        assert len(called) == 1

    def test_confirmation_handler_called(self):
        from app.desktop.actions import DesktopActionLayer, ActionRisk
        confirmed = []
        def on_confirm(name):
            confirmed.append(name)
            return True
        layer = DesktopActionLayer(confirmation_handler=on_confirm)
        called = []
        layer.register("dangerous", "Dangerous", ActionRisk.HIGH,
                       lambda: called.append(True), require_confirmation=True)
        result = layer.execute("dangerous")
        assert result is True
        assert "dangerous" in confirmed

    def test_action_history_logged(self):
        from app.desktop.actions import DesktopActionLayer, ActionRisk
        layer = DesktopActionLayer()
        layer.register("hist_test", "Test", ActionRisk.SAFE, lambda: None)
        layer.execute("hist_test")
        history = layer.get_history()
        assert len(history) >= 1
        assert history[-1]["action"] == "hist_test"

    def test_get_actions_by_category(self):
        from app.desktop.actions import DesktopActionLayer
        layer = DesktopActionLayer()
        media = layer.get_actions("media")
        assert len(media) >= 3
        assert all(a.category == "media" for a in media)
