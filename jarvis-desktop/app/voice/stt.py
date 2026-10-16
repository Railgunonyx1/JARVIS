"""STT for JARVIS Desktop — whisper.cpp local transcription with cloud fallback.

Push-to-talk only: the microphone is never always-listening. Audio is
captured on demand, transcribed locally via whisper.cpp, and the mic
stops immediately after.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger("jarvis.desktop.voice.stt")

# whisper.cpp binary location (can be overridden)
WHISPER_CPP_PATH = os.getenv("JARVIS_WHISPER_CPP", "whisper-cli")
# Model size: tiny (75MB), base (142MB), small (466MB), medium (1.5GB)
WHISPER_MODEL = os.getenv("JARVIS_WHISPER_MODEL", "base")
WHISPER_MODEL_PATH = os.getenv("JARVIS_WHISPER_MODEL_PATH", "")

SAMPLE_RATE = 16000
RECORD_SECONDS_MAX = 30  # safety cap


class STTResult:
    """Result of a speech-to-text transcription."""
    def __init__(self, text: str, confidence: float = 0.0,
                 engine: str = "", duration_ms: float = 0.0):
        self.text = text
        self.confidence = confidence
        self.engine = engine
        self.duration_ms = duration_ms

    def __bool__(self) -> bool:
        return bool(self.text.strip())


class WhisperSTT:
    """Local whisper.cpp STT engine.

    Captures audio from the default microphone, saves to a temp WAV,
    and transcribes via whisper-cli subprocess. No Python whisper
    dependency needed — just the whisper.cpp binary.
    """

    def __init__(self, *, model_size: str = WHISPER_MODEL,
                 model_path: str = WHISPER_MODEL_PATH,
                 language: str = "en",
                 on_ready: Callable[[], None] | None = None):
        self._model_size = model_size
        self._model_path = model_path or str(
            Path.home() / ".jarvis" / "whisper" / f"ggml-{model_size}.bin"
        )
        self._language = language
        self._on_ready = on_ready
        self._ready = False
        self._binary = WHISPER_CPP_PATH

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def binary(self) -> str:
        return self._binary

    def check_binary(self) -> bool:
        """Check if whisper-cli is available."""
        try:
            result = subprocess.run(
                [self._binary, "--help"],
                capture_output=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def warmup(self) -> None:
        """Check binary availability in background."""
        import threading
        threading.Thread(target=self._warmup_check, daemon=True).start()

    def _warmup_check(self) -> None:
        if self.check_binary():
            self._ready = True
            if self._on_ready:
                self._on_ready()
            logger.info("whisper.cpp STT ready (model=%s)", self._model_size)
        else:
            logger.warning("whisper.cpp not found at %s — STT will use cloud fallback", self._binary)

    def transcribe(self, audio_bytes: bytes, mime: str = "audio/wav") -> STTResult:
        """Transcribe audio bytes. Returns STTResult."""
        start = time.time()
        if not audio_bytes:
            return STTResult("", 0.0, "none", 0.0)

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        try:
            return self._transcribe_file(temp_path, start)
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    def _transcribe_file(self, filepath: str, start_time: float) -> STTResult:
        """Run whisper-cli on a WAV file."""
        if not self.check_binary():
            return STTResult("", 0.0, "unavailable", 0.0)

        cmd = [
            self._binary,
            "-m", self._model_path,
            "-f", filepath,
            "-l", self._language,
            "--no-timestamps",
            "-otxt",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, timeout=60,
            text=True,
            cwd=str(Path(filepath).parent),
            env={**os.environ, "GGML_CUDA_NO_PINNED": "1"},
            )
            duration_ms = (time.time() - start_time) * 1000
            if result.returncode == 0:
                text = result.stdout.strip()
                return STTResult(text, 0.0, "whisper.cpp", duration_ms)
            else:
                logger.warning("whisper-cli failed: %s", result.stderr[:200])
                return STTResult("", 0.0, "whisper.cpp", duration_ms)
        except subprocess.TimeoutExpired:
            logger.warning("whisper-cli timed out")
            return STTResult("", 0.0, "whisper.cpp", (time.time() - start_time) * 1000)
        except Exception as e:
            logger.warning("whisper-cli error: %s", e)
            return STTResult("", 0.0, "whisper.cpp", (time.time() - start_time) * 1000)

    def record_and_transcribe(self, duration: float = 5.0,
                              silence_timeout: float = 2.0) -> STTResult:
        """Record from microphone and transcribe.

        Args:
            duration: Max recording duration in seconds.
            silence_timeout: Stop after this many seconds of silence.
        """
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            logger.warning("sounddevice not available — cannot record")
            return STTResult("", 0.0, "no-sounddevice", 0.0)

        duration = min(duration, RECORD_SECONDS_MAX)
        frames = []
        start = time.time()
        recording = True

        def callback(indata, frame_count, time_info, status):
            if recording:
                frames.append(indata.copy())

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                dtype=np.float32, callback=callback):
                logger.info("Recording... (max %.0fs)", duration)
                while recording and (time.time() - start) < duration:
                    time.sleep(0.05)
                    # Simple VAD: check if audio is silent
                    if frames and len(frames) > 10:
                        recent = np.concatenate(frames[-10:])
                        if np.abs(recent).max() < 0.01:
                            break
        except Exception as e:
            logger.warning("Recording failed: %s", e)
            return STTResult("", 0.0, "record-error", 0.0)

        if not frames:
            return STTResult("", 0.0, "no-audio", 0.0)

        # Convert to WAV
        import io
        import wave
        audio = np.concatenate(frames)
        # Convert float32 to int16
        audio_int16 = (audio * 32767).astype(np.int16)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_int16.tobytes())

        return self.transcribe(wav_buffer.getvalue(), "audio/wav")


class CloudSTT:
    """Cloud STT fallback using the existing ElevenLabs Scribe."""

    def __init__(self):
        self._engine_name = "elevenlabs"

    def transcribe(self, audio_bytes: bytes, mime: str = "audio/wav") -> STTResult:
        start = time.time()
        try:
            import sys
            repo_root = Path(__file__).resolve().parents[3]
            bridge_path = repo_root / "jbrowser-bridge"
            if str(bridge_path) not in sys.path:
                sys.path.insert(0, str(bridge_path))
            from voice import stt_bytes
            text = stt_bytes(audio_bytes, "audio.wav")
            duration_ms = (time.time() - start) * 1000
            return STTResult(text, 0.0, self._engine_name, duration_ms)
        except Exception as e:
            logger.warning("Cloud STT failed: %s", e)
            return STTResult("", 0.0, self._engine_name, (time.time() - start) * 1000)


class STTManager:
    """STT coordinator: tries local whisper.cpp, falls back to cloud."""

    def __init__(self, *, prefer_local: bool = True,
                 on_ready: Callable[[], None] | None = None):
        self._prefer_local = prefer_local
        self._on_ready = on_ready
        self._local = WhisperSTT(on_ready=on_ready) if prefer_local else None
        self._cloud = CloudSTT()
        self._active_engine = "none"

    @property
    def active_engine(self) -> str:
        return self._active_engine

    def warmup(self) -> None:
        if self._local:
            self._local.warmup()

    def transcribe(self, audio_bytes: bytes, mime: str = "audio/wav") -> STTResult:
        """Transcribe audio, trying local first."""
        if self._prefer_local and self._local and self._local.is_ready:
            result = self._local.transcribe(audio_bytes, mime)
            if result:
                self._active_engine = "whisper.cpp"
                return result

        # Fallback to cloud
        result = self._cloud.transcribe(audio_bytes, mime)
        if result:
            self._active_engine = "elevenlabs"
        return result

    def record_and_transcribe(self, duration: float = 5.0) -> STTResult:
        """Record and transcribe, trying local first."""
        if self._prefer_local and self._local and self._local.is_ready:
            result = self._local.record_and_transcribe(duration)
            if result:
                self._active_engine = "whisper.cpp"
                return result

        # Cloud fallback: record then transcribe
        if self._local:
            result = self._local.record_and_transcribe(duration)
            if result:
                self._active_engine = "whisper.cpp"
                return result

        return STTResult("", 0.0, "unavailable", 0.0)
