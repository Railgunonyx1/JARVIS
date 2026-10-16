"""TTS for JARVIS Desktop — wraps the existing Kokoro neural TTS.

Reuses the jbrowser-bridge voice module's Kokoro chain (Apache-2.0,
local ONNX, ~330MB model). Falls back to SAPI on Windows, edge-tts
on Linux if Kokoro is unavailable.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger("jarvis.desktop.voice.tts")

# Kokoro model cache location
KOKORO_CACHE = Path.home() / ".jarvis" / "kokoro"


class TTSEngine:
    """Text-to-speech engine with local Kokoro preference.

    Usage:
        tts = TTSEngine()
        audio_bytes, mime = tts.speak("Hello world")
        # play audio_bytes via sounddevice or save to file
    """

    def __init__(self, *, voice: str = "", speed: float = 1.0,
                 use_kokoro: bool = True, on_ready: Callable[[], None] | None = None):
        self._voice = voice or os.getenv("JARVIS_KOKORO_VOICE", "af_sarah")
        self._speed = max(0.5, min(2.0, speed))
        self._use_kokoro = use_kokoro
        self._on_ready = on_ready
        self._kokoro_ready = False
        self._engine_name = "none"

    @property
    def engine_name(self) -> str:
        return self._engine_name

    @property
    def is_ready(self) -> bool:
        return self._kokoro_ready or self._engine_name != "none"

    def warmup(self) -> None:
        """Pre-load the Kokoro model in the background."""
        if not self._use_kokoro:
            return
        import threading
        threading.Thread(target=self._warmup_kokoro, daemon=True).start()

    def _warmup_kokoro(self) -> None:
        try:
            import sys
            repo_root = Path(__file__).resolve().parents[3]
            bridge_path = repo_root / "jbrowser-bridge"
            if str(bridge_path) not in sys.path:
                sys.path.insert(0, str(bridge_path))
            from voice import tts_kokoro
            # Trigger model load
            tts_kokoro("warmup", voice=self._voice)
            self._kokoro_ready = True
            self._engine_name = "kokoro"
            if self._on_ready:
                self._on_ready()
            logger.info("Kokoro TTS ready (voice=%s)", self._voice)
        except Exception as e:
            logger.warning("Kokoro warmup failed: %s — will use fallback", e)
            self._kokoro_ready = False

    def speak(self, text: str) -> tuple[bytes, str]:
        """Synthesize speech. Returns (audio_bytes, mime_type).

        Tries Kokoro first, then falls back to edge-tts (Linux) or SAPI.
        """
        if not text or not text.strip():
            return b"", "audio/wav"

        text = text.strip()

        # Try Kokoro (local, preferred)
        if self._use_kokoro:
            try:
                result = self._speak_kokoro(text)
                if result:
                    return result
            except Exception as e:
                logger.debug("Kokoro speak failed: %s", e)

        # Fallback: edge-tts (Linux) or SAPI
        return self._speak_fallback(text)

    def _speak_kokoro(self, text: str) -> tuple[bytes, str] | None:
        import sys
        repo_root = Path(__file__).resolve().parents[3]
        bridge_path = repo_root / "jbrowser-bridge"
        if str(bridge_path) not in sys.path:
            sys.path.insert(0, str(bridge_path))
        from voice import tts_kokoro
        audio_bytes, mime = tts_kokoro(text, voice=self._voice, speed=self._speed)
        self._engine_name = "kokoro"
        return audio_bytes, mime

    def _speak_fallback(self, text: str) -> tuple[bytes, str]:
        """Fallback TTS: edge-tts on Linux, SAPI on Windows."""
        try:
            import sys
            repo_root = Path(__file__).resolve().parents[3]
            bridge_path = repo_root / "jbrowser-bridge"
            if str(bridge_path) not in sys.path:
                sys.path.insert(0, str(bridge_path))
            from voice import tts
            audio_bytes, mime, engine = tts(text, voice=self._voice, speed=self._speed)
            self._engine_name = engine
            return audio_bytes, mime
        except Exception as e:
            logger.warning("Fallback TTS failed: %s", e)
            return b"", "audio/wav"

    def speak_to_file(self, text: str, filepath: str | Path | None = None) -> Path | None:
        """Synthesize and save to a WAV file. Returns the path or None."""
        audio_bytes, mime = self.speak(text)
        if not audio_bytes:
            return None
        if filepath is None:
            filepath = Path(tempfile.gettempdir()) / f"jarvis_tts_{int(time.time())}.wav"
        else:
            filepath = Path(filepath)
        filepath.write_bytes(audio_bytes)
        return filepath

    def play(self, text: str, block: bool = False) -> None:
        """Synthesize and play audio immediately."""
        audio_bytes, mime = self.speak(text)
        if not audio_bytes:
            return
        self.play_bytes(audio_bytes, block=block)

    @staticmethod
    def play_bytes(audio_bytes: bytes, block: bool = False) -> None:
        """Play raw audio bytes via sounddevice."""
        try:
            import sounddevice as sd
            import numpy as np
            import io
            import wave

            # Parse WAV
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                frames = wf.readframes(wf.getnframes())
                rate = wf.getframerate()
                channels = wf.getnchannels()
                width = wf.getsampwidth()

            if width == 2:
                data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            elif width == 4:
                data = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
            else:
                data = np.frombuffer(frames, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0

            if channels > 1:
                data = data.reshape(-1, channels)

            sd.play(data, rate)
            if block:
                sd.wait()
        except Exception as e:
            logger.warning("Audio playback failed: %s", e)
