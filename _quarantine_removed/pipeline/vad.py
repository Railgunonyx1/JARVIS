"""Voice Activity Detection — energy-based speech segment detection."""

import logging
import time
from collections import deque

import numpy as np

logger = logging.getLogger("jarvis.pipeline.vad")


class VoiceActivityDetector:
    def __init__(self, config: dict):
        cfg = config.get("vad", {})
        self._threshold = cfg.get("energy_threshold", 300)
        self._silence_ms = cfg.get("silence_duration_ms", 800)
        self._min_speech_ms = cfg.get("min_speech_duration_ms", 200)
        self._speaking = False
        self._speech_start = 0.0
        self._last_speech = 0.0
        self._energy_hist = deque(maxlen=50)
        self._calibrated = False

    def process_frame(self, audio_frame: np.ndarray, timestamp: float | None = None) -> dict:
        ts = timestamp or time.time()
        energy = self._compute_energy(audio_frame)
        self._energy_hist.append(energy)

        if len(self._energy_hist) >= 20 and not self._calibrated:
            self._calibrate()

        is_speech = energy > self._threshold
        result = {"energy": energy, "threshold": self._threshold, "is_speech": is_speech, "speech_active": self._speaking, "speech_ended": False}

        if is_speech:
            if not self._speaking:
                self._speaking = True
                self._speech_start = ts
                result["speech_started"] = True
            self._last_speech = ts
        elif self._speaking:
            silence_ms = (ts - self._last_speech) * 1000
            if silence_ms >= self._silence_ms:
                duration_ms = (ts - self._speech_start) * 1000
                result["speech_ended"] = True
                result["speech_duration_ms"] = duration_ms if duration_ms >= self._min_speech_ms else 0
                self._speaking = False
        return result

    def _compute_energy(self, frame: np.ndarray) -> float:
        if frame.size == 0:
            return 0.0
        f = frame.astype(np.float32)
        if np.abs(f).max() > 1.0:
            f /= 32768.0
        return float(np.sqrt(np.mean(f ** 2)) * 1000)

    def _calibrate(self):
        energies = list(self._energy_hist)
        self._threshold = max(np.mean(energies) + 2.5 * np.std(energies), 50)
        self._calibrated = True
        logger.info("VAD calibrated: threshold=%.1f", self._threshold)

    def reset(self):
        self._speaking = False
        self._speech_start = 0
        self._last_speech = 0
