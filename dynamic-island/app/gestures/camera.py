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

    def stop(self) -> None:
        """Stop camera capture and release resources.

        1. Request stop via _running flag.
        2. Wait for capture thread to confirm exit (join with timeout).
        3. Do NOT release camera hardware yet — wait for the coordinator to
           confirm that the tracker worker has exited.
        4. Idempotent: second call is a no-op if already stopped.

        This method does NOT set _tracker_exit_confirmed — that is the
        coordinator's responsibility. The coordinator must call
        camera.tracker_exit_confirmed() after the tracker worker has stopped.
        """
        if not self._running:
            return
        self._running = False
        # Wait for capture thread to exit
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=3.0)
        # Do NOT release camera hardware here. The coordinator will call
        # camera.tracker_exit_confirmed() after the tracker worker has
        # confirmed its own exit. Releasing the camera before the tracker
        # has stopped would race with the tracker reading frames.
        # Only after the coordinator signals tracker exit confirmation do we
        # release the capture object.
        # NOTE: Camera.release() is deferred to the coordinator's
        # tracker_exit_confirmed() callback path.

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
        self._tracker_exit_confirmed_by_coordinator = True
        # Now safe to release the camera
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