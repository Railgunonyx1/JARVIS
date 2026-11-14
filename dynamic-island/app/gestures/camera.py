"""Camera capture for JARVIS Desktop gestures.

Privacy-first: the camera is OFF until explicitly activated. No frames
are captured or retained when gesture mode is disabled.

Shutdown ordering invariant: The camera is released only AFTER the gesture
tracker worker has confirmed exit. This prevents a race where the camera
might still be read by the tracker during shutdown. Camera.stop() does NOT
set _tracker_exit_confirmed — the coordinator owns that confirmation.
"""

from __future__ import annotations

import logging
import threading

import numpy as np

logger = logging.getLogger("jarvis.desktop.gestures.camera")


class Camera:
    """On-demand camera capture.

    Key invariant: Camera is released only after the gesture tracker worker
    has confirmed exit. This prevents a race where the camera might still
    be read by the tracker during shutdown.

    The _tracker_exit_confirmed flag is owned by the coordinator, not the
    camera. Camera.stop() releases the capture after being notified that the
    tracker has exited.

    Usage:
        cam = Camera()
        cam.start()          # begins capture
        frame = cam.read()   # get latest frame (or None)
        cam.stop()           # stops capture, releases camera
    """

    def __init__(self, *, device: int = 0, width: int = 640, height: int = 480, fps: int = 30):
        self._device = device
        self._width = width
        self._height = height
        self._fps = fps
        self._cap = None
        self._running = False
        self._lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._capture_thread: threading.Thread | None = None
        # _tracker_exit_confirmed is NOT set here — the coordinator owns this.
        # It will be set by the coordinator after the tracker thread has exited.
        self._tracker_exit_confirmed_by_coordinator = False

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

    def stop(self) -> bool:
        """Request capture shutdown and report whether its worker has exited.

        Camera hardware is deliberately not released here. The coordinator
        must first stop the tracker, then wait for both worker threads to exit,
        and only then call tracker_exit_confirmed().
        """
        self._running = False
        thread = self._capture_thread
        if thread is not None and thread.is_alive():
            if thread is threading.current_thread():
                return False
            thread.join(timeout=3.0)
        return thread is None or not thread.is_alive()

    def read(self) -> np.ndarray | None:
        """Get the latest frame (non-blocking)."""
        return self.latest_frame

    def _capture_loop(self) -> None:
        """Background capture loop.

        Checks _running each iteration. Camera frame is read and stored.
        The camera is released only after the coordinator has confirmed
        that the tracker worker has exited.
        """
        import time as _time
        while self._running:
            try:
                if self._cap is None:
                    break
                ret, frame = self._cap.read()
                if ret and frame is not None:
                    with self._lock:
                        self._latest_frame = frame
                else:
                    _time.sleep(0.01)
            except Exception as e:
                logger.debug("Capture error: %s", e)
                _time.sleep(0.05)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()
        # Do NOT set _tracker_exit_confirmed here — coordinator owns it.
        # The coordinator must call camera.tracker_exit_confirmed() after
        # the tracker worker has exited.
        return False

    # ── Coordinator notification ──────────────────────────────────────

    def tracker_exit_confirmed(self) -> None:
        """Signal from the coordinator that the tracker worker has exited.

        The coordinator should call this after the HandTracker.stop() has
        confirmed the worker thread has exited. After this call, it is safe
        to release the camera hardware.

        This separates the ownership: the tracker confirms its own exit,
        then the coordinator confirms it to the camera, then the camera
        releases the hardware.
        """
        capture_thread = self._capture_thread
        if capture_thread is not None and capture_thread.is_alive():
            raise RuntimeError(
                "Cannot release camera while the capture worker is still running"
            )
        self._tracker_exit_confirmed_by_coordinator = True
        self._release_camera()

    def _release_camera(self) -> None:
        """Release the camera capture hardware.

        Safe to call only after tracker_exit_confirmed() has been called.
        """
        with self._lock:
            self._latest_frame = None
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        logger.info("Camera hardware released (tracker exit confirmed)")


# Convenience function for the coordinator to signal camera release
def signal_camera_tracker_exit_confirmed(camera: Camera) -> None:
    """Call from the coordinator after HandTracker.stop() confirms worker exit.

    This separates ownership: the tracker confirms its exit, then the
    coordinator signals the camera that it's safe to release hardware.
    """
    camera.tracker_exit_confirmed()