"""
JARVIS MK-X — Terminal-First Benchmark.

Measures the real CLI/agent stack (no daemon, no voice):
  1. Cold start   — import ``cli.main`` + build the agent loop
  2. Warm boot    — re-build loop inside one process (provider pre-warm)
  3. First token  — TTFT via streaming (``loop.run(goal, on_chunk=...)``)
  4. End-to-end   — one-shot goal latency through the same path as ``-m cli``

Usage:
  python scripts/bench.py                # full benchmark (needs API keys)
  python scripts/bench.py --cold-only    # only startup measurements
  python scripts/bench.py --iterations N # streaming probes per goal
"""

import os

os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import logging

logging.basicConfig(level=logging.WARNING, handlers=[logging.NullHandler()])
for name in ["jarvis", "urllib3", "httpx", "httpcore", "asyncio", "groq",
             "openai", "anthropic", "google"]:
    logging.getLogger(name).setLevel(logging.ERROR)

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Small goals so the model finishes quickly; the LLM is the variable part.
PROBES = ["Say hello in one short sentence."]
COLD_ONLY = "--cold-only" in sys.argv
ITERATIONS = 1


def banner(msg):
    print(f"\n{'=' * 60}")
    print(f"  {msg}")
    print(f"{'=' * 60}")


def fmt_time(ms):
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.2f}s"


def fmt_bytes(b):
    if b < 1024 * 1024:
        return f"{b / 1024:.0f}KB"
    return f"{b / (1024 * 1024):.1f}MB"


def _extract_iterations():
    global ITERATIONS
    for i, arg in enumerate(sys.argv):
        if arg == "--iterations" and i + 1 < len(sys.argv):
            try:
                ITERATIONS = max(1, int(sys.argv[i + 1]))
            except ValueError:
                pass


def measure_cold_start():
    """Import cli.main and build an agent loop (config, tools, providers, memory)."""
    banner("1. COLD-START (CLI import + kernel build)")
    proc = psutil.Process(os.getpid())
    rss_before = proc.memory_info().rss

    from cli.main import _build_loop

    t_start = time.perf_counter()
    t_import_start = time.perf_counter()
    import cli.main  # noqa: F401  (first import of the whole CLI stack)
    t_import = (time.perf_counter() - t_import_start) * 1000

    t_build_start = time.perf_counter()
    loop = _build_loop("agent", 10, None, None)
    t_build = (time.perf_counter() - t_build_start) * 1000

    t_total = (time.perf_counter() - t_start) * 1000
    rss_after = proc.memory_info().rss

    print(f"  CLI import:      {fmt_time(t_import)}")
    print(f"  Kernel build:    {fmt_time(t_build)}")
    print(f"  Total cold start:{fmt_time(t_total)}")
    print(f"  RSS delta:       {fmt_bytes(rss_before)} -> {fmt_bytes(rss_after)} (+{fmt_bytes(rss_after - rss_before)})")

    return loop, t_total, rss_after


def measure_warm_boot():
    """Re-build the loop in-process to isolate per-boot costs (provider pre-warm)."""
    banner("2. WARM KERNEL BOOT (in-process rebuild)")
    from cli.main import _build_loop

    samples = []
    for _ in range(2):
        t0 = time.perf_counter()
        _build_loop("agent", 10, None, None)
        samples.append((time.perf_counter() - t0) * 1000)
    best = min(samples)
    print(f"  best:  {fmt_time(best)}")
    print(f"  runs:  " + "  ".join(fmt_time(s) for s in samples))
    return best


def measure_streaming(loop):
    """TTFT + end-to-end through loop.run(goal, on_chunk=...)."""
    import asyncio

    banner("3. STREAMING (TTFT via on_chunk)")
    if not PROBES:
        print("  no probes defined")
        return []

    async def run_once(goal):
        first = None
        chunks = 0
        t0 = time.perf_counter()

        async def on_chunk(delta):
            nonlocal first, chunks
            if first is None:
                first = (time.perf_counter() - t0) * 1000
            chunks += 1

        result = await loop.run(goal, session_id="", on_chunk=on_chunk)
        return first, (time.perf_counter() - t0) * 1000, chunks, result

    ttfts = []
    for goal in PROBES:
        for i in range(ITERATIONS):
            print(f"  probe: \"{goal[:50]}\"  (run {i + 1}/{ITERATIONS})")
            try:
                first, total, chunks, result = asyncio.run(
                    asyncio.wait_for(run_once(goal), timeout=60)
                )
            except asyncio.TimeoutError:
                print("    TIMEOUT (60s)")
                continue
            except Exception as exc:  # provider down, no key, etc.
                print(f"    ERROR: {exc}")
                continue
            if first:
                ttfts.append(first)
                print(f"    TTFT:     {fmt_time(first)}")
                print(f"    Total:    {fmt_time(total)}")
                print(f"    Chunks:   {chunks}")
                print(f"    Success:  {result.success}")
            else:
                print(f"    No streamed tokens (e2e {fmt_time(total)}ms, success={result.success})")
                if not result.success:
                    print(f"    error: {result.error}")

    if ttfts:
        print(f"\n  Avg TTFT:  {fmt_time(sum(ttfts) / len(ttfts))}")
        print(f"  Best TTFT: {fmt_time(min(ttfts))}")
    return ttfts


def measure_oneshot(loop):
    """Plain one-shot latency (same path as ``python -m cli 'goal'``)."""
    import asyncio

    banner("4. ONE-SHOT LATENCY (plain complete, no streaming)")
    if not PROBES:
        return
    goal = PROBES[0]
    t0 = time.perf_counter()
    try:
        result = asyncio.run(asyncio.wait_for(loop.run(goal), timeout=60))
        total = (time.perf_counter() - t0) * 1000
        print(f"  Total:    {fmt_time(total)}")
        print(f"  Success:  {result.success}")
        if not result.success:
            print(f"  error:    {result.error}")
        tokens = result.state.tokens_used if result.state else 0
        print(f"  Tokens:   {tokens}")
    except Exception as exc:
        print(f"  ERROR: {exc}")


def main():
    _extract_iterations()
    banner("JARVIS MK-X — TERMINAL-FIRST BENCHMARK")
    print(f"  Python {sys.version.split()[0]}")
    print(f"  PID    {os.getpid()}")

    loop, cold_start, rss = measure_cold_start()
    loop.router.warm()

    if COLD_ONLY:
        banner("SUMMARY (COLD-ONLY)")
        print(f"  Cold start:  {fmt_time(cold_start)}")
        print(f"  RSS:         {fmt_bytes(rss)}")
        return

    warm = measure_warm_boot()
    ttfts = measure_streaming(loop)
    if not COLD_ONLY and not ttfts:
        print("\n  No streaming data — provider may be unavailable.")
    measure_oneshot(loop)

    banner("SUMMARY")
    print(f"  Cold start:   {fmt_time(cold_start)}")
    print(f"  Warm boot:    {fmt_time(warm)}")
    if ttfts:
        print(f"  Avg TTFT:     {fmt_time(sum(ttfts) / len(ttfts))}")
        print(f"  Best TTFT:    {fmt_time(min(ttfts))}")

    if loop.mem is not None:
        try:
            loop.mem.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
