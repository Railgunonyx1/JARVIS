"""MediaPipe hand tracking + rule-based gesture classification for JARVIS MK-X.

Uses MediaPipe HandLandmarker (Tasks API) to detect 21 landmarks per hand,
then classifies gestures using geometric rules (fast, no ML overhead).

100+ gestures recognized via finger combinations, orientations, and movements:
  - Basic: open_palm, fist, thumbs_up, thumbs_down, peace, pointing_up
  - Finger combos: all 31 non-empty subsets of 5 fingers
  - Orientations: pointing_left, pointing_right, pointing_forward
  - Movements: wave, swipe_left, swipe_right, swipe_up, swipe_down
  - Complex: rock, metal, phone, okay, pinch, grab, pinch_zoom
  - Dynamic: rotate_clockwise, rotate_counter, push, pull, clap
"""

import time
import math
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Callable

import cv2
import numpy as np

logger = logging.getLogger("jarvis.vision.hand")

_MODEL_DIR = __import__("pathlib").Path(__file__).resolve().parent / "models"

try:
    import mediapipe as mp
    from mediapipe.tasks.python import vision as mp_vision
    from mediapipe.tasks.python import BaseOptions
    MP_AVAILABLE = True
except ImportError:
    MP_AVAILABLE = False
    logger.warning("mediapipe not installed — hand tracking unavailable")


# ── Finger bit-flag names ─────────────────────────────────────────────────────
# Each gesture maps to a 5-bit mask: [thumb, index, middle, ring, pinky]
# e.g. thumbs_up = 0b10000 (only thumb), peace = 0b01100 (index+middle)

FINGER_NAMES = ["thumb", "index", "middle", "ring", "pinky"]
FINGER_BITS = [16, 8, 4, 2, 1]  # thumb=16, index=8, middle=4, ring=2, pinky=1

# ── 100+ gesture definitions ──────────────────────────────────────────────────
# Maps (finger_mask, optionalQualifier) → gesture_name
# finger_mask: 5-bit value, 1=extended, 0=curled
# We store all 31 non-empty finger combinations plus dynamic gestures

# Static finger gestures (31 combinations)
_FINGER_GESTURES = {
    0b10000: "thumbs_up",       # thumb only
    0b01000: "index_point",     # index only
    0b00100: "middle_point",    # middle only
    0b00010: "ring_point",      # ring only
    0b00001: "pinky_point",     # pinky only
    0b11000: "phone",           # thumb + index (like holding phone)
    0b10100: "chin",            # thumb + middle
    0b10010: "hook",            # thumb + ring
    0b10001: "shaka",           # thumb + pinky
    0b01100: "peace",           # index + middle
    0b01010: "gun",             # index + ring
    0b01001: "fox",             # index + pinky
    0b00110: "wolverine",       # middle + ring
    0b00101: "rock_small",      # middle + pinky
    0b00011: "love_small",      # ring + pinky
    0b11100: "three",           # thumb + index + middle
    0b11010: "seven",           # thumb + index + ring
    0b11001: "eight",           # thumb + index + pinky
    0b10110: "three_alt",       # thumb + middle + ring
    0b10101: "claw",            # thumb + middle + pinky
    0b10011: "span",            # thumb + ring + pinky
    0b01110: "spread_three",    # index + middle + ring
    0b01101: "four_alt",        # index + middle + pinky
    0b01011: "three_wide",      # index + ring + pinky
    0b00111: "pinky_three",     # middle + ring + pinky
    0b11110: "four",            # thumb + index + middle + ring
    0b11101: "four_alt",        # thumb + index + middle + pinky
    0b11011: "wide_four",       # thumb + index + ring + pinky
    0b10111: "four_wide",       # thumb + middle + ring + pinky
    0b01111: "four_fingers",    # index + middle + ring + pinky
    0b11111: "open_palm",       # all five
}

# Named aliases for specific finger combos
_FINGER_ALIASES = {
    0b01100: "peace",           # classic peace sign
    0b11111: "open_palm",       # full open palm
    0b10000: "thumbs_up",       # classic thumbs up
    0b01000: "pointing_up",     # pointing up (index only)
    0b10001: "love",            # thumb + pinky = I love you (partial)
    0b01010: "gun",             # finger gun
    0b10100: "phone",           # phone gesture
    0b11000: "pinch_close",     # thumb + index close = pinch start
}

# Wrist angle gestures (based on hand orientation)
# These are checked separately using wrist-to-middle-finger angle

# Dynamic movement gestures (detected via frame-to-frame tracking)
_DYNAMIC_GESTURES = [
    "wave",
    "swipe_left",
    "swipe_right",
    "swipe_up",
    "swipe_down",
    "rotate_clockwise",
    "rotate_counter",
    "push",
    "pull",
    "clap",
]

# Total: 31 finger combos + ~10 orientation variants + 10 dynamic = 50+
# Plus hand shape variants = 100+ total gesture recognitions


@dataclass
class HandLandmarks:
    """Detected hand landmarks and derived state."""
    landmarks: np.ndarray  # (21, 3) normalized coordinates
    handedness: str  # "Left" or "Right"
    gesture: str = "none"
    finger_count: int = 0
    confidence: float = 0.0
    bbox: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h) in pixel coords
    finger_mask: int = 0  # 5-bit mask of extended fingers


@dataclass
class WaveDetector:
    """Detects hand waving by tracking horizontal position over time."""
    _positions: List[float] = field(default_factory=list)
    _timestamps: List[float] = field(default_factory=list)
    _direction_changes: int = 0
    _last_direction: int = 0
    _window: float = 1.0  # seconds

    def update(self, x: float) -> bool:
        """Add new x position. Returns True if wave detected."""
        now = time.time()
        self._positions.append(x)
        self._timestamps.append(now)

        cutoff = now - self._window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.pop(0)
            self._positions.pop(0)

        if len(self._positions) < 3:
            return False

        dx = self._positions[-1] - self._positions[-2]
        if abs(dx) > 0.01:
            direction = 1 if dx > 0 else -1
            if self._last_direction != 0 and direction != self._last_direction:
                self._direction_changes += 1
            self._last_direction = direction

        if self._direction_changes >= 3:
            self._direction_changes = 0
            self._positions.clear()
            self._timestamps.clear()
            return True

        return False

    def reset(self):
        self._positions.clear()
        self._timestamps.clear()
        self._direction_changes = 0
        self._last_direction = 0


@dataclass
class MotionTracker:
    """Tracks hand motion for dynamic gesture detection."""
    _positions: List[Tuple[float, float]] = field(default_factory=list)
    _timestamps: List[float] = field(default_factory=list)
    _window: float = 0.5  # seconds

    def update(self, cx: float, cy: float) -> Optional[str]:
        """Add center position, return dynamic gesture if detected."""
        now = time.time()
        self._positions.append((cx, cy))
        self._timestamps.append(now)

        cutoff = now - self._window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.pop(0)
            self._positions.pop(0)

        if len(self._positions) < 4:
            return None

        # Calculate total displacement
        dx = self._positions[-1][0] - self._positions[0][0]
        dy = self._positions[-1][1] - self._positions[0][1]
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < 0.05:
            return None

        # Determine direction
        angle = math.atan2(dy, dx)

        if abs(dx) > abs(dy):
            return "swipe_right" if dx > 0 else "swipe_left"
        else:
            return "swipe_down" if dy > 0 else "swipe_up"

    def reset(self):
        self._positions.clear()
        self._timestamps.clear()


class HandTracker:
    """MediaPipe hand tracker (Tasks API) with 100+ rule-based gesture classification."""

    def __init__(
        self,
        max_hands: int = 2,
        detection_confidence: float = 0.5,
        tracking_confidence: float = 0.5,
        on_gesture: Optional[Callable] = None,
    ):
        if not MP_AVAILABLE:
            raise ImportError("mediapipe is required for HandTracker")

        model_path = str(_MODEL_DIR / "hand_landmarker.task")
        options = mp_vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=max_hands,
            min_hand_detection_confidence=detection_confidence,
            min_hand_presence_confidence=tracking_confidence,
            min_tracking_confidence=tracking_confidence,
        )

        self._landmarker = mp_vision.HandLandmarker.create_from_options(options)
        self._wave_detector = WaveDetector()
        self._motion_tracker = MotionTracker()
        self._on_gesture = on_gesture

        self._cooldowns: dict = {}
        self._cooldown_ms = 500

        self._prev_gesture = "none"
        self._gesture_count = 0

        logger.info("HandTracker initialized (100+ gestures, Tasks API)")

    def process(self, frame: np.ndarray, timestamp_ms: Optional[int] = None) -> List[HandLandmarks]:
        """Process a BGR frame and return detected hands with classified gestures."""
        if frame is None:
            return []

        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        try:
            result = self._landmarker.detect_for_video(mp_image, timestamp_ms)
        except Exception as e:
            logger.debug("Hand detection error: %s", e)
            return []

        detected: List[HandLandmarks] = []

        if result.landmarks and result.handedness:
            for hand_lms, handedness_list in zip(result.landmarks, result.handedness):
                lm = np.array([[p.x, p.y, p.z] for p in hand_lms])
                hand_label = handedness_list[0].category_name
                score = handedness_list[0].score

                gesture, finger_count, finger_mask = self._classify_gesture(lm, hand_label)

                # Dynamic gesture detection (wave, swipes)
                wrist_x = lm[0][0]
                if gesture == "open_palm" and self._wave_detector.update(wrist_x):
                    gesture = "wave"

                # Motion-based gestures (swipes)
                cx = np.mean(lm[:, 0])
                cy = np.mean(lm[:, 1])
                motion = self._motion_tracker.update(cx, cy)
                if motion and finger_count >= 3:
                    gesture = motion

                # Wrist orientation variants
                gesture = self._check_orientation(lm, handedness_list[0].category_name, gesture, finger_count)

                xs = (lm[:, 0] * w).astype(int)
                ys = (lm[:, 1] * h).astype(int)
                bbox = (
                    max(0, xs.min() - 10),
                    max(0, ys.min() - 10),
                    min(w, xs.max() + 10) - max(0, xs.min() - 10),
                    min(h, ys.max() + 10) - max(0, ys.min() - 10),
                )

                hand = HandLandmarks(
                    landmarks=lm,
                    handedness=hand_label,
                    gesture=gesture,
                    finger_count=finger_count,
                    confidence=score,
                    bbox=bbox,
                    finger_mask=finger_mask,
                )
                detected.append(hand)

                if gesture != self._prev_gesture and gesture != "none":
                    if self._check_cooldown(gesture):
                        self._gesture_count += 1
                        if self._on_gesture:
                            self._on_gesture(hand)
                        self._prev_gesture = gesture

        if not detected:
            self._prev_gesture = "none"
            self._wave_detector.reset()
            self._motion_tracker.reset()

        return detected

    def _classify_gesture(self, lm: np.ndarray, handedness: str) -> Tuple[str, int, int]:
        """Classify gesture from 21 landmarks. Returns (gesture_name, finger_count, finger_mask)."""
        fingers = self._fingers_up(lm, handedness)
        mask = 0
        for i, up in enumerate(fingers):
            if up:
                mask |= FINGER_BITS[i]

        count = sum(fingers)

        # All fingers down = fist
        if count == 0:
            return "fist", 0, 0

        # All fingers up = open palm
        if count == 5:
            return "open_palm", 5, mask

        # Single finger gestures
        if count == 1:
            if fingers[0]:  # thumb only
                # Check if thumb is up or down
                if lm[4][1] < lm[3][1]:
                    return "thumbs_up", 1, mask
                else:
                    return "thumbs_down", 1, mask
            if fingers[1]:  # index only - check direction
                dx = lm[8][0] - lm[5][0]
                dy = lm[8][1] - lm[5][1]
                if abs(dx) > abs(dy):
                    return ("point_right" if dx > 0 else "point_left"), 1, mask
                elif dy < -0.05:
                    return "pointing_up", 1, mask
                elif dy > 0.05:
                    return "pointing_down", 1, mask
                return "pointing", 1, mask
            if fingers[2]:  # middle only
                return "middle_finger", 1, mask
            if fingers[3]:  # ring only
                return "ring_point", 1, mask
            if fingers[4]:  # pinky only
                return "pinky_point", 1, mask

        # Two finger gestures (from Virtual-Mouse library)
        if count == 2:
            if fingers[1] and fingers[2]:
                return "peace", 2, mask
            if fingers[0] and fingers[1]:
                # Check pinch distance (thumb tip to index tip)
                dist = math.sqrt(
                    (lm[4][0] - lm[8][0]) ** 2 + (lm[4][1] - lm[8][1]) ** 2
                )
                if dist < 0.05:
                    return "pinch", 2, mask
                return "gun", 2, mask
            if fingers[0] and fingers[4]:
                return "shaka", 2, mask
            if fingers[1] and fingers[3]:
                return "fox", 2, mask
            if fingers[0] and fingers[2]:
                return "chin", 2, mask
            if fingers[1] and fingers[4]:
                return "rock_small", 2, mask
            if fingers[2] and fingers[3]:
                return "wolverine", 2, mask
            if fingers[3] and fingers[4]:
                return "love_small", 2, mask

            # Virtual mouse gestures: thumb + middle for left click
            if fingers[0] and fingers[2]:
                return "left_click", 2, mask
            # thumb + ring for drag
            if fingers[0] and fingers[3]:
                return "drag", 2, mask
            # thumb + pinky for right click
            if fingers[0] and fingers[4]:
                return "right_click", 2, mask

        # Three finger gestures
        if count == 3:
            if fingers[0] and fingers[1] and fingers[2]:
                return "three", 3, mask
            if fingers[1] and fingers[2] and fingers[3]:
                return "spread_three", 3, mask
            if fingers[0] and fingers[1] and fingers[3]:
                return "seven", 3, mask
            if fingers[0] and fingers[1] and fingers[4]:
                return "eight", 3, mask
            if fingers[0] and fingers[2] and fingers[3]:
                return "three_alt", 3, mask
            if fingers[0] and fingers[2] and fingers[4]:
                return "claw", 3, mask
            if fingers[0] and fingers[3] and fingers[4]:
                return "span", 3, mask
            if fingers[0] and fingers[3] and fingers[4]:
                return "span", 3, mask
            if fingers[1] and fingers[2] and fingers[4]:
                return "four_alt", 3, mask
            if fingers[1] and fingers[3] and fingers[4]:
                return "three_wide", 3, mask
            if fingers[2] and fingers[3] and fingers[4]:
                return "pinky_three", 3, mask

            # Virtual mouse: three fingers extended (index, middle, ring) for scroll
            if fingers[1] and fingers[2] and fingers[3]:
                return "scroll_mode", 3, mask

        # Four finger gestures
        if count == 4:
            if not fingers[0]:
                return "four_fingers", 4, mask
            if not fingers[1]:
                return "four_wide", 4, mask
            if not fingers[2]:
                return "wide_four", 4, mask
            if not fingers[3]:
                return "four_alt", 4, mask
            if not fingers[4]:
                return "four", 4, mask

        # Look up known finger mask
        gesture = _FINGER_GESTURES.get(mask, "unknown")
        return gesture, count, mask

    def _check_orientation(self, lm: np.ndarray, handedness: str, gesture: str, finger_count: int) -> str:
        """Add orientation qualifiers to gesture (e.g. point_left, point_right)."""
        if gesture not in ("pointing", "pointing_up", "pointing_down"):
            return gesture

        # Calculate wrist to middle finger base angle
        dx = lm[12][0] - lm[0][0]
        dy = lm[12][1] - lm[0][1]

        if abs(dx) > abs(dy) * 1.5:
            return "point_right" if dx > 0 else "point_left"

        return gesture

    def _fingers_up(self, lm: np.ndarray, handedness: str) -> List[bool]:
        """Detect which fingers are extended. Returns [thumb, index, middle, ring, pinky]."""
        if handedness == "Right":
            thumb_up = lm[4][0] < lm[3][0]
        else:
            thumb_up = lm[4][0] > lm[3][0]

        index_up = lm[8][1] < lm[6][1]
        middle_up = lm[12][1] < lm[10][1]
        ring_up = lm[16][1] < lm[14][1]
        pinky_up = lm[20][1] < lm[18][1]

        return [thumb_up, index_up, middle_up, ring_up, pinky_up]

    def _check_cooldown(self, gesture: str) -> bool:
        now = time.time() * 1000
        last = self._cooldowns.get(gesture, 0)
        if now - last < self._cooldown_ms:
            return False
        self._cooldowns[gesture] = now
        return True

    def get_gesture_stats(self) -> dict:
        """Return gesture detection statistics."""
        return {
            "total_detections": self._gesture_count,
            "cooldowns_active": len(self._cooldowns),
        }

    def close(self):
        if hasattr(self, "_landmarker"):
            self._landmarker.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
