"""Gesture recognition for JARVIS Desktop.

Classifies hand landmarks into gesture events with debouncing to
prevent accidental repeated activations.

Gesture vocabulary (master plan §7):
  - Pinch: thumb tip close to index tip
  - Pinch + move: pinch held while hand moves
  - Open palm: all fingers extended
  - Zoom in: both hands separating
  - Zoom out: both hands approaching
  - Horizontal swipe: hand moving left/right
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable

from app.gestures.tracking import HandLandmarks

logger = logging.getLogger("jarvis.desktop.gestures.recognition")


class GestureType(StrEnum):
    NONE = "none"
    PINCH = "pinch"
    PINCH_MOVE = "pinch_move"
    OPEN_PALM = "open_palm"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    SWIPE_LEFT = "swipe_left"
    SWIPE_RIGHT = "swipe_right"
    GRAB = "grab"
    RELEASE = "release"


@dataclass
class GestureEvent:
    """A recognized gesture event."""
    gesture: GestureType
    confidence: float = 0.0
    hand: str = "Right"  # which hand triggered it
    position: tuple[float, float] = (0.0, 0.0)  # normalized hand position
    timestamp: float = 0.0
    metadata: dict = field(default_factory=dict)


# MediaPipe landmark indices
WRIST = 0
THUMB_TIP = 4
INDEX_TIP = 8
MIDDLE_TIP = 12
RING_TIP = 16
PINKY_TIP = 20
INDEX_PIP = 6
MIDDLE_PIP = 10
RING_PIP = 14
PINKY_PIP = 18

# Distance thresholds (normalized coordinates)
PINCH_THRESHOLD = 0.08
FINGER_EXTEND_THRESHOLD = 0.05
SWIPE_VELOCITY_THRESHOLD = 0.3  # normalized units per second
DEBOUNCE_SECONDS = 0.5


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def _is_finger_extended(hand: HandLandmarks, tip_idx: int, pip_idx: int) -> bool:
    """Check if a finger is extended (tip further from wrist than PIP)."""
    wrist = hand.landmark(WRIST)
    tip = hand.landmark(tip_idx)
    pip = hand.landmark(pip_idx)
    if wrist is None or tip is None or pip is None:
        return False
    return _distance(wrist, tip) > _distance(wrist, pip) + FINGER_EXTEND_THRESHOLD


def _is_pinch(hand: HandLandmarks) -> bool:
    """Check if thumb and index are close enough to pinch."""
    thumb = hand.landmark(THUMB_TIP)
    index = hand.landmark(INDEX_TIP)
    if thumb is None or index is None:
        return False
    return _distance(thumb, index) < PINCH_THRESHOLD


def _is_open_palm(hand: HandLandmarks) -> bool:
    """Check if all four fingers are extended."""
    return (
        _is_finger_extended(hand, INDEX_TIP, INDEX_PIP) and
        _is_finger_extended(hand, MIDDLE_TIP, MIDDLE_PIP) and
        _is_finger_extended(hand, RING_TIP, RING_PIP) and
        _is_finger_extended(hand, PINKY_TIP, PINKY_PIP)
    )


def _hand_position(hand: HandLandmarks) -> tuple[float, float]:
    """Get normalized hand center position (average of wrist and middle MCP)."""
    wrist = hand.landmark(WRIST)
    middle = hand.landmark(MIDDLE_TIP)
    if wrist is None or middle is None:
        return (0.0, 0.0)
    return ((wrist[0] + middle[0]) / 2, (wrist[1] + middle[1]) / 2)


class GestureRecognizer:
    """Classifies hand landmarks into gesture events with debouncing.

    Usage:
        rec = GestureRecognizer(on_gesture=handler)
        rec.process(hands)  # call each frame with tracked hands
    """

    def __init__(self, *, on_gesture: Callable[[GestureEvent], None] | None = None,
                 debounce_seconds: float = DEBOUNCE_SECONDS):
        self._on_gesture = on_gesture
        self._debounce = debounce_seconds
        self._last_gesture: GestureType = GestureType.NONE
        self._last_gesture_time: float = 0.0
        self._last_position: dict[str, tuple[float, float]] = {}
        self._pinch_active: dict[str, bool] = {}
        self._prev_hands: dict[str, HandLandmarks] = {}

    def process(self, hands: list[HandLandmarks]) -> list[GestureEvent]:
        """Process a frame of hand landmarks. Returns recognized events."""
        events = []
        current_time = time.time()
        current_hands = {h.handedness: h for h in hands}

        for handedness, hand in current_hands.items():
            if not hand.is_valid:
                continue

            pos = _hand_position(hand)
            prev = self._prev_hands.get(handedness)
            prev_pos = self._last_position.get(handedness, pos)

            # Calculate velocity
            dt = current_time - (prev.timestamp if prev else current_time)
            if dt > 0:
                vx = (pos[0] - prev_pos[0]) / dt
                vy = (pos[1] - prev_pos[1]) / dt
            else:
                vx = vy = 0.0

            # Detect gestures
            pinch = _is_pinch(hand)
            open_palm = _is_open_palm(hand)

            # Pinch state machine
            was_pinch = self._pinch_active.get(handedness, False)
            if pinch and not was_pinch:
                # Pinch started
                self._pinch_active[handedness] = True
                events.append(self._emit(GestureType.PINCH, hand, pos, current_time))
            elif pinch and was_pinch:
                # Pinch held — check for movement
                if abs(vx) > SWIPE_VELOCITY_THRESHOLD or abs(vy) > SWIPE_VELOCITY_THRESHOLD:
                    events.append(self._emit(GestureType.PINCH_MOVE, hand, pos, current_time,
                                              {"vx": vx, "vy": vy}))
            elif not pinch and was_pinch:
                # Pinch released
                self._pinch_active[handedness] = False
                events.append(self._emit(GestureType.RELEASE, hand, pos, current_time))

            # Open palm (only if not pinching)
            if open_palm and not pinch:
                events.append(self._emit(GestureType.OPEN_PALM, hand, pos, current_time))

            # Swipe detection (fast horizontal movement without pinch)
            if not pinch and abs(vx) > SWIPE_VELOCITY_THRESHOLD * 2:
                if vx > 0:
                    events.append(self._emit(GestureType.SWIPE_RIGHT, hand, pos, current_time))
                else:
                    events.append(self._emit(GestureType.SWIPE_LEFT, hand, pos, current_time))

            self._last_position[handedness] = pos
            self._prev_hands[handedness] = hand

        # Two-hand zoom detection
        if len(current_hands) == 2:
            left = current_hands.get("Left")
            right = current_hands.get("Right")
            if left and right and left.is_valid and right.is_valid:
                dist = _distance(_hand_position(left), _hand_position(right))
                prev_left = self._prev_hands.get("Left")
                prev_right = self._prev_hands.get("Right")
                if prev_left and prev_right:
                    prev_dist = _distance(_hand_position(prev_left), _hand_position(prev_right))
                    if dist > prev_dist + 0.05:
                        events.append(self._emit(GestureType.ZOOM_IN, right, pos, current_time))
                    elif dist < prev_dist - 0.05:
                        events.append(self._emit(GestureType.ZOOM_OUT, right, pos, current_time))

        return events

    def _emit(self, gesture: GestureType, hand: HandLandmarks,
              position: tuple[float, float], timestamp: float,
              metadata: dict | None = None) -> GestureEvent:
        """Emit a gesture event with debouncing."""
        # Debounce: skip if same gesture fired recently
        if gesture == self._last_gesture and (timestamp - self._last_gesture_time) < self._debounce:
            return GestureEvent(GestureType.NONE, 0.0, hand.handedness, position, timestamp)

        self._last_gesture = gesture
        self._last_gesture_time = timestamp

        event = GestureEvent(
            gesture=gesture,
            confidence=hand.confidence,
            hand=hand.handedness,
            position=position,
            timestamp=timestamp,
            metadata=metadata or {},
        )
        if self._on_gesture and gesture != GestureType.NONE:
            self._on_gesture(event)
        return event

    def reset(self) -> None:
        """Reset all state (e.g., when tracking is lost)."""
        self._last_gesture = GestureType.NONE
        self._last_gesture_time = 0.0
        self._last_position.clear()
        self._pinch_active.clear()
        self._prev_hands.clear()
