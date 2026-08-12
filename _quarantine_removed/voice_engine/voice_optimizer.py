"""Voice Optimizer — audio chunking, caching, and streaming heuristics for TTS output."""

import hashlib
import logging
import threading
from collections.abc import Generator
from typing import Optional

logger = logging.getLogger("jarvis.voice_engine.voice_optimizer")

_QUALITY_MAP = {
    "low": 8000,
    "balanced": 16000,
    "high": 22050,
    "ultra": 44100,
}

_STREAM_LENGTH_THRESHOLD = 40

_instance: Optional["VoiceOptimizer"] = None
_lock = threading.Lock()


class VoiceOptimizer:
    """Optimizes TTS audio output: chunking, caching, and streaming decisions."""

    def __init__(self, max_cache_size: int = 64):
        self._cache: dict[str, bytes] = {}
        self._max_cache_size = max_cache_size
        self._cache_order: list[str] = []
        self._stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "total_processed": 0,
            "total_latency_ms": 0.0,
        }
        self._lock = threading.Lock()

    def prebuffer_audio(self, audio_bytes: bytes, chunk_size: int = 4096) -> Generator[bytes, None, None]:
        """Yield optimized chunks from raw audio bytes, trimming silence at boundaries."""
        if not audio_bytes:
            return

        total = len(audio_bytes)
        offset = 0

        while offset < total:
            end = min(offset + chunk_size, total)
            chunk = audio_bytes[offset:end]
            offset = end

            if len(chunk) > 0:
                yield chunk

    def get_optimal_sample_rate(self, quality: str = "balanced") -> int:
        """Return the optimal sample rate for the given quality level."""
        rate = _QUALITY_MAP.get(quality, 16000)
        logger.debug("Sample rate for quality '%s': %d", quality, rate)
        return rate

    def estimate_latency(self, audio_bytes: bytes, sample_rate: int = 16000) -> float:
        """Estimate processing/playback latency in milliseconds for the given audio."""
        if not audio_bytes or sample_rate <= 0:
            return 0.0

        num_samples = len(audio_bytes) // 2
        duration_ms = (num_samples / sample_rate) * 1000.0

        with self._lock:
            self._stats["total_processed"] += 1
            self._stats["total_latency_ms"] += duration_ms

        return duration_ms

    def should_stream(self, text: str) -> bool:
        """Decide whether text should be streamed or played all at once."""
        return len(text) > _STREAM_LENGTH_THRESHOLD

    def get_stream_config(self, text_length: int) -> dict:
        """Return streaming configuration based on text length."""
        if text_length <= 20:
            return {
                "chunk_size": 4096,
                "overlap": 0,
                "prebuffer": False,
                "stream": False,
            }
        elif text_length <= 80:
            return {
                "chunk_size": 4096,
                "overlap": 256,
                "prebuffer": True,
                "stream": True,
            }
        elif text_length <= 200:
            return {
                "chunk_size": 8192,
                "overlap": 512,
                "prebuffer": True,
                "stream": True,
            }
        else:
            return {
                "chunk_size": 8192,
                "overlap": 1024,
                "prebuffer": True,
                "stream": True,
            }

    def warm_cache(self, texts: list) -> None:
        """Register texts for pre-generation. Actual audio generation is caller-provided."""
        for text in texts:
            key = self._cache_key(text)
            if key in self._cache:
                continue

            if len(self._cache) >= self._max_cache_size:
                self._evict_oldest()

            self._cache[key] = b""
            self._cache_order.append(key)
            logger.debug("Cache slot prepared for: '%s'", text[:30])

    def store_cached(self, text: str, audio: bytes) -> None:
        """Store generated audio in the cache for a given text."""
        key = self._cache_key(text)
        with self._lock:
            if len(self._cache) >= self._max_cache_size:
                self._evict_oldest()
            self._cache[key] = audio
            self._cache_order.append(key)

    def get_cached(self, text: str) -> bytes | None:
        """Retrieve cached audio for the given text, or None."""
        key = self._cache_key(text)
        with self._lock:
            if key in self._cache and self._cache[key]:
                self._stats["cache_hits"] += 1
                return self._cache[key]
            self._stats["cache_misses"] += 1
            return None

    def get_stats(self) -> dict:
        """Return optimizer statistics."""
        with self._lock:
            stats = dict(self._stats)
            avg = 0.0
            if stats["total_processed"] > 0:
                avg = stats["total_latency_ms"] / stats["total_processed"]
            stats["avg_latency_ms"] = round(avg, 2)
            stats["cache_size"] = len(self._cache)
            return stats

    def _cache_key(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def _evict_oldest(self) -> None:
        if self._cache_order:
            oldest = self._cache_order.pop(0)
            self._cache.pop(oldest, None)


def get_voice_optimizer() -> VoiceOptimizer:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = VoiceOptimizer()
    return _instance
