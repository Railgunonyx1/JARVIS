"""Compression Engine — auto-selecting data compression (zlib/gzip/lz4)."""

import zlib
import gzip
import threading
import logging
from typing import Optional

logger = logging.getLogger("jarvis.performance_engine.compression")

try:
    import lz4.frame as _lz4_frame
    import lz4.block as _lz4_block

    _HAS_LZ4 = True
except ImportError:
    _HAS_LZ4 = False

# Compression format tags (first byte) so we know how to decompress.
_TAG_ZLIB = b"\x01"
_TAG_GZIP = b"\x02"
_TAG_LZ4 = b"\x03"
_TAG_NONE = b"\x00"


class CompressionEngine:
    """Compresses / decompresses data using the best available algorithm.

    Internally picks the algorithm that yields the smallest output. On
    decompression the stored tag selects the correct decoder automatically.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total_compressed: int = 0
        self._total_original: int = 0
        self._total_bytes_compressed: int = 0

    # ------------------------------------------------------------------
    # Bytes API
    # ------------------------------------------------------------------

    def compress(self, data: bytes) -> bytes:
        """Compress raw bytes, auto-selecting the best algorithm."""
        if not data:
            return _TAG_NONE

        best: Optional[bytes] = None
        best_len = len(data) + 1

        # Always available
        for tag, compressed in (
            (_TAG_ZLIB, zlib.compress(data, level=6)),
            (_TAG_GZIP, gzip.compress(data, compresslevel=6)),
        ):
            if len(compressed) < best_len:
                best = tag + compressed
                best_len = len(compressed)

        # LZ4 if available
        if _HAS_LZ4:
            try:
                lz4_compressed = _lz4_frame.compress(data)
                if len(lz4_compressed) < best_len:
                    best = _TAG_LZ4 + lz4_compressed
                    best_len = len(lz4_compressed)
            except Exception:
                pass

        result = best if best is not None else _TAG_ZLIB + zlib.compress(data, level=6)

        with self._lock:
            self._total_original += len(data)
            self._total_bytes_compressed += len(result) - 1  # subtract tag byte
            self._total_compressed += 1

        return result

    def decompress(self, data: bytes) -> bytes:
        """Decompress data previously compressed by :meth:`compress`."""
        if not data:
            return b""

        tag = data[:1]
        payload = data[1:]

        if tag == _TAG_ZLIB:
            return zlib.decompress(payload)
        if tag == _TAG_GZIP:
            return gzip.decompress(payload)
        if tag == _TAG_LZ4:
            if not _HAS_LZ4:
                raise RuntimeError("lz4 is not installed; cannot decompress lz4 data")
            return _lz4_frame.decompress(payload)
        if tag == _TAG_NONE:
            return b""
        raise ValueError(f"Unknown compression tag: {tag!r}")

    # ------------------------------------------------------------------
    # Text convenience
    # ------------------------------------------------------------------

    def compress_text(self, text: str) -> bytes:
        """Compress a UTF-8 string."""
        return self.compress(text.encode("utf-8"))

    def decompress_text(self, data: bytes) -> str:
        """Decompress back to a UTF-8 string."""
        return self.decompress(data).decode("utf-8")

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return cumulative compression statistics."""
        with self._lock:
            ratio = (
                self._total_bytes_compressed / self._total_original
                if self._total_original > 0
                else 0.0
            )
            return {
                "total_compressed": self._total_compressed,
                "total_original": self._total_original,
                "total_compressed_bytes": self._total_bytes_compressed,
                "ratio": round(ratio, 4),
                "lz4_available": _HAS_LZ4,
            }

    def reset_stats(self) -> None:
        """Reset statistics counters."""
        with self._lock:
            self._total_compressed = 0
            self._total_original = 0
            self._total_bytes_compressed = 0


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_compression_engine: Optional[CompressionEngine] = None
_compression_lock = threading.Lock()


def get_compression_engine() -> CompressionEngine:
    global _compression_engine
    if _compression_engine is None:
        with _compression_lock:
            if _compression_engine is None:
                _compression_engine = CompressionEngine()
    return _compression_engine
