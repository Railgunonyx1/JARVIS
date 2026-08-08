"""Microsecond Profiler — Measure kernel launch, token generation, context build, etc.

Locate every bottleneck at microsecond granularity.
"""
import logging
import time
import threading
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger("inference_optimization.micro_profiler")


@dataclass
class TimingEntry:
    """A single timing measurement."""
    name: str
    start_ns: int = 0
    end_ns: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed_us(self) -> float:
        return (self.end_ns - self.start_ns) / 1000

    @property
    def elapsed_ms(self) -> float:
        return (self.end_ns - self.start_ns) / 1_000_000


class MicrosecondProfiler:
    """Ultra-precise profiler measuring at microsecond granularity.

    Tracks:
    - Kernel launch overhead
    - Token generation time
    - Context build time
    - Scheduler delay
    - Memory copy time
    - Cache lookup time
    """

    def __init__(self, max_entries: int = 10000):
        self._entries: Dict[str, List[TimingEntry]] = defaultdict(list)
        self._active: Dict[str, int] = {}  # name → start_ns
        self._max_entries = max_entries
        self._lock = threading.Lock()

    def start(self, name: str) -> None:
        """Start timing a named section."""
        self._active[name] = time.perf_counter_ns()

    def stop(self, name: str, **metadata) -> Optional[TimingEntry]:
        """Stop timing and record the entry."""
        start_ns = self._active.pop(name, None)
        if start_ns is None:
            return None

        entry = TimingEntry(
            name=name,
            start_ns=start_ns,
            end_ns=time.perf_counter_ns(),
            metadata=metadata,
        )

        with self._lock:
            self._entries[name].append(entry)
            if len(self._entries[name]) > self._max_entries:
                self._entries[name] = self._entries[name][-self._max_entries // 2:]

        return entry

    def get_stats(self, name: str) -> Dict[str, Any]:
        """Get statistics for a named timing section."""
        with self._lock:
            entries = self._entries.get(name, [])

        if not entries:
            return {"name": name, "samples": 0}

        times_us = sorted([e.elapsed_us for e in entries])
        times_ms = [e.elapsed_ms for e in entries]
        n = len(times_us)

        return {
            "name": name,
            "samples": n,
            "min_us": round(times_us[0], 1),
            "max_us": round(times_us[-1], 1),
            "avg_us": round(sum(times_us) / n, 1),
            "median_us": round(times_us[n // 2], 1),
            "p95_us": round(times_us[int(n * 0.95)] if n >= 20 else times_us[-1], 1),
            "p99_us": round(times_us[int(n * 0.99)] if n >= 100 else times_us[-1], 1),
            "avg_ms": round(sum(times_ms) / n, 3),
        }

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            names = list(self._entries.keys())
        return {name: self.get_stats(name) for name in names}

    def clear(self, name: str = None) -> None:
        with self._lock:
            if name:
                self._entries.pop(name, None)
            else:
                self._entries.clear()

    def report(self) -> str:
        """Generate a formatted profiling report."""
        all_stats = self.get_all_stats()
        lines = ["=== Microsecond Profiler Report ==="]
        for name, stats in sorted(all_stats.items()):
            if stats["samples"] > 0:
                lines.append(
                    f"  {name}: avg={stats['avg_us']:.1f}us "
                    f"p95={stats['p95_us']:.1f}us "
                    f"n={stats['samples']}"
                )
        return "\n".join(lines)


_profiler_instance: Optional[MicrosecondProfiler] = None


def get_micro_profiler() -> MicrosecondProfiler:
    global _profiler_instance
    if _profiler_instance is None:
        _profiler_instance = MicrosecondProfiler()
    return _profiler_instance
