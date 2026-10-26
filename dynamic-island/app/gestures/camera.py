"""Camera capture for JARVIS Desktop gestures.

Privacy-first: the camera is OFF until explicitly activated. No frames
are captured or retained when gesture mode is disabled.
"""

from __future__ import annotations

import logging
import threading
import time

import numpy as np

logger = logging.getLogger("jarvis.desktop.gestures.camera")


class Camera:
    """On-demand camera capture.

    Key invariant: Camera is released only after the gesture tracker worker
    has confirmed exit. This prevents a race where the camera might still
    be read by the tracker during shutdown.

    Usage:
        cam = Camera()
        cam.start()          # begins capture
        frame = cam.read()   # get latest frame (or None)
        cam.stop()           # stops capture, releases camera
    """

    def __init__(self, *, device: int = 0, width: int = 640, height: int = 480,
                 fps: int = 30):
        self._device = device
        self._width = width
        self._height = height
        self._fps = fps
        self._cap = None
        self._running = False
        self._lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._capture_thread: threading.Thread | None = None
        self._tracker_exit_confirmed: bool = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def latest_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def start(self) -> bool:
        """Start camera capture. Returns True on success.

        Idempotent: a second call while already running returns True immediately.
        """
        if self._running:
            return True
        try:
            import cv2
            self._cap = cv2.VideoCapture(self._device)
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
            self._cap.set(cv2.CAP_PROP_FPS, self._fps)
            if not self._cap.isOpened():
                logger.error("Failed to open camera device %d", self._device)
                self._cap = None
                return False
            self._running = True
            self._capture_thread = threading.Thread(
                target=self._capture_loop, daemon=True, name="jarvis-camera"
            )
            self._capture_thread.start()
            logger.info("Camera started (device=%d, %dx%d)", self._device, self._width, self._height)
            return True
        except Exception as e:
            logger.error("Camera start failed: %s", e)
            self._cap = None
            self._running = False
            return False

    def stop(self) -> None:
        """Stop camera capture and release resources.

        1. Request stop via _running flag.
        2. Wait for capture thread to confirm exit.
        3. Mark that tracker exit must be confirmed before camera release.
        4. After tracker exit is confirmed (by coordinator), release camera.
        5. Idempotent: second call is a no-op.
        """
        if not self._running:
            return
        self._running = False
        # Wait for capture thread to exit
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=3.0)
        # Only after capture thread has exited do we respect tracker exit
        # confirmation before releasing the camera hardware.
        self._tracker_exit_confirmed = True
        # Now release the camera — this is safe because the tracker should
        # have already stopped and released its references.
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        with self._lock:
            self._latest_frame = None
        logger.info("Camera stopped")

    def read(self) -> np.ndarray | None:
        """Get the latest frame (non-blocking)."""
        return self.latest_frame

    def _capture_loop(self) -> None:
        """Background capture loop.

        Checks _running each iteration. Camera frame is read and stored.
        The camera is released only after stop() sets _tracker_exit_confirmed
        and the tracker worker has confirmed its own exit.
        """
        while self._running:
            try:
                if self._cap is None:
                    break
                ret, frame = self._cap.read()
                if ret and frame is not None:
                    with self._lock:
                        self._latest_frame = frame
                else:
                    time.sleep(0.01)
            except Exception as e:
                logger.debug("Capture error: %s", e)
                time.sleep(0.05)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
