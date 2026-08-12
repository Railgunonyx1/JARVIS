"""Speech-to-Text: Groq Whisper Large v3 (cloud) → faster-whisper tiny (local)."""

import io
import logging
import time
import wave

logger = logging.getLogger("jarvis.pipeline.stt")


class SpeechToText:
    """Two-tier STT: fast cloud transcription with local fallback."""

    def __init__(self, config: dict, api_keys: dict):
        self._config = config.get("stt", {})
        self._api_keys = api_keys
        self._groq_key = api_keys.get("groq", "")
        self._local_model = None
        self._groq_client = None  # Reuse client across requests

    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """Transcribe audio bytes to text. Cloud first, local fallback."""
        if self._groq_key:
            try:
                return await self._transcribe_groq(audio_data, sample_rate)
            except Exception as e:
                logger.warning("Groq STT failed, falling back to local: %s", e)

        try:
            return await self._transcribe_local(audio_data, sample_rate)
        except Exception as e:
            logger.error("Local STT also failed: %s", e)
            return ""

    def _get_groq_client(self):
        if self._groq_client is None:
            import groq
            self._groq_client = groq.Groq(api_key=self._groq_key)
        return self._groq_client

    async def _transcribe_groq(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """Transcribe via Groq Whisper API. Wraps raw PCM into proper WAV first."""
        client = self._get_groq_client()

        # Wrap raw int16 PCM in a proper WAV file
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)
        wav_bytes = wav_buffer.getvalue()

        start = time.time()
        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "audio.wav"

        result = await _run_sync(
            client.audio.transcriptions.create,
            model=self._config.get("groq_model", "whisper-large-v3"),
            file=audio_file,
        )
        latency = (time.time() - start) * 1000
        text = result.text.strip()
        logger.info("Groq STT: '%s' (%.0fms)", text[:50], latency)
        return text

    async def _transcribe_local(self, audio_data: bytes, sample_rate: int) -> str:
        """Transcribe via local faster-whisper model."""
        import numpy as np

        model = self._get_local_model()

        # Convert bytes to numpy array
        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        def _run() -> str:
            segments, info = model.transcribe(
                audio_np,
                language="en",
                beam_size=1,  # Fastest
                vad_filter=True,
            )
            return " ".join(seg.text.strip() for seg in segments)

        start = time.time()
        text = await _run_sync(_run)
        latency = (time.time() - start) * 1000
        logger.info("Local STT: '%s' (%.0fms)", text[:50], latency)
        return text.strip()

    def _get_local_model(self):
        """Lazy-load the local faster-whisper model."""
        if self._local_model is None:
            from faster_whisper import WhisperModel
            model_size = self._config.get("local_model", "tiny")
            logger.info("Loading faster-whisper model: %s", model_size)
            self._local_model = WhisperModel(model_size, device="cpu", compute_type="int8")
        return self._local_model


async def _run_sync(func, *args, **kwargs):
    """Run a synchronous function in a thread pool."""
    import asyncio
    return await asyncio.to_thread(func, *args, **kwargs)
