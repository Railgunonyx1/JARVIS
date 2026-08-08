"""JARVIS MK-X Hyper-Optimization Engine — Batched I/O optimizer."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.hyper_opt.io_optimizer")

_DEFAULT_CACHE_TTL_S = 5.0
_DEFAULT_DIR_CACHE_TTL_S = 2.0


class IOBatchOptimizer:
    """Batches filesystem operations for reduced I/O overhead with read caching."""

    def __init__(
        self,
        batch_size: int = 10,
        flush_interval_ms: float = 100.0,
        cache_ttl_s: float = _DEFAULT_CACHE_TTL_S,
        dir_cache_ttl_s: float = _DEFAULT_DIR_CACHE_TTL_S,
    ) -> None:
        self._pending_writes: List[Dict[str, Any]] = []
        self._read_cache: Dict[str, Dict[str, Any]] = {}
        self._dir_cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._batch_size = batch_size
        self._flush_interval_ms = flush_interval_ms
        self._cache_ttl_s = cache_ttl_s
        self._dir_cache_ttl_s = dir_cache_ttl_s
        self._last_flush_time = time.perf_counter()
        self._stats: Dict[str, Any] = {
            "reads": 0,
            "writes": 0,
            "batched_writes": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "dir_cache_hits": 0,
            "dir_cache_misses": 0,
            "total_read_ms": 0.0,
            "total_write_ms": 0.0,
            "flushes": 0,
        }

    def read_file(self, path: str, use_cache: bool = True) -> bytes:
        """Read file contents. Uses cache when available and fresh."""
        abs_path = os.path.abspath(path)
        with self._lock:
            if use_cache:
                entry = self._read_cache.get(abs_path)
                if entry is not None:
                    if time.perf_counter() - entry["timestamp"] < self._cache_ttl_s:
                        try:
                            current_mtime = os.path.getmtime(abs_path)
                        except OSError:
                            current_mtime = None
                        if current_mtime is not None and current_mtime <= entry["mtime"]:
                            self._stats["reads"] += 1
                            self._stats["cache_hits"] += 1
                            return entry["data"]
            start = time.perf_counter()
            try:
                with open(abs_path, "rb") as fh:
                    data = fh.read()
            except OSError:
                logger.warning("Failed to read file: %s", abs_path)
                raise
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            self._stats["reads"] += 1
            self._stats["cache_misses"] += 1
            self._stats["total_read_ms"] += elapsed_ms
            try:
                mtime = os.path.getmtime(abs_path)
            except OSError:
                mtime = time.time()
            if use_cache:
                self._read_cache[abs_path] = {
                    "data": data,
                    "mtime": mtime,
                    "timestamp": time.perf_counter(),
                }
            logger.debug(
                "Read %s (%d bytes, %.2f ms, cached=%s)",
                abs_path,
                len(data),
                elapsed_ms,
                use_cache,
            )
            return data

    def write_file(
        self, path: str, data: bytes, immediate: bool = False
    ) -> None:
        """Queue a write or write immediately."""
        abs_path = os.path.abspath(path)
        if immediate:
            start = time.perf_counter()
            with self._lock:
                self._write_to_disk(abs_path, data)
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                self._stats["writes"] += 1
                self._stats["total_write_ms"] += elapsed_ms
                self._invalidate_read_cache(abs_path)
            logger.debug("Immediate write to %s (%d bytes, %.2f ms)", abs_path, len(data), elapsed_ms)
            return
        with self._lock:
            self._pending_writes.append(
                {
                    "path": abs_path,
                    "data": data,
                    "timestamp": time.perf_counter(),
                }
            )
            self._stats["batched_writes"] += 1
            self._invalidate_read_cache(abs_path)
            should_flush = (
                len(self._pending_writes) >= self._batch_size
                or (time.perf_counter() - self._last_flush_time) * 1000.0
                >= self._flush_interval_ms
            )
        if should_flush:
            self.flush()

    def _write_to_disk(self, abs_path: str, data: bytes) -> None:
        """Write data to disk, creating parent directories if needed."""
        try:
            parent = os.path.dirname(abs_path)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
            with open(abs_path, "wb") as fh:
                fh.write(data)
        except OSError:
            logger.exception("Failed to write file: %s", abs_path)
            raise

    def _invalidate_read_cache(self, abs_path: str) -> None:
        """Remove a specific path from the read cache."""
        self._read_cache.pop(abs_path, None)

    def flush(self) -> int:
        """Flush all pending writes immediately. Returns count of writes flushed."""
        with self._lock:
            if not self._pending_writes:
                return 0
            pending = list(self._pending_writes)
            self._pending_writes.clear()
            self._last_flush_time = time.perf_counter()
        start = time.perf_counter()
        count = 0
        for entry in pending:
            try:
                self._write_to_disk(entry["path"], entry["data"])
                count += 1
            except OSError:
                continue
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        with self._lock:
            self._stats["writes"] += count
            self._stats["total_write_ms"] += elapsed_ms
            self._stats["flushes"] += 1
        logger.debug("Flushed %d writes (%.2f ms)", count, elapsed_ms)
        return count

    def list_dir(self, path: str, use_cache: bool = True) -> List[str]:
        """List directory entries with caching."""
        abs_path = os.path.abspath(path)
        with self._lock:
            if use_cache:
                entry = self._dir_cache.get(abs_path)
                if entry is not None:
                    if time.perf_counter() - entry["timestamp"] < self._dir_cache_ttl_s:
                        self._stats["dir_cache_hits"] += 1
                        return list(entry["entries"])
            try:
                entries = sorted(os.listdir(abs_path))
            except OSError:
                logger.warning("Failed to list directory: %s", abs_path)
                raise
            self._stats["dir_cache_misses"] += 1
            if use_cache:
                self._dir_cache[abs_path] = {
                    "entries": entries,
                    "timestamp": time.perf_counter(),
                }
            logger.debug("Listed %s (%d entries)", abs_path, len(entries))
            return entries

    def batch_read(self, paths: List[str]) -> Dict[str, bytes]:
        """Read multiple files, leveraging cache where possible."""
        results: Dict[str, bytes] = {}
        uncached: List[str] = []
        with self._lock:
            for p in paths:
                abs_p = os.path.abspath(p)
                entry = self._read_cache.get(abs_p)
                if entry is not None:
                    if time.perf_counter() - entry["timestamp"] < self._cache_ttl_s:
                        try:
                            current_mtime = os.path.getmtime(abs_p)
                        except OSError:
                            current_mtime = None
                        if current_mtime is not None and current_mtime <= entry["mtime"]:
                            results[abs_p] = entry["data"]
                            self._stats["cache_hits"] += 1
                            self._stats["reads"] += 1
                            continue
                uncached.append(abs_p)
        start = time.perf_counter()
        for abs_p in uncached:
            try:
                with open(abs_p, "rb") as fh:
                    data = fh.read()
                try:
                    mtime = os.path.getmtime(abs_p)
                except OSError:
                    mtime = time.time()
                results[abs_p] = data
                with self._lock:
                    self._read_cache[abs_p] = {
                        "data": data,
                        "mtime": mtime,
                        "timestamp": time.perf_counter(),
                    }
                    self._stats["reads"] += 1
                    self._stats["cache_misses"] += 1
            except OSError:
                logger.debug("batch_read: skipping unreadable file %s", abs_p)
                continue
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        logger.debug(
            "Batch read: %d total, %d cached, %.2f ms",
            len(paths),
            len(paths) - len(uncached),
            elapsed_ms,
        )
        return results

    def invalidate_cache(self, path: Optional[str] = None) -> int:
        """Invalidate read cache for a specific path or all. Returns entries removed."""
        with self._lock:
            if path is None:
                count = len(self._read_cache) + len(self._dir_cache)
                self._read_cache.clear()
                self._dir_cache.clear()
                logger.info("Invalidated all caches (%d entries)", count)
                return count
            abs_path = os.path.abspath(path)
            removed = 0
            if abs_path in self._read_cache:
                del self._read_cache[abs_path]
                removed += 1
            if abs_path in self._dir_cache:
                del self._dir_cache[abs_path]
                removed += 1
            logger.debug("Invalidated cache for %s (%d entries)", abs_path, removed)
            return removed

    def get_pending_count(self) -> int:
        """Return count of pending (unflushed) writes."""
        with self._lock:
            return len(self._pending_writes)

    def get_stats(self) -> Dict[str, Any]:
        """Returns aggregate I/O statistics."""
        with self._lock:
            reads = self._stats["reads"]
            cache_hits = self._stats["cache_hits"]
            total_cache = cache_hits + self._stats["cache_misses"]
            cache_hit_rate = cache_hits / total_cache if total_cache > 0 else 0.0
            avg_read_ms = (
                self._stats["total_read_ms"] / reads if reads > 0 else 0.0
            )
            writes = self._stats["writes"]
            avg_write_ms = (
                self._stats["total_write_ms"] / writes if writes > 0 else 0.0
            )
            return {
                "reads": reads,
                "writes": writes,
                "batched_writes": self._stats["batched_writes"],
                "cache_hit_rate": round(cache_hit_rate, 4),
                "dir_cache_hit_rate": round(
                    self._stats["dir_cache_hits"]
                    / (
                        self._stats["dir_cache_hits"]
                        + self._stats["dir_cache_misses"]
                    )
                    if (self._stats["dir_cache_hits"] + self._stats["dir_cache_misses"]) > 0
                    else 0.0,
                    4,
                ),
                "avg_read_ms": round(avg_read_ms, 3),
                "avg_write_ms": round(avg_write_ms, 3),
                "total_read_ms": round(self._stats["total_read_ms"], 3),
                "total_write_ms": round(self._stats["total_write_ms"], 3),
                "flushes": self._stats["flushes"],
                "pending_writes": len(self._pending_writes),
                "read_cache_size": len(self._read_cache),
                "dir_cache_size": len(self._dir_cache),
            }

    def get_io_profile(self) -> Dict[str, Any]:
        """Returns IO usage profile with recommendations."""
        with self._lock:
            stats = self.get_stats()
            total_ops = stats["reads"] + stats["writes"]
            read_ratio = stats["reads"] / total_ops if total_ops > 0 else 0.0
            write_ratio = stats["writes"] / total_ops if total_ops > 0 else 0.0
            if read_ratio > 0.8:
                profile = "read_heavy"
            elif write_ratio > 0.8:
                profile = "write_heavy"
            elif stats["batched_writes"] > stats["writes"] * 0.5:
                profile = "batched_writes"
            else:
                profile = "balanced"
            recommendations: List[str] = []
            if stats["cache_hit_rate"] < 0.3 and stats["reads"] > 50:
                recommendations.append("Cache hit rate is low — consider increasing TTL")
            if stats["pending_writes"] > 20:
                recommendations.append("Many pending writes — consider more frequent flushes")
            if stats["avg_read_ms"] > 10.0:
                recommendations.append("High average read time — check disk performance")
            return {
                "profile": profile,
                "read_ratio": round(read_ratio, 4),
                "write_ratio": round(write_ratio, 4),
                "total_operations": total_ops,
                "recommendations": recommendations,
                "stats": stats,
            }


_instance: Optional[IOBatchOptimizer] = None
_instance_lock = threading.RLock()


def get_io_batch_optimizer() -> IOBatchOptimizer:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = IOBatchOptimizer()
            logger.info("Created IOBatchOptimizer singleton")
        return _instance
