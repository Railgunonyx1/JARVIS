"""Telemetry Benchmark — Measures system stats collection overhead, SSE streaming performance."""
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import time
import json
import statistics
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psutil


@dataclass
class TelemetryBenchmarkResult:
    system_stats_ms: List[float] = field(default_factory=list)
    telemetry_collection_ms: List[float] = field(default_factory=list)
    cpu_overhead_percent: float = 0.0
    memory_overhead_kb: int = 0
    json_serialization_ms: List[float] = field(default_factory=list)
    sse_message_count: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "avg_system_stats_ms": round(statistics.mean(self.system_stats_ms), 2) if self.system_stats_ms else 0,
            "avg_telemetry_collection_ms": round(statistics.mean(self.telemetry_collection_ms), 2) if self.telemetry_collection_ms else 0,
            "cpu_overhead_percent": round(self.cpu_overhead_percent, 2),
            "memory_overhead_kb": self.memory_overhead_kb,
            "avg_json_serialization_ms": round(statistics.mean(self.json_serialization_ms), 3) if self.json_serialization_ms else 0,
            "sse_message_count": self.sse_message_count,
            "errors": self.errors,
        }


def run_telemetry_benchmark(rounds: int = 100) -> TelemetryBenchmarkResult:
    result = TelemetryBenchmarkResult()

    for _ in range(rounds):
        _measure_system_stats(result)

    _measure_collection_overhead(result)
    _measure_json_serialization(result)

    return result


def _measure_system_stats(result: TelemetryBenchmarkResult):
    t0 = time.perf_counter()
    try:
        proc = psutil.Process(os.getpid())

        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        proc_mem = proc.memory_info()
        proc_cpu = proc.cpu_percent(interval=None)

        stats = {
            "cpu_percent": cpu,
            "ram_percent": mem.percent,
            "ram_used_mb": mem.used / (1024 * 1024),
            "ram_total_mb": mem.total / (1024 * 1024),
            "process_rss_mb": proc_mem.rss / (1024 * 1024),
            "process_cpu_percent": proc_cpu,
            "thread_count": proc.num_threads(),
            "open_files": len(proc.open_files()),
            "connections": len(proc.connections()),
        }

        elapsed = (time.perf_counter() - t0) * 1000
        result.system_stats_ms.append(elapsed)
    except Exception as e:
        result.errors.append(f"system_stats: {e}")


def _measure_collection_overhead(result: TelemetryBenchmarkResult):
    proc = psutil.Process(os.getpid())

    # Measure overhead of collecting telemetry over 50 iterations
    t0 = time.perf_counter()
    for _ in range(50):
        psutil.cpu_percent(interval=None)
        proc.memory_info()
        proc.num_threads()
    elapsed = (time.perf_counter() - t0) * 1000
    result.telemetry_collection_ms.append(elapsed)
    result.cpu_overhead_percent = proc.cpu_percent(interval=None)


def _measure_json_serialization(result: TelemetryBenchmarkResult):
    sample_data = {
        "cpu_percent": 25.5,
        "ram_percent": 65.2,
        "ram_used_mb": 5200.0,
        "ram_total_mb": 8192.0,
        "process_rss_mb": 204.0,
        "thread_count": 14,
        "providers": {
            "groq": {"available": True, "model": "llama-3.3-70b", "latency_ms": 150},
            "gemini": {"available": True, "model": "gemini-2.5-flash", "latency_ms": 300},
        },
        "voice": {"stt_backend": "groq", "tts_backend": "piper", "vad_active": False},
        "session_id": "abc12345",
    }

    for _ in range(100):
        t0 = time.perf_counter()
        serialized = json.dumps(sample_data)
        _ = json.loads(serialized)
        elapsed = (time.perf_counter() - t0) * 1000
        result.json_serialization_ms.append(elapsed)


def print_telemetry_result(result: TelemetryBenchmarkResult):
    print(f"\n{'=' * 60}")
    print("  TELEMETRY BENCHMARK RESULTS")
    print(f"{'=' * 60}")

    if result.system_stats_ms:
        avg_stats = statistics.mean(result.system_stats_ms)
        print(f"\n  System Stats Collection:")
        print(f"    Average:  {avg_stats:.2f}ms")
        print(f"    Min:      {min(result.system_stats_ms):.2f}ms")
        print(f"    Max:      {max(result.system_stats_ms):.2f}ms")

    if result.telemetry_collection_ms:
        print(f"\n  Collection Overhead (50 iterations):")
        print(f"    Total:    {result.telemetry_collection_ms[0]:.1f}ms")
        print(f"    Per-call: {result.telemetry_collection_ms[0] / 50:.2f}ms")

    print(f"\n  CPU Overhead:     {result.cpu_overhead_percent:.1f}%")

    if result.json_serialization_ms:
        avg_json = statistics.mean(result.json_serialization_ms)
        print(f"\n  JSON Serialization:")
        print(f"    Average:  {avg_json:.3f}ms")
        print(f"    Per 1KB:  {avg_json:.3f}ms")

    if result.errors:
        print(f"\n  Errors ({len(result.errors)}):")
        for err in result.errors[:5]:
            print(f"    - {err}")

    print(f"{'=' * 60}")
