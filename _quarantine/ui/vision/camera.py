"""Threaded webcam capture for JARVIS MK-X Vision.

Pre-allocates buffer, runs capture in a background thread,
provides latest frame on demand with FPS counter.
"""

import logging
import queue
import threading
import time

import cv2
import numpy as np

logger = logging.getLogger("jarvis.vision.camera")


class Camera:
    """Threaded webcam capture. Reads frames in background, latest frame on demand."""

    def __init__(
        self,
        camera_id: int = 0,
        width: int = 640,
        height: int = 480,
        max_fps: int = 30,
        buffer_size: int = 2,
    ):
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self._target_fps = max_fps
        self._frame_interval = 1.0 / max_fps

        self._cap: cv2.VideoCapture | None = None
        self._frame_queue: queue.Queue = queue.Queue(maxsize=buffer_size)
        self._thread: threading.Thread | None = None
        self._running = False

        # FPS tracking
        self._fps = 0.0
        self._frame_count = 0
        self._fps_timer = time.time()

        # Latest frame + lock
        self._latest_frame: np.ndarray | None = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        """Open camera and start capture thread. Returns True if successful."""
        try:
            self._cap = cv2.VideoCapture(self.camera_id)
            if not self._cap.isOpened():
                logger.error("Cannot open camera %d", self.camera_id)
                return False

            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self._cap.set(cv2.CAP_PROP_FPS, self._target_fps)

            # Read actual resolution
            self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.info("Camera opened: %dx%d (id=%d)", self.width, self.height, self.camera_id)

            self._running = True
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()
            return True

        except Exception as e:
            logger.error("Camera start failed: %s", e)
            return False

    def stop(self):
        """Stop capture and release camera."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
            self._cap = None
        logger.info("Camera stopped")

    def read(self) -> np.ndarray | None:
        """Get the latest frame (horizontal flip applied for mirror view)."""
        with self._lock:
            frame = self._latest_frame
        if frame is not None:
            return cv2.flip(frame, 1)  # Mirror
        return None

    def read_raw(self) -> np.ndarray | None:
        """Get the latest frame without flipping."""
        with self._lock:
            return self._latest_frame

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def is_running(self) -> bool:
        return self._running and self._cap is not None and self._cap.isOpened()

    @property
    def resolution(self) -> tuple[int, int]:
        return (self.width, self.height)

    def _capture_loop(self):
        """Background thread: read frames, update latest."""
        while self._running and self._cap and self._cap.isOpened():
            start = time.time()

            ret, frame = self._cap.read()
            if not ret:
                logger.warning("Frame read failed, retrying...")
                async_sleep(CALLBACK_WAIT)  # replaced with CALLBACK_WAIT
                continue

            with self._lock:
                self._latest_frame = frame

            # FPS calculation
            self._frame_count += 1
            elapsed = time.time() - self._fps_timer
            if elapsed >= 1.0:
                self._fps = self._frame_count / elapsed
                self._frame_count = 0
                self._fps_timer = time.time()

            # Frame rate limiting
            elapsed = time.time() - start
            if elapsed < self._frame_interval:
                async_sleep(self._frame_interval - elapsed)  # replaced with frame interval sleep

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
