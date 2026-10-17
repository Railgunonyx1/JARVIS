"""Hand tracking for JARVIS Desktop gestures.

Uses MediaPipe Hands for 21-landmark hand tracking. Runs in a worker
thread, processing frames from the Camera layer.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

logger = logging.getLogger("jarvis.desktop.gestures.tracking")


@dataclass
class HandLandmarks:
    """21 hand landmarks from MediaPipe (normalized 0-1 coordinates)."""
    landmarks: list[tuple[float, float, float]] = field(default_factory=list)
    handedness: str = "Right"  # "Left" or "Right"
    confidence: float = 0.0
    timestamp: float = 0.0

    @property
    def is_valid(self) -> bool:
        return len(self.landmarks) == 21 and self.confidence > 0.5

    def landmark(self, idx: int) -> tuple[float, float, float] | None:
        if 0 <= idx < len(self.landmarks):
            return self.landmarks[idx]
        return None


class HandTracker:
    """MediaPipe hand tracking in a worker thread.

    Usage:
        tracker = HandTracker()
        tracker.start()
        hands = tracker.hands  # list[HandLandmarks]
        tracker.stop()
    """

    def __init__(self, *, max_hands: int = 2,
                 detection_confidence: float = 0.7,
                 tracking_confidence: float = 0.5,
                 on_hands: Callable[[list[HandLandmarks]], None] | None = None,
                 target_fps: int = 30):
        self._max_hands = max_hands
        self._detection_confidence = detection_confidence
        self._tracking_confidence = tracking_confidence
        self._on_hands = on_hands
        self._running = False
        self._lock = threading.Lock()
        self._hands: list[HandLandmarks] = []
        self._thread: threading.Thread | None = None
        self._mp = None
        self._frame_source: Callable[[], np.ndarray | None] | None = None
        self._target_fps = max(1, target_fps)
        self._min_frame_interval = 1.0 / self._target_fps
        self._last_frame_time = 0.0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def hands(self) -> list[HandLandmarks]:
        with self._lock:
            return list(self._hands)

    def set_frame_source(self, source: Callable[[], np.ndarray | None]) -> None:
        """Set the frame source (typically Camera.latest_frame)."""
        self._frame_source = source

    def start(self) -> bool:
        """Start tracking. Returns True on success."""
        if self._running:
            return True
        try:
            import mediapipe as mp
            self._mp_hands = mp.solutions.hands
            self._mp = self._mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=self._max_hands,
                min_detection_confidence=self._detection_confidence,
                min_tracking_confidence=self._tracking_confidence,
            )
            self._running = True
            self._thread = threading.Thread(
                target=self._track_loop, daemon=True, name="jarvis-hand-tracker"
            )
            self._thread.start()
            logger.info("Hand tracker started (max_hands=%d)", self._max_hands)
            return True
        except Exception as e:
            logger.error("Hand tracker start failed: %s", e)
            self._mp = None
            self._running = False
            return False

    def stop(self) -> None:
        """Stop tracking and release resources."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._mp:
            self._mp.close()
            self._mp = None
        with self._lock:
            self._hands = []
        logger.info("Hand tracker stopped")

    def _track_loop(self) -> None:
        """Background tracking loop."""
        while self._running:
            try:
                if self._frame_source is None:
                    time.sleep(0.03)
                    continue
                # Frame rate limiting — don't process faster than target FPS
                now = time.perf_counter()
                elapsed = now - self._last_frame_time
                if elapsed < self._min_frame_interval:
                    time.sleep(self._min_frame_interval - elapsed)
                    continue
                self._last_frame_time = time.perf_counter()

                frame = self._frame_source()
                if frame is None:
                    time.sleep(0.03)
                    continue
                # Convert BGR to RGB for MediaPipe
                rgb = frame[:, :, ::-1]
                results = self._mp.process(rgb)
                hands = []
                if results.multi_hand_landmarks:
                    for idx, (landmarks, handedness) in enumerate(
                        zip(results.multi_hand_landmarks, results.multi_handedness)
                    ):
                        lm_list = [(lm.x, lm.y, lm.z) for lm in landmarks.landmark]
                        hand = HandLandmarks(
                            landmarks=lm_list,
                            handedness=handedness.classification[0].label,
                            confidence=handedness.classification[0].score,
                            timestamp=time.time(),
                        )
                        hands.append(hand)
                with self._lock:
                    self._hands = hands
                if self._on_hands:
                    self._on_hands(hands)
            except Exception as e:
                logger.debug("Tracking error: %s", e)
                time.sleep(0.05)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
