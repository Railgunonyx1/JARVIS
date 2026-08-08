"""JARVIS MK-X — Full Benchmark Suite (Phase 0)

Runs all benchmark modules and produces a comprehensive report.

Usage:
    python -m benchmark.run_all              # Full suite
    python -m benchmark.run_all --quick      # Skip voice benchmarks
    python -m benchmark.run_all --startup    # Startup only
    python -m benchmark.run_all --memory     # Memory only
    python -m benchmark.run_all --latency    # Latency only
    python -m benchmark.run_all --voice      # Voice only
    python -m benchmark.run_all --telemetry  # Telemetry only
"""

import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import json
import time
import logging
from pathlib import Path
from datetime import datetime

# Setup path
BENCHMARK_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BENCHMARK_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Suppress noisy logs
logging.basicConfig(level=logging.WARNING, handlers=[logging.NullHandler()])
for name in ["jarvis", "urllib3", "httpx", "httpcore", "asyncio", "groq", "piper", "edge_tts"]:
    logging.getLogger(name).setLevel(logging.ERROR)

from benchmark.startup_benchmark import run_startup_benchmark, print_startup_result
from benchmark.memory_benchmark import run_memory_benchmark, print_memory_result
from benchmark.latency_benchmark import run_latency_benchmark, print_latency_result
from benchmark.voice_benchmark import run_voice_benchmark, print_voice_result
from benchmark.telemetry_benchmark import run_telemetry_benchmark, print_telemetry_result


def banner(msg):
    print(f"\n{'#' * 70}")
    print(f"  {msg}")
    print(f"{'#' * 70}")


def save_results(results: dict, filename: str = None):
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"benchmark_{timestamp}.json"

    results_path = BENCHMARK_DIR / "results" / filename
    results_path.parent.mkdir(exist_ok=True)

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n  Results saved to: {results_path}")
    return results_path


def print_executive_summary(results: dict):
    banner("EXECUTIVE SUMMARY")

    startup = results.get("startup", {})
    memory = results.get("memory", {})
    latency = results.get("latency", {})
    voice = results.get("voice", {})
    telemetry = results.get("telemetry", {})

    print(f"  Date:             {results.get('timestamp', 'unknown')}")
    print(f"  Python:           {results.get('python_version', 'unknown')}")
    print()

    # Key metrics
    print("  KEY METRICS:")
    print(f"  {'Metric':35s} {'Value':15s} {'Target':15s} {'Status':10s}")
    print(f"  {'-' * 75}")

    # Cold start
    cold_start = startup.get("total_cold_start_ms", 0)
    target_startup = 3000  # 3 seconds
    status = "OK" if cold_start <= target_startup else "NEEDS WORK"
    print(f"  {'Cold Start':35s} {cold_start / 1000:.2f}s{'':<9s} {target_startup / 1000:.0f}s{'':<10s} {status}")

    # Idle RAM
    idle_ram = memory.get("idle_30s", {}).get("rss_mb", 0) if memory.get("idle_30s") else 0
    target_ram = 200  # 200MB
    status = "OK" if idle_ram <= target_ram else "NEEDS WORK"
    print(f"  {'Idle RAM':35s} {idle_ram:.0f}MB{'':<10s} {target_ram}MB{'':<10s} {status}")

    # TTFT
    avg_ttft = latency.get("avg_ttft_ms", 0)
    target_ttft = 200  # 200ms
    status = "OK" if avg_ttft <= target_ttft else "NEEDS WORK"
    print(f"  {'TTFT (avg)':35s} {avg_ttft:.0f}ms{'':<10s} {target_ttft}ms{'':<10s} {status}")

    # TTS first chunk
    tts_first = voice.get("tts_avg_first_chunk_ms", 0)
    target_tts = 100  # 100ms
    status = "OK" if tts_first <= target_tts else "NEEDS WORK"
    print(f"  {'TTS First Audio':35s} {tts_first:.0f}ms{'':<10s} {target_tts}ms{'':<10s} {status}")

    # Tokens per sec
    tps = latency.get("avg_tokens_per_sec", 0)
    target_tps = 30
    status = "OK" if tps >= target_tps else "NEEDS WORK"
    print(f"  {'Tokens/sec':35s} {tps:.1f}{'':<13s} {target_tps}{'':<13s} {status}")

    # Telemetry overhead
    json_ms = telemetry.get("avg_json_serialization_ms", 0)
    target_json = 1.0
    status = "OK" if json_ms <= target_json else "NEEDS WORK"
    print(f"  {'JSON Serialization':35s} {json_ms:.3f}ms{'':<10s} {target_json}ms{'':<9s} {status}")

    print()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="JARVIS MK-X Benchmark Suite")
    parser.add_argument("--quick", action="store_true", help="Skip voice benchmarks")
    parser.add_argument("--startup", action="store_true", help="Run startup benchmark only")
    parser.add_argument("--memory", action="store_true", help="Run memory benchmark only")
    parser.add_argument("--latency", action="store_true", help="Run latency benchmark only")
    parser.add_argument("--voice", action="store_true", help="Run voice benchmark only")
    parser.add_argument("--telemetry", action="store_true", help="Run telemetry benchmark only")
    parser.add_argument("--rounds", type=int, default=1, help="Number of rounds per benchmark")
    args = parser.parse_args()

    run_all = not any([args.startup, args.memory, args.latency, args.voice, args.telemetry])

    banner("JARVIS MK-X — FULL BENCHMARK SUITE (PHASE 0)")
    print(f"  Python {sys.version.split()[0]}")
    print(f"  PID {os.getpid()}")
    print(f"  Rounds per benchmark: {args.rounds}")
    print(f"  Time: {datetime.now().isoformat()}")

    results = {
        "timestamp": datetime.now().isoformat(),
        "python_version": sys.version.split()[0],
        "pid": os.getpid(),
        "rounds": args.rounds,
    }

    # 1. Startup
    if run_all or args.startup:
        print("\n>>> Running Startup Benchmark...")
        try:
            startup_result = run_startup_benchmark(rounds=args.rounds)
            print_startup_result(startup_result)
            results["startup"] = startup_result.to_dict()
        except Exception as e:
            print(f"  STARTUP BENCHMARK FAILED: {e}")
            results["startup"] = {"error": str(e)}

    # 2. Memory
    if run_all or args.memory:
        print("\n>>> Running Memory Benchmark...")
        try:
            memory_result = run_memory_benchmark(rounds=args.rounds)
            print_memory_result(memory_result)
            results["memory"] = memory_result.to_dict()
        except Exception as e:
            print(f"  MEMORY BENCHMARK FAILED: {e}")
            results["memory"] = {"error": str(e)}

    # 3. Latency
    if run_all or args.latency:
        print("\n>>> Running Latency Benchmark...")
        try:
            latency_result = run_latency_benchmark(rounds=args.rounds)
            print_latency_result(latency_result)
            results["latency"] = latency_result.to_dict()
        except Exception as e:
            print(f"  LATENCY BENCHMARK FAILED: {e}")
            results["latency"] = {"error": str(e)}

    # 4. Voice
    if (run_all and not args.quick) or args.voice:
        print("\n>>> Running Voice Benchmark...")
        try:
            voice_result = run_voice_benchmark(rounds=args.rounds)
            print_voice_result(voice_result)
            results["voice"] = voice_result.to_dict()
        except Exception as e:
            print(f"  VOICE BENCHMARK FAILED: {e}")
            results["voice"] = {"error": str(e)}

    # 5. Telemetry
    if run_all or args.telemetry:
        print("\n>>> Running Telemetry Benchmark...")
        try:
            telemetry_result = run_telemetry_benchmark()
            print_telemetry_result(telemetry_result)
            results["telemetry"] = telemetry_result.to_dict()
        except Exception as e:
            print(f"  TELEMETRY BENCHMARK FAILED: {e}")
            results["telemetry"] = {"error": str(e)}

    # Executive summary
    print_executive_summary(results)

    # Save results
    save_results(results)

    print("\n  Benchmark suite complete.")


if __name__ == "__main__":
    main()
