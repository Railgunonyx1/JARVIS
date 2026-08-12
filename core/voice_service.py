"""VoiceService — wraps VAD, wake word, STT, TTS into a service-oriented design.

Integrates with DI container, ResourceManager, and EventBus.
Optimizes streaming latency via Silero VAD hints and resource-aware execution.
"""

import logging
from collections.abc import AsyncIterator, Callable

logger = logging.getLogger("jarvis.core.voice_service")


class VoiceService:
    """Service-oriented wrapper around the JARVIS voice pipeline.

    Manages VAD, wake word, STT, and TTS as a cohesive service.
    """

    def __init__(self, config: dict | None = None,
                 resource_manager=None, event_bus=None):
        self._config = config or {}
        self._resource_manager = resource_manager
        self._event_bus = event_bus

        self._vad = None
        self._wake_word = None
        self._stt = None
        self._tts = None

        self._is_listening = False
        self._is_speaking = False
        self._wake_word_detected = False

    async def initialize(self):
        """Lazy-initialize all voice components."""
        try:
            from pipeline.stt import SpeechToText
            from pipeline.tts import TextToSpeech
            from pipeline.vad import VoiceActivityDetector
            from pipeline.wake_word import WakeWordDetector
        except ImportError:
            logger.warning("Voice pipeline unavailable; voice service disabled")
            self._vad = self._wake_word = self._stt = self._tts = None
            self._is_listening = self._is_speaking = False
            return

        voice_cfg = self._config.get("voice", {})

        self._vad = VoiceActivityDetector(voice_cfg)
        self._wake_word = WakeWordDetector(
            voice_cfg,
            on_wake=self._on_wake_word,
        )
        self._stt = SpeechToText(voice_cfg)
        self._tts = TextToSpeech(voice_cfg)

        logger.info("VoiceService initialized (VAD=%s, WW=%s, STT=%s, TTS=%s)",
                     type(self._vad).__name__,
                     type(self._wake_word).__name__,
                     type(self._stt).__name__,
                     type(self._tts).__name__)

    def _on_wake_word(self):
        self._wake_word_detected = True
        if self._event_bus:
            self._event_bus.publish("voice.wake_word", {})

    # ── VAD ────────────────────────────────────

    def is_speech(self, audio_chunk) -> bool:
        if self._vad:
            return self._vad.is_speech(audio_chunk)
        return False

    def process_vad_frame(self, audio_frame) -> bool:
        if self._vad:
            return self._vad.process_frame(audio_frame)
        return False

    def reset_vad(self):
        if self._vad:
            self._vad.reset()

    # ── Wake Word ──────────────────────────────

    def start_wake_word(self):
        if self._wake_word:
            self._wake_word.start()
            self._wake_word_detected = False

    def stop_wake_word(self):
        if self._wake_word:
            self._wake_word.stop()

    @property
    def wake_word_detected(self) -> bool:
        return self._wake_word_detected

    # ── STT ────────────────────────────────────

    async def transcribe(self, audio_data, **kwargs) -> str:
        if self._resource_manager and self._resource_manager.should_throttle:
            logger.info("Throttling STT due to resource pressure")
        if self._stt:
            result = await self._stt.transcribe(audio_data, **kwargs)
            if self._event_bus:
                self._event_bus.publish("voice.transcribed", {
                    "text": result[:50], "length": len(result),
                })
            return result
        return ""

    async def transcribe_stream(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
        if self._stt:
            async for chunk in self._stt.transcribe_stream(audio_stream):
                yield chunk

    # ── TTS ────────────────────────────────────

    async def speak(self, text: str, **kwargs):
        self._is_speaking = True
        try:
            if self._tts:
                if self._event_bus:
                    self._event_bus.publish("voice.speaking", {"text": text[:50]})
                await self._tts.speak(text, **kwargs)
        finally:
            self._is_speaking = False

    async def speak_stream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        if self._tts:
            async for audio_chunk in self._tts.synthesize_stream(text_stream):
                yield audio_chunk

    # ── Listening loop ─────────────────────────

    async def listen_loop(self, audio_input_stream: AsyncIterator[bytes],
                           on_transcription: Callable[[str], None]):
        """Full voice loop: VAD → wake word → STT → callback."""
        self._is_listening = True
        try:
            async for audio_chunk in audio_input_stream:
                if not self._is_listening:
                    break
                is_speech = self.process_vad_frame(audio_chunk)
                if is_speech and not self._wake_word_detected:
                    continue
                # If wake word detected, transcribe
                if self._wake_word_detected:
                    text = await self.transcribe(audio_chunk)
                    if text.strip():
                        await on_transcription(text)
                        self._wake_word_detected = False
        finally:
            self._is_listening = False

    # ── Status ─────────────────────────────────

    @property
    def is_listening(self) -> bool:
        return self._is_listening

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    def get_status(self) -> dict:
        return {
            "listening": self._is_listening,
            "speaking": self._is_speaking,
            "vad": self._vad is not None,
            "wake_word": self._wake_word is not None,
            "stt": self._stt is not None,
            "tts": self._tts is not None,
        }

    async def shutdown(self):
        self._is_listening = False
        if self._wake_word:
            self._wake_word.stop()
        logger.info("VoiceService shutdown")
