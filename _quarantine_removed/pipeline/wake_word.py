"""Wake Word Detection — openWakeWord (local, always-on)."""

import logging
import time
from collections.abc import Callable

import numpy as np

logger = logging.getLogger("jarvis.pipeline.wake_word")


class WakeWordDetector:
    def __init__(self, config: dict, on_wake: Callable | None = None):
        cfg = config.get("wake_word", {})
        self._enabled = cfg.get("enabled", True)
        self._sensitivity = cfg.get("sensitivity", 0.5)
        self._on_wake = on_wake
        self._model = None
        self._last_activation = 0.0

    def _ensure_model(self):
        if self._model is None and self._enabled:
            try:
                from openwakeword import Model as OWWModel
                self._model = OWWModel(wakeword_models=["hey_jarvis"])
            except Exception as e:
                logger.error("openWakeWord load failed: %s", e)
                self._enabled = False

    def process_frame(self, audio_frame: np.ndarray) -> dict:
        if not self._enabled:
            return {"wake_detected": False, "enabled": False}
        self._ensure_model()
        if self._model is None:
            return {"wake_detected": False, "enabled": False}
        now = time.time()
        score = self._model.predict(audio_frame).get("hey_jarvis", 0.0)
        result = {"wake_detected": False, "score": score, "enabled": True}
        if score >= self._sensitivity and (now - self._last_activation) > 1.0:
            result["wake_detected"] = True
            self._last_activation = now
            if self._on_wake:
                try:
                    self._on_wake()
                except Exception as e:
                    logger.error("Wake callback error: %s", e)
        return result

    def reset(self):
        self._last_activation = 0
        if self._model:
            self._model.reset()
