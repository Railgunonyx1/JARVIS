"""Stream Manager — priority-based audio buffer and streaming pipeline for TTS output."""

import heapq
import logging
import threading
from typing import Optional

logger = logging.getLogger("jarvis.voice_engine.stream_manager")

_instance: Optional["StreamManager"] = None
_lock = threading.Lock()


class AudioBuffer:
    """Thread-safe priority buffer for audio chunks. Higher priority = dequeued first.

    Uses heapq min-heap with negated priorities so the highest-priority chunk
    is always at heap[0].  When the buffer is at capacity the *lowest*-priority
    chunk is evicted to make room for a higher-priority incoming chunk.
    """

    def __init__(self, max_chunks: int = 50):
        self._max_chunks = max_chunks
        self._heap: list[tuple[int, int, bytes]] = []
        self._counter = 0
        self._lock = threading.Lock()

    def push(self, chunk: bytes, priority: int = 0) -> bool:
        """Add a chunk with a given priority. Returns False if rejected."""
        with self._lock:
            neg = -priority

            if len(self._heap) >= self._max_chunks:
                if not self._heap:
                    return False
                # heap[0] is the highest-priority item (smallest neg value).
                # The worst item has the *largest* neg value — find and evict it.
                worst_idx = max(range(len(self._heap)), key=lambda i: self._heap[i][0])
                worst_neg = self._heap[worst_idx][0]
                if neg >= worst_neg:
                    logger.debug(
                        "Dropping chunk with priority %d (worst=%d)",
                        priority, -worst_neg,
                    )
                    return False
                del self._heap[worst_idx]
                heapq.heapify(self._heap)

            self._counter += 1
            heapq.heappush(self._heap, (neg, self._counter, chunk))
            return True

    def pop(self) -> bytes | None:
        """Remove and return the highest-priority chunk, or None if empty."""
        with self._lock:
            if not self._heap:
                return None
            _, _, chunk = heapq.heappop(self._heap)
            return chunk

    def peek(self) -> bytes | None:
        """Return the highest-priority chunk without removing it."""
        with self._lock:
            if not self._heap:
                return None
            return self._heap[0][2]

    def flush(self) -> list[bytes]:
        """Return all chunks in priority order and clear the buffer."""
        with self._lock:
            chunks = []
            while self._heap:
                _, _, chunk = heapq.heappop(self._heap)
                chunks.append(chunk)
            return chunks

    def size(self) -> int:
        with self._lock:
            return len(self._heap)

    def clear(self) -> None:
        with self._lock:
            self._heap.clear()

    @property
    def capacity(self) -> int:
        return self._max_chunks


class StreamManager:
    """Manages audio streaming pipeline with configurable buffers."""

    def __init__(self):
        self._global_buffer: AudioBuffer = AudioBuffer(max_chunks=50)
        self._lock = threading.Lock()

    def create_buffer(self, max_chunks: int = 50) -> AudioBuffer:
        """Create a new isolated AudioBuffer instance."""
        return AudioBuffer(max_chunks=max_chunks)

    def get_global_buffer(self) -> AudioBuffer:
        """Return the shared global AudioBuffer."""
        return self._global_buffer


def get_stream_manager() -> StreamManager:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = StreamManager()
    return _instance
