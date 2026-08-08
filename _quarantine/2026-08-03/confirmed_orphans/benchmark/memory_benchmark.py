"""Memory Benchmark — Profiles memory usage, finds largest allocations, detects leaks."""
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import gc
import time
import tracemalloc
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psutil


@dataclass
class MemorySnapshot:
    label: str
    rss_kb: int
    vms_kb: int
    tracemalloc_current_kb: int = 0
    tracemalloc_peak_kb: int = 0
    top_allocations: List[Tuple[str, int]] = field(default_factory=list)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "rss_kb": self.rss_kb,
            "vms_kb": self.vms_kb,
            "rss_mb": round(self.rss_kb / 1024, 1),
            "tracemalloc_current_kb": self.tracemalloc_current_kb,
            "tracemalloc_peak_kb": self.tracemalloc_peak_kb,
            "top_allocations": [{"file": f, "size_kb": s} for f, s in self.top_allocations],
        }


@dataclass
class MemoryBenchmarkResult:
    baseline: MemorySnapshot = None
    after_construction: MemorySnapshot = None
    after_startup: MemorySnapshot = None
    idle_5s: MemorySnapshot = None
    idle_30s: MemorySnapshot = None
    potential_leaks: List[Dict[str, Any]] = field(default_factory=list)
    growth_during_idle_kb: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline": self.baseline.to_dict() if self.baseline else None,
            "after_construction": self.after_construction.to_dict() if self.after_construction else None,
            "after_startup": self.after_startup.to_dict() if self.after_startup else None,
            "idle_5s": self.idle_5s.to_dict() if self.idle_5s else None,
            "idle_30s": self.idle_30s.to_dict() if self.idle_30s else None,
            "potential_leaks": self.potential_leaks,
            "growth_during_idle_kb": self.growth_during_idle_kb,
        }


def _get_process_info() -> Tuple[int, int]:
    p = psutil.Process(os.getpid())
    mem = p.memory_info()
    return mem.rss // 1024, mem.vms // 1024


def _take_snapshot(label: str) -> MemorySnapshot:
    rss, vms = _get_process_info()
    tracemalloc_current = 0
    tracemalloc_peak = 0
    top_allocs = []

    if tracemalloc.is_tracing():
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc_current = int(current / 1024)
        tracemalloc_peak = int(peak / 1024)

        snapshot = tracemalloc.take_snapshot()
        stats = snapshot.statistics("lineno")
        for stat in stats[:10]:
            top_allocs.append((str(stat), int(stat.size / 1024)))

    return MemorySnapshot(
        label=label,
        rss_kb=rss,
        vms_kb=vms,
        tracemalloc_current_kb=tracemalloc_current,
        tracemalloc_peak_kb=tracemalloc_peak,
        top_allocations=top_allocs,
    )


def run_memory_benchmark(rounds: int = 1) -> MemoryBenchmarkResult:
    result = MemoryBenchmarkResult()

    for _ in range(rounds):
        result = _run_single_memory_benchmark()

    return result


def _run_single_memory_benchmark() -> MemoryBenchmarkResult:
    result = MemoryBenchmarkResult()

    gc.collect()
    tracemalloc.start()

    # 1. Baseline (before any imports)
    result.baseline = _take_snapshot("baseline")

    # 2. After construction
    from core.jarvis import JarvisMKX
    jarvis = JarvisMKX()
    gc.collect()
    result.after_construction = _take_snapshot("after_construction")

    # 3. After startup
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(jarvis.startup())
    except Exception:
        pass
    gc.collect()
    result.after_startup = _take_snapshot("after_startup")

    # 4. Idle 5s
    time.sleep(5)
    gc.collect()
    result.idle_5s = _take_snapshot("idle_5s")

    # 5. Idle 30s
    time.sleep(25)
    gc.collect()
    result.idle_30s = _take_snapshot("idle_30s")

    # Check for growth during idle (potential leak)
    if result.idle_5s and result.idle_30s:
        result.growth_during_idle_kb = result.idle_30s.rss_kb - result.idle_5s.rss_kb
        if result.growth_during_idle_kb > 1024:  # > 1MB growth during idle
            result.potential_leaks.append({
                "type": "idle_growth",
                "growth_kb": result.growth_during_idle_kb,
                "description": f"Memory grew {result.growth_during_idle_kb}KB during 25s idle period",
            })

    # Cleanup
    try:
        jarvis.shutdown()
    except Exception:
        pass
    try:
        loop.close()
    except Exception:
        pass

    tracemalloc.stop()

    return result


def print_memory_result(result: MemoryBenchmarkResult):
    print(f"\n{'=' * 60}")
    print("  MEMORY BENCHMARK RESULTS")
    print(f"{'=' * 60}")

    snapshots = [
        ("Baseline (empty)", result.baseline),
        ("After construction", result.after_construction),
        ("After startup()", result.after_startup),
        ("Idle 5s", result.idle_5s),
        ("Idle 30s", result.idle_30s),
    ]

    for label, snap in snapshots:
        if snap:
            print(f"  {label:30s} RSS={snap.rss_kb / 1024:.1f}MB  tracemalloc={snap.tracemalloc_current_kb / 1024:.1f}MB")

    if result.growth_during_idle_kb:
        sign = "+" if result.growth_during_idle_kb > 0 else ""
        print(f"\n  Idle memory growth:    {sign}{result.growth_during_idle_kb}KB ({result.growth_during_idle_kb / 1024:.1f}MB)")

    if result.potential_leaks:
        print("\n  ⚠ Potential leaks detected:")
        for leak in result.potential_leaks:
            print(f"    - {leak['description']}")

    # Show top allocations from last snapshot
    last_snap = result.idle_30s or result.after_startup
    if last_snap and last_snap.top_allocations:
        print("\n  Top memory allocations:")
        for alloc_file, alloc_size in last_snap.top_allocations[:5]:
            print(f"    {alloc_size:8d}KB  {alloc_file}")

    print(f"{'=' * 60}")
