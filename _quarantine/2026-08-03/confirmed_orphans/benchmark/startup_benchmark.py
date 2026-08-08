"""Startup Benchmark — Measures Python import time, module loading, provider init, voice init, UI startup."""
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import time
import logging
import importlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("benchmark.startup")


@dataclass
class StartupResult:
    python_import_ms: float = 0.0
    module_loads: Dict[str, float] = field(default_factory=dict)
    total_import_ms: float = 0.0
    construction_ms: float = 0.0
    provider_init_ms: float = 0.0
    voice_init_ms: float = 0.0
    startup_call_ms: float = 0.0
    total_cold_start_ms: float = 0.0
    rss_before_kb: int = 0
    rss_after_kb: int = 0
    rss_delta_kb: int = 0
    thread_count_before: int = 0
    thread_count_after: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "python_import_ms": self.python_import_ms,
            "module_loads": self.module_loads,
            "total_import_ms": self.total_import_ms,
            "construction_ms": self.construction_ms,
            "provider_init_ms": self.provider_init_ms,
            "voice_init_ms": self.voice_init_ms,
            "startup_call_ms": self.startup_call_ms,
            "total_cold_start_ms": self.total_cold_start_ms,
            "rss_before_kb": self.rss_before_kb,
            "rss_after_kb": self.rss_after_kb,
            "rss_delta_kb": self.rss_delta_kb,
            "thread_count_before": self.thread_count_before,
            "thread_count_after": self.thread_count_after,
        }


def _get_rss_kb() -> int:
    import psutil
    return psutil.Process(os.getpid()).memory_info().rss // 1024


def _get_thread_count() -> int:
    import psutil
    return psutil.Process(os.getpid()).num_threads()


def _measure_import(module_name: str) -> float:
    t0 = time.perf_counter()
    try:
        importlib.import_module(module_name)
    except Exception:
        pass
    return (time.perf_counter() - t0) * 1000


def run_startup_benchmark(rounds: int = 1) -> StartupResult:
    result = StartupResult()

    for _ in range(rounds):
        result = _run_single_startup_benchmark()

    return result


def _run_single_startup_benchmark() -> StartupResult:
    result = StartupResult()
    proc_rss_before = _get_rss_kb()
    result.rss_before_kb = proc_rss_before
    result.thread_count_before = _get_thread_count()

    # 1. Python import time (measure core.jarvis import which triggers all deps)
    t_import_start = time.perf_counter()

    # Measure individual critical module imports
    critical_modules = [
        "core.config",
        "core.jarvis",
        "core.intent_router",
        "core.context",
        "core.dialogue",
        "core.personality",
        "providers.router",
        "pipeline.stt",
        "pipeline.tts",
        "pipeline.vad",
        "pipeline.wake_word",
        "memory.store",
        "memory.vector_store",
        "security.engine",
        "web.server",
    ]

    # Reset import state by clearing cached modules (only if not first run)
    for mod_name in critical_modules:
        if mod_name in sys.modules:
            del sys.modules[mod_name]

    module_times = {}
    for mod_name in critical_modules:
        t0 = time.perf_counter()
        try:
            importlib.import_module(mod_name)
        except Exception as e:
            logger.debug("Failed to import %s: %s", mod_name, e)
        elapsed = (time.perf_counter() - t0) * 1000
        module_times[mod_name] = round(elapsed, 2)

    result.module_loads = module_times
    result.total_import_ms = round((time.perf_counter() - t_import_start) * 1000, 2)

    # 2. Construction time (JarvisMKX.__init__)
    from core.jarvis import JarvisMKX

    t_init_start = time.perf_counter()
    jarvis = JarvisMKX()
    result.construction_ms = round((time.perf_counter() - t_init_start) * 1000, 2)

    # 3. Provider initialization (via startup)
    t_startup_start = time.perf_counter()
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(jarvis.startup())
    except Exception as e:
        logger.debug("Startup error: %s", e)
    result.startup_call_ms = round((time.perf_counter() - t_startup_start) * 1000, 2)

    # 4. Final measurements
    result.rss_after_kb = _get_rss_kb()
    result.rss_delta_kb = result.rss_after_kb - result.rss_before_kb
    result.thread_count_after = _get_thread_count()
    result.total_cold_start_ms = round(result.total_import_ms + result.construction_ms + result.startup_call_ms, 2)

    # Cleanup
    try:
        jarvis.shutdown()
    except Exception:
        pass
    try:
        loop.close()
    except Exception:
        pass

    return result


def print_startup_result(result: StartupResult):
    print(f"\n{'=' * 60}")
    print("  STARTUP BENCHMARK RESULTS")
    print(f"{'=' * 60}")
    print(f"  Total cold start:     {result.total_cold_start_ms:.0f}ms ({result.total_cold_start_ms / 1000:.2f}s)")
    print(f"  ├─ Module imports:    {result.total_import_ms:.0f}ms")
    print(f"  ├─ Construction:      {result.construction_ms:.0f}ms")
    print(f"  └─ Startup():         {result.startup_call_ms:.0f}ms")
    print()
    print(f"  RSS: {result.rss_before_kb}KB → {result.rss_after_kb}KB (+{result.rss_delta_kb}KB / +{result.rss_delta_kb / 1024:.1f}MB)")
    print(f"  Threads: {result.thread_count_before} → {result.thread_count_after}")
    print()
    print("  Module load times:")
    for mod, ms in sorted(result.module_loads.items(), key=lambda x: -x[1])[:10]:
        print(f"    {mod:40s} {ms:8.1f}ms")
    print(f"{'=' * 60}")
