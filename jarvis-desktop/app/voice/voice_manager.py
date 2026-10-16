"""Voice manager — push-to-talk coordinator for JARVIS Desktop.

Manages the full voice loop:
  Mic → STT → JARVIS Agent → TTS → Audio output

The microphone is never always-listening. Push-to-talk starts capture
on demand and stops immediately after transcription.
"""

from __future__ import annotations

import logging
import threading
import time
from enum import StrEnum
from typing import Callable

from app.voice.stt import STTManager, STTResult
from app.voice.tts import TTSEngine

logger = logging.getLogger("jarvis.desktop.voice.manager")


class VoiceState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


class VoiceManager:
    """Coordinates STT, agent interaction, and TTS.

    Usage:
        vm = VoiceManager(agent_backend=backend)
        vm.start_listening()   # push-to-talk
        vm.stop_speaking()     # interrupt TTS
    """

    def __init__(self, *, agent_backend=None,
                 on_state_change: Callable[[VoiceState], None] | None = None,
                 on_transcription: Callable[[str], None] | None = None,
                 on_response: Callable[[str], None] | None = None,
                 prefer_local_stt: bool = True,
                 use_kokoro_tts: bool = True,
                 voice: str = "",
                 speed: float = 1.0):
        self._backend = agent_backend
        self._on_state = on_state_change
        self._on_transcription = on_transcription
        self._on_response = on_response

        self._state = VoiceState.IDLE
        self._state_lock = threading.Lock()
        self._speaking_lock = threading.Lock()
        self._stop_speaking = threading.Event()

        self._stt = STTManager(prefer_local=prefer_local_stt)
        self._tts = TTSEngine(voice=voice, speed=speed, use_kokoro=use_kokoro_tts)

        self._tts_thread: threading.Thread | None = None

    @property
    def state(self) -> VoiceState:
        with self._state_lock:
            return self._state

    @property
    def is_listening(self) -> bool:
        return self.state == VoiceState.LISTENING

    @property
    def is_speaking(self) -> bool:
        return self.state == VoiceState.SPEAKING

    @property
    def stt_engine(self) -> str:
        return self._stt.active_engine

    @property
    def tts_engine(self) -> str:
        return self._tts.engine_name

    def _set_state(self, state: VoiceState) -> None:
        with self._state_lock:
            self._state = state
        if self._on_state:
            try:
                self._on_state(state)
            except Exception:
                pass

    def warmup(self) -> None:
        """Pre-load models in background."""
        self._stt.warmup()
        self._tts.warmup()

    def start_listening(self) -> None:
        """Start push-to-talk recording."""
        if self.state != VoiceState.IDLE:
            return
        self._set_state(VoiceState.LISTENING)

        def _record():
            try:
                result = self._stt.record_and_transcribe(duration=5.0)
                self._set_state(VoiceState.TRANSCRIBING)
                if result and result.text:
                    if self._on_transcription:
                        self._on_transcription(result.text)
                    self._send_to_agent(result.text)
                else:
                    self._set_state(VoiceState.IDLE)
            except Exception as e:
                logger.exception("Recording failed")
                self._set_state(VoiceState.ERROR)
                if self._on_response:
                    self._on_response(f"[Voice error: {str(e)[:100]}]")

        threading.Thread(target=_record, daemon=True, name="jarvis-voice-record").start()

    def stop_listening(self) -> None:
        """Stop recording early (user released push-to-talk)."""
        if self.state == VoiceState.LISTENING:
            # The recording loop checks state; we just transition
            self._set_state(VoiceState.TRANSCRIBING)

    def _send_to_agent(self, text: str) -> None:
        """Send transcribed text to the agent backend."""
        if not self._backend:
            self._set_state(VoiceState.ERROR)
            return

        self._set_state(VoiceState.THINKING)

        def _run():
            try:
                self._backend.send_message(text)
            except Exception as e:
                logger.exception("Agent send failed")
                self._set_state(VoiceState.ERROR)

        threading.Thread(target=_run, daemon=True, name="jarvis-voice-agent").start()

    def speak(self, text: str) -> None:
        """Synthesize and play TTS (non-blocking)."""
        if not text or not text.strip():
            return
        self._set_state(VoiceState.SPEAKING)
        self._stop_speaking.clear()

        def _speak():
            try:
                self._tts.play(text, block=False)
                # Wait for playback to finish (poll state)
                while not self._stop_speaking.is_set():
                    time.sleep(0.1)
                self._set_state(VoiceState.IDLE)
            except Exception as e:
                logger.warning("TTS playback failed: %s", e)
                self._set_state(VoiceState.IDLE)

        self._tts_thread = threading.Thread(target=_speak, daemon=True, name="jarvis-voice-tts")
        self._tts_thread.start()

    def stop_speaking(self) -> None:
        """Interrupt TTS playback."""
        self._stop_speaking.set()
        self._set_state(VoiceState.IDLE)

    def toggle_listening(self) -> None:
        """Toggle push-to-talk on/off."""
        if self.state == VoiceState.IDLE:
            self.start_listening()
        elif self.state == VoiceState.LISTENING:
            self.stop_listening()

    def get_status(self) -> dict:
        """Return current voice system status."""
        return {
            "state": self.state.value,
            "stt_engine": self.stt_engine,
            "tts_engine": self.tts_engine,
            "listening": self.is_listening,
            "speaking": self.is_speaking,
        }
