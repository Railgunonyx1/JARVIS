"""Text-to-Speech — Piper local (fast) + Edge-TTS cloud fallback.
Sentence-level streaming: split text, generate each sentence, yield immediately."""

import re
import time
import wave
import asyncio
import logging
import io as _io
from pathlib import Path
from typing import Optional, AsyncIterator
from functools import lru_cache

logger = logging.getLogger("jarvis.pipeline.tts")

_piper_available = None

# Sentences that fit in ~30 words for fast first-utterance latency
_MAX_SENTENCE_WORDS = 30

# Pre-cache these common greetings (bounded LRU to prevent memory leak)
_response_cache: dict[str, bytes] = {}
_CACHE_MAX_SIZE = 200


def _has_piper() -> bool:
    global _piper_available
    if _piper_available is None:
        try:
            import piper  # noqa: F401
            _piper_available = True
        except ImportError:
            _piper_available = False
    return _piper_available


def split_sentences(text: str) -> list[str]:
    """Split text into sentence-level chunks for streaming TTS.
    Each sentence boundary triggers a new chunk for fast first-utterance latency."""
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = []
    for s in raw:
        if s.strip():
            sentences.append(s.strip())
    return sentences if sentences else [text.strip()]


class TextToSpeech:
    def __init__(self, config: dict):
        cfg = config.get("tts", {})
        self._edge_cfg = config.get("edge", {})
        self._piper_cfg = config.get("piper", {})
        self._piper_model = None
        self._voice = self._edge_cfg.get("default_voice", "en-GB-RyanNeural")
        self._rate = self._edge_cfg.get("rate", "+0%")
        self._warmed_up = False

    async def warmup(self):
        """Pre-load Piper model so first real request is fast."""
        if self._warmed_up:
            return
        if _has_piper():
            try:
                self._get_piper_model()
                self._piper_model.synthesize("Hi.")
                self._warmed_up = True
                logger.info("TTS warmup complete (Piper)")
            except Exception as e:
                logger.warning("TTS warmup failed: %s", e)

    async def precache_deterministic(self):
        """Pre-generate audio for all deterministic responses.
        Eliminates TTS latency for greetings, time, exit, etc.
        Must be called after warmup().
        """
        from core.personality import (
            _GREETINGS, _HOW_ARE_YOU, _EXIT,
            TimeOfDay
        )

        responses = []
        # Greetings (all times × all variants)
        for tod in TimeOfDay:
            for g in _GREETINGS[tod]:
                responses.append(g)
        # How are you
        responses.extend(_HOW_ARE_YOU)
        # Exit
        responses.extend(_EXIT)
        # Fixed responses
        responses.extend([
            "Session cleared. Starting fresh.",
            "Configuration panel not yet available in MK-X.",
            "You're welcome.",
            "I don't have weather API access yet. Check weather manually for now.",
            "I can help with: time, date, memories, web search, opening apps, notes, reminders, and conversation. Try voice commands or type directly.",
            "I don't have any stored memories about you yet.",
            "What would you like me to remember?",
        ])

        logger.info("Pre-caching %d deterministic responses...", len(responses))
        start = time.time()
        # Limit concurrent synthesis to 4 (prevents thread storm on startup)
        sem = asyncio.Semaphore(4)
        async def _limited_synthesize(r):
            async with sem:
                return await self.synthesize(r)
        tasks = [_limited_synthesize(r) for r in responses]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        cached = sum(1 for r in results if isinstance(r, bytes) and r)
        elapsed = (time.time() - start) * 1000
        logger.info("Pre-cached %d/%d responses in %.0fms", cached, len(responses), elapsed)

    def cache_response(self, text: str, audio: bytes):
        """Cache audio for a deterministic response. Evicts oldest if full."""
        key = text.lower().strip()
        if len(_response_cache) >= _CACHE_MAX_SIZE:
            # Remove oldest entry (first key inserted)
            _response_cache.pop(next(iter(_response_cache)))
        _response_cache[key] = audio

    def get_cached(self, text: str) -> Optional[bytes]:
        """Check if audio is cached for this text."""
        return _response_cache.get(text.lower().strip())

    async def synthesize(self, text: str, output_path: Optional[str] = None) -> bytes:
        """Full synthesis — returns complete audio bytes. Checks cache first.
        Respects resource governor: skips synthesis under high load."""
        if not text.strip():
            return b""

        cached = self.get_cached(text)
        if cached:
            return cached

        # Resource governor: skip TTS under aggressive throttle
        try:
            from core.resource_governor import get_governor
            gov = get_governor()
            if gov.should_reduce_tts:
                logger.info("TTS skipped: resource governor throttle level %d", gov.throttle_level)
                return b""
        except Exception:
            pass

        audio = b""
        if _has_piper():
            try:
                audio = await self._piper(text, output_path)
            except Exception:
                pass

        if not audio:
            try:
                audio = await self._edge(text, output_path)
            except Exception as e:
                logger.error("TTS failed: %s", e)
                return b""

        # Cache the result for future instant lookups
        if audio:
            self.cache_response(text, audio)

        return audio

    async def synthesize_streaming(self, text: str) -> AsyncIterator[bytes]:
        """Split text into sentences, generate each with Piper, yield WAV chunks.

        Yields complete WAV byte sequences for each sentence.
        Browser plays each chunk as it arrives for near-instant first-utterance.
        """
        if not text.strip():
            return

        cached = self.get_cached(text)
        if cached:
            yield cached
            return

        sentences = split_sentences(text)

        if _has_piper() and self._piper_model:
            for sentence in sentences:
                try:
                    wav = await self._piper(sentence)
                    if wav:
                        yield wav
                        continue
                except Exception:
                    pass
                # Fallback for this sentence
                try:
                    wav = await self._edge(sentence)
                    if wav:
                        yield wav
                except Exception:
                    pass
        else:
            # Edge-TTS: stream full text as one chunk
            try:
                wav = await self._edge(text)
                if wav:
                    yield wav
            except Exception:
                pass

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Legacy streaming — yields raw audio chunks from Edge-TTS."""
        if not text.strip():
            return
        try:
            import edge_tts
            from security.redaction import redact_sensitive
            redacted = redact_sensitive(text)
            async for chunk in edge_tts.Communicate(redacted, self._voice, rate=self._rate).stream():
                if chunk["type"] == "audio" and chunk["data"]:
                    yield chunk["data"]
        except Exception as e:
            logger.error("Streaming TTS failed: %s", e)

    async def _edge(self, text: str, output_path: Optional[str] = None) -> bytes:
        import edge_tts
        from security.redaction import redact_sensitive
        redacted = redact_sensitive(text)
        start = time.time()
        chunks = bytearray()
        async for chunk in edge_tts.Communicate(redacted, self._voice, rate=self._rate).stream():
            if chunk["type"] == "audio":
                chunks.extend(chunk["data"])
        audio = bytes(chunks)
        logger.info("Edge TTS: %d bytes (%.0fms)", len(audio), (time.time() - start) * 1000)
        if output_path:
            Path(output_path).write_bytes(audio)
        return audio

    async def _piper(self, text: str, output_path: Optional[str] = None) -> bytes:
        def _synthesize():
            model = self._get_piper_model()
            start = time.time()
            chunks = list(model.synthesize(text))
            wav_buf = _io.BytesIO()
            with wave.open(wav_buf, "wb") as wf:
                wf.setnchannels(chunks[0].sample_channels)
                wf.setsampwidth(chunks[0].sample_width)
                wf.setframerate(chunks[0].sample_rate)
                for chunk in chunks:
                    wf.writeframes(chunk.audio_int16_bytes)
            wav = wav_buf.getvalue()
            logger.info("Piper: %d bytes (%.0fms)", len(wav), (time.time() - start) * 1000)
            return wav

        wav = await asyncio.to_thread(_synthesize)
        if output_path:
            Path(output_path).write_bytes(wav)
        return wav

    def _get_piper_model(self):
        if self._piper_model is None:
            import piper
            model_dir = Path(self._piper_cfg.get("model_dir", "~/.jarvis/models/piper")).expanduser()
            model_dir.mkdir(parents=True, exist_ok=True)
            onnx = list(model_dir.glob("*.onnx"))
            if not onnx:
                raise FileNotFoundError(f"No Piper models in {model_dir}")
            self._piper_model = piper.PiperVoice.load(str(onnx[0]))
        return self._piper_model
