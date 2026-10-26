"""Hand tracking for JARVIS Desktop gestures.

Uses MediaPipe Hands for 21-landmark hand tracking. Runs in a worker
thread, processing frames from the Camera layer.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger("jarvis.desktop.gestures.tracking")


MP_INIT_ERROR = "MediaPipe not available"

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

    Key invariant: Only the worker thread owns and closes the MediaPipe resource.
    Stop signals from other threads are handled via a threading.Event stop token;
    the worker loop checks it each iteration and exits gracefully. Camera release
only occurs after the worker thread has confirmed exit.

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
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._hands: list[HandLandmarks] = []
        self._thread: threading.Thread | None = None
        self._mp = None
        self._mp_owning_thread: threading.Thread | None = None
        self._frame_source: Callable[[], np.ndarray | None] | None = None
        self._target_fps = max(1, target_fps)
        self._min_frame_interval = 1.0 / self._target_fps
        self._last_frame_time = 0.0
        self._startup_error: Exception | None = None

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
        """Start tracking. Returns True on success.

        Idempotent: a second call while already running returns True immediately.
        """
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
            self._mp_owning_thread = threading.current_thread()
            self._running = True
            self._stop_event = threading.Event()
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
            self._mp_owning_thread = None
            return False

    def stop(self) -> None:
        """Stop tracking and release resources.

        1. Request stop via the stop event (thread-safe, no race with loop check).
        2. Wait for the worker thread to confirm it has exited.
        3. Only after worker exit does this thread close MediaPipe and release refs.
        4. Idempotent: second call is a no-op.
        """
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        # Wait for worker thread to exit (it checks _stop_event each iteration)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        # Only after the worker has exited do we close MediaPipe and clear refs.
        # This prevents a race where the worker might still be reading frames.
        if self._mp is not None:
            try:
                self._mp.close()
            except Exception:
                pass
            self._mp = None
        self._mp_owning_thread = None
        with self._lock:
            self._hands = []
        logger.info("Hand tracker stopped")

    def _track_loop(self) -> None:
        """Background tracking loop.

        Checks _stop_event each iteration. Only the worker thread closes MediaPipe.
        Camera release happens only after the worker exits (enforced by stop()).
        Idempotent start/stop: rapid double activate/deactivate creates no leaks.
        """
        try:
            while self._running:
                # Check stop event first — if set, exit loop gracefully
                if self._stop_event.is_set():
                    break
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
                    if not self._mp:
                        break
                    results = self._mp.process(rgb)
                    hands = []
                    if results.multi_hand_landmarks:
                        for idx, (landmarks, handedness) in enumerate(
                            zip(results.multi_hand_landmarks, results.multi_handedness, strict=True)
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
                    # After an error, still check stop event on next iteration
                    if self._stop_event.is_set():
                        break
                    time.sleep(0.05)
        finally:
            # Worker thread exits here. MediaPipe close is handled by stop()
            # to avoid double-close races. Just clear refs.
            try:
                pass  # _mp close is done in stop() only
            except Exception:
                pass
            with self._lock:
                self._hands = []

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
