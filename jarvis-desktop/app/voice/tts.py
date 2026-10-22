"""TTS for JARVIS Desktop — local Kokoro neural TTS with edge-tts fallback.

Uses kokoro_onnx directly (Apache-2.0, local ONNX, ~330MB model).
Falls back to edge-tts on Linux if Kokoro is unavailable.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

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
            from kokoro_onnx import Kokoro
            self._kokoro = Kokoro(
                str(KOKORO_CACHE / "kokoro-v1.0.onnx"),
                str(KOKORO_CACHE / "voices-v1.0.bin"),
            )
            self._kokoro_ready = True
            self._engine_name = "kokoro"
            if self._on_ready:
                self._on_ready()
            logger.info("Kokoro TTS ready (voice=%s)", self._voice)
        except Exception as e:
            logger.warning("Kokoro warmup failed: %s", e)
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
        if not hasattr(self, "_kokoro") or self._kokoro is None:
            return None
        import io
        import wave

        import numpy as np
        audio, sr = self._kokoro(text)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes((audio * 32767).astype(np.int16).tobytes())
        self._engine_name = "kokoro"
        return wav_buffer.getvalue(), "audio/wav"

    def _speak_fallback(self, text: str) -> tuple[bytes, str]:
        """Fallback TTS: edge-tts on Linux, SAPI on Windows."""
        import io
        import subprocess
        import tempfile

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name

            import shutil
            edge_cmd = shutil.which("edge-tts")
            if edge_cmd is None:
                venv_bin = Path(sys.executable).parent
                cand = venv_bin / "edge-tts"
                if cand.exists():
                    edge_cmd = str(cand)
            if edge_cmd is None:
                cmd = [sys.executable, "-m", "edge_tts"]
            else:
                cmd = [edge_cmd]
            cmd.extend(["--text", text, "--write-media", tmp_path])
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=30,
                check=False,
            )

            if result.returncode != 0 or not os.path.exists(tmp_path):
                logger.warning("edge-tts failed (rc=%s): %s",
                             result.returncode, result.stderr.decode()[:200])
                return b"", "audio/wav"

            # edge-tts produces MP3; decode to WAV for sounddevice
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_mp3(tmp_path)
                wav_buffer = io.BytesIO()
                audio.export(wav_buffer, format="wav")
                self._engine_name = "edge-tts"
                return wav_buffer.getvalue(), "audio/wav"
            except ImportError:
                # pydub unavailable; return raw MP3 and let the player handle it
                with open(tmp_path, "rb") as f:
                    mp3_data = f.read()
                self._engine_name = "edge-tts"
                return mp3_data, "audio/mpeg"
        except Exception as e:
            logger.warning("Fallback TTS failed: %s", e)
            return b"", "audio/wav"
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

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
        """Play raw audio bytes via sounddevice. Accepts WAV or MP3."""
        try:
            import io
            import wave

            import numpy as np
            import sounddevice as sd

            try:
                with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                    frames = wf.readframes(wf.getnframes())
                    rate = wf.getframerate()
                    channels = wf.getnchannels()
                    width = wf.getsampwidth()
            except wave.Error:
                # Not WAV — try MP3 via pydub
                from pydub import AudioSegment
                audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
                rate = audio.frame_rate
                channels = audio.channels
                data = np.array(audio.get_array_of_samples(), dtype=np.float32)
                if audio.sample_width == 2:
                    data = data / 32768.0
                elif audio.sample_width == 4:
                    data = data / 2147483648.0
                else:
                    data = data / 128.0 - 1.0
                if channels > 1:
                    data = data.reshape(-1, channels)
                sd.play(data, rate)
                if block:
                    sd.wait()
                return

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
