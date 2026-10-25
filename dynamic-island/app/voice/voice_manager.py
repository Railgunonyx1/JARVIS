"""Voice manager — push-to-talk coordinator for JARVIS Desktop.

Manages the full voice loop:
  Mic → STT → JARVIS Agent → TTS → Audio output

The microphone is never always-listening. Push-to-talk starts capture
on demand and stops immediately after transcription.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from enum import StrEnum

from app.voice.stt import STTManager
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
        self._stop_recording = threading.Event()

        self._stt = STTManager(prefer_local=prefer_local_stt)
        self._tts = TTSEngine(voice=voice, speed=speed, use_kokoro=use_kokoro_tts)

        self._tts_thread: threading.Thread | None = None
        self._record_thread: threading.Thread | None = None
        self._speak_thread: threading.Thread | None = None
        self._shutdown = False

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

    def shutdown(self) -> None:
        """Stop all voice activity, cancel pending work, and join workers.

        Must be called when disabling voice and during coordinator shutdown.
        After this returns, no microphone capture should remain active
        and no late transcription should be submitted.
        """
        if getattr(self, "_shutdown", False):
            self._stop_recording.set()
            self._stop_speaking.set()
            self._set_state(VoiceState.IDLE)
            return
        self._shutdown = True
        self._stop_recording.set()
        self._stop_speaking.set()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        # Join any known threads
        for t in (getattr(self, "_record_thread", None), getattr(self, "_speak_thread", None), getattr(self, "_tts_thread", None)):
            try:
                if t and getattr(t, "is_alive", lambda: False)():
                    t.join(timeout=3.0)
            except Exception:
                pass
        self._set_state(VoiceState.IDLE)

    def warmup(self) -> None:
        """Pre-load models in background."""
        self._stt.warmup()
        self._tts.warmup()

    def start_listening(self) -> None:
        """Start push-to-talk recording."""
        if self.state not in (VoiceState.IDLE, VoiceState.ERROR):
            return
        self._set_state(VoiceState.LISTENING)
        self._stop_recording.clear()

        def _record():
            try:
                if getattr(self, "_shutdown", False):
                    self._set_state(VoiceState.IDLE)
                    return
                result = self._stt.record_and_transcribe(duration=5.0,
                                                         stop_event=self._stop_recording)
                if getattr(self, "_shutdown", False):
                    self._set_state(VoiceState.IDLE)
                    return
                self._set_state(VoiceState.TRANSCRIBING)
                if result and result.text:
                    if getattr(self, "_shutdown", False):
                        self._set_state(VoiceState.IDLE)
                        return
                    if self._on_transcription:
                        self._on_transcription(result.text)
                    self._send_to_agent(result.text)
                else:
                    reason = getattr(result, "engine", "unknown") if result else "no-result"
                    logger.warning("No transcription result (reason=%s)", reason)
                    self._set_state(VoiceState.IDLE)
                    if self._on_response and reason and reason not in ("", "none"):
                        try:
                            self._on_response("[Voice: no speech detected or STT unavailable]")
                        except Exception:
                            pass
            except Exception as e:
                logger.exception("Recording failed")
                if getattr(self, "_shutdown", False):
                    self._set_state(VoiceState.IDLE)
                    return
                self._set_state(VoiceState.ERROR)
                if self._on_response:
                    self._on_response(f"[Voice error: {str(e)[:100]}]")

        self._record_thread = threading.Thread(target=_record, daemon=True, name="jarvis-voice-record")
        self._record_thread.start()

    def stop_listening(self) -> None:
        """Stop recording early (user released push-to-talk)."""
        if self.state == VoiceState.LISTENING:
            self._stop_recording.set()

    def _send_to_agent(self, text: str) -> None:
        """Send transcribed text to the agent backend."""
        if not self._backend:
            logger.warning("Voice: no backend available to send transcription")
            self._set_state(VoiceState.ERROR)
            if self._on_response:
                try:
                    self._on_response("[Voice: agent backend unavailable]")
                except Exception:
                    pass
            return

        self._set_state(VoiceState.THINKING)

        def _run():
            try:
                self._backend.send_message(text)
            except Exception:
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
                if getattr(self, "_shutdown", False):
                    self._set_state(VoiceState.IDLE)
                    return
                self._tts.play(text, block=True)
                # Only set IDLE if we weren't interrupted
                if not self._stop_speaking.is_set() and not getattr(self, "_shutdown", False):
                    self._set_state(VoiceState.IDLE)
            except Exception as e:
                logger.warning("TTS playback failed: %s", e)
                # Do NOT change state on failure - keep current state
                # so the conversation continues even if voice output fails

        self._tts_thread = threading.Thread(target=_speak, daemon=True, name="jarvis-voice-tts")
        self._speak_thread = self._tts_thread
        self._tts_thread.start()

    def stop_speaking(self) -> None:
        """Interrupt TTS playback."""
        self._stop_speaking.set()
        # Stop audio playback immediately
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
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
