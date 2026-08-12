"""MediaPipe Gesture Recognizer for JARVIS MK-X.

Uses Google's official ML-based gesture recognizer model (Tasks API).
Built-in gestures: Closed_Fist, Open_Palm, Pointing_Up, Thumb_Down, Thumb_Up, Victory, ILoveYou.

This is the higher-level alternative to hand_tracker.py's rule-based classifier.
Run this for gesture commands; run hand_tracker for cursor/mouse control.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger("jarvis.vision.gesture")

_MODEL_DIR = Path(__file__).resolve().parent / "models"

try:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python import vision as mp_vision
    MP_TASKS_AVAILABLE = True
except ImportError:
    MP_TASKS_AVAILABLE = False
    logger.warning("mediapipe tasks API not available — ML gesture recognition unavailable")


GESTURE_ALIASES = {
    "Closed_Fist": "fist",
    "Open_Palm": "open_palm",
    "Pointing_Up": "pointing_up",
    "Thumb_Down": "thumbs_down",
    "Thumb_Up": "thumbs_up",
    "Victory": "victory",
    "ILoveYou": "love",
}

DEFAULT_GESTURE_ACTIONS = {
    "open_palm": "mute",
    "thumbs_up": "confirm",
    "thumbs_down": "deny",
    "victory": "wake",
    "fist": "stop",
    "pointing_up": "select",
    "love": "favorite",
}


@dataclass
class GestureResult:
    """Result from gesture recognition."""
    gesture: str
    raw_gesture: str
    score: float
    timestamp: float


class GestureEngine:
    """ML-based gesture recognition using MediaPipe GestureRecognizer (Tasks API)."""

    def __init__(
        self,
        on_gesture: Callable | None = None,
        confidence_threshold: float = 0.7,
        cooldown_ms: int = 800,
    ):
        if not MP_TASKS_AVAILABLE:
            raise ImportError("mediapipe[tasks] is required for GestureEngine")

        self._on_gesture = on_gesture
        self._confidence_threshold = confidence_threshold
        self._cooldown_ms = cooldown_ms
        self._last_gesture_time: dict = {}
        self._available = False
        self._recognizer = None

        model_path = str(_MODEL_DIR / "gesture_recognizer.task")
        options = mp_vision.GestureRecognizerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        try:
            self._recognizer = mp_vision.GestureRecognizer.create_from_options(options)
            self._available = True
            logger.info("GestureEngine initialized (ML-based, 7 built-in gestures)")
        except Exception as e:
            logger.warning("GestureEngine init failed: %s", e)
            self._recognizer = None

    @property
    def available(self) -> bool:
        return self._available

    def process(self, frame: np.ndarray, timestamp_ms: int | None = None) -> list[GestureResult]:
        """Process a BGR frame and return detected gestures."""
        if not self._available or frame is None:
            return []

        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        try:
            result = self._recognizer.recognize_for_video(mp_image, timestamp_ms)
        except Exception as e:
            logger.debug("Gesture recognition error: %s", e)
            return []

        gestures: list[GestureResult] = []

        if result.gestures:
            for hand_gestures in result.gestures:
                if hand_gestures:
                    top = hand_gestures[0]
                    raw = top.category_name
                    friendly = GESTURE_ALIASES.get(raw, raw.lower())
                    score = top.score

                    if score >= self._confidence_threshold and friendly != "none":
                        gr = GestureResult(
                            gesture=friendly,
                            raw_gesture=raw,
                            score=score,
                            timestamp=timestamp_ms / 1000.0,
                        )
                        gestures.append(gr)

                        if self._check_cooldown(friendly):
                            if self._on_gesture:
                                self._on_gesture(gr)

        return gestures

    def _check_cooldown(self, gesture: str) -> bool:
        now = time.time() * 1000
        last = self._last_gesture_time.get(gesture, 0)
        if now - last < self._cooldown_ms:
            return False
        self._last_gesture_time[gesture] = now
        return True

    def get_action_for_gesture(self, gesture: str) -> str | None:
        """Map a gesture name to a JARVIS action."""
        return DEFAULT_GESTURE_ACTIONS.get(gesture)

    def close(self):
        if self._recognizer:
            self._recognizer.close()
            self._recognizer = None
        self._available = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
