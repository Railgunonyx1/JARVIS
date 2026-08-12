"""
JARVIS MK-X — Baseline Benchmark
Measures 5 metrics before any optimization:
  1. Cold-start time  (import + construct JarvisMKX)
  2. Idle RSS         (memory after 5s idle)
  3. Idle CPU         (CPU after 5s idle)
  4. First-token latency (TTFT via streaming)
  5. First-audio latency (TTS first WAV chunk)

Usage:
  python bench.py              # Full benchmark
  python bench.py --quick      # Skip TTS measurement
  python bench.py --cold-only  # Only measure startup
"""

import os

os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import asyncio
import logging
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Suppress noisy logs during benchmark
logging.basicConfig(level=logging.WARNING, handlers=[logging.NullHandler()])
for name in ["jarvis", "urllib3", "httpx", "httpcore", "asyncio", "groq"]:
    logging.getLogger(name).setLevel(logging.ERROR)

import psutil


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


# ── 1. Cold-Start Time ────────────────────────────────────────────────────
def measure_cold_start():
    banner("1. COLD-START TIME")
    proc = psutil.Process(os.getpid())

    rss_before = proc.memory_info().rss

    # Import the module (forces all imports inside jarvis.py)
    t_import_start = time.perf_counter()
    from core.jarvis import JarvisMKX
    t_import_end = time.perf_counter()

    # Construct the instance
    t_init_start = time.perf_counter()
    jarvis = JarvisMKX()
    t_init_end = time.perf_counter()

    t_total = (t_init_end - t_import_start) * 1000
    t_import = (t_import_end - t_import_start) * 1000
    t_init = (t_init_end - t_init_start) * 1000

    rss_after = proc.memory_info().rss
    rss_delta = rss_after - rss_before

    print(f"  Module import:     {fmt_time(t_import)}")
    print(f"  Construction:      {fmt_time(t_init)}")
    print(f"  Total cold start:  {fmt_time(t_total)}")
    print(f"  RSS delta:         {fmt_bytes(rss_before)} -> {fmt_bytes(rss_after)} (+{fmt_bytes(rss_delta)})")

    return jarvis, t_total, rss_after


# ── 2–3. Idle RSS + CPU ──────────────────────────────────────────────────
def measure_idle(jarvis, duration=5):
    banner("2-3. IDLE RESOURCE USAGE")
    print(f"  Sampling for {duration}s after construction...")

    proc = psutil.Process(os.getpid())

    # Let system settle
    psutil.cpu_percent(interval=None)  # prime the counter
    time.sleep(duration)

    rss = proc.memory_info().rss
    vms = proc.memory_info().vms
    cpu_samples = []
    for _ in range(10):
        cpu_samples.append(psutil.cpu_percent(interval=0.2))

    avg_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0
    max_cpu = max(cpu_samples) if cpu_samples else 0

    print(f"  RSS:               {fmt_bytes(rss)}")
    print(f"  VMS:               {fmt_bytes(vms)}")
    print(f"  Idle CPU (avg):    {avg_cpu:.1f}%")
    print(f"  Idle CPU (max):    {max_cpu:.1f}%")

    return rss, avg_cpu


# ── 4. First-Token Latency (TTFT) ────────────────────────────────────────
def measure_ttft(jarvis):
    banner("4. FIRST-TOKEN LATENCY (TTFT)")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Run startup first so providers are connected
    print("  Running startup (TTS warmup + provider connect)...")
    t_startup_start = time.perf_counter()
    loop.run_until_complete(jarvis.startup())
    t_startup = (time.perf_counter() - t_startup_start) * 1000
    print(f"  Startup time:      {fmt_time(t_startup)}")

    test_commands = [
        "Hello, how are you?",
        "What time is it?",
        "Tell me a joke",
    ]

    ttfts = []
    for cmd in test_commands:
        print(f"\n  Sending: \"{cmd}\"")
        first_token_time = None
        t_start = time.perf_counter()
        token_count = 0

        async def measure():
            nonlocal first_token_time, token_count
            async for chunk_type, chunk_data in jarvis.process_text_streaming(cmd):
                if chunk_type == "text" and first_token_time is None:
                    first_token_time = (time.perf_counter() - t_start) * 1000
                if chunk_type == "text":
                    token_count += 1
                if chunk_type in ("done", "error"):
                    break

        try:
            loop.run_until_complete(asyncio.wait_for(measure(), timeout=30))
        except TimeoutError:
            print("    TIMEOUT (30s)")
            continue

        total = (time.perf_counter() - t_start) * 1000
        if first_token_time:
            ttfts.append(first_token_time)
            print(f"    TTFT:            {fmt_time(first_token_time)}")
            print(f"    Total:           {fmt_time(total)}")
            print(f"    Tokens:          {token_count}")
        else:
            print("    No tokens received")

    if ttfts:
        avg_ttft = sum(ttfts) / len(ttfts)
        print(f"\n  Average TTFT:      {fmt_time(avg_ttft)}")
        print(f"  Best TTFT:         {fmt_time(min(ttfts))}")
        print(f"  Worst TTFT:        {fmt_time(max(ttfts))}")
    else:
        print("\n  No TTFT data collected")

    return ttfts


# ── 5. First-Audio Latency ───────────────────────────────────────────────
def measure_first_audio(jarvis):
    banner("5. FIRST-AUDIO LATENCY")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    cmd = "Say hello in one sentence."
    print(f"  Sending: \"{cmd}\"")

    first_audio_time = None
    t_start = time.perf_counter()
    audio_chunks = 0

    async def measure():
        nonlocal first_audio_time, audio_chunks
        async for chunk_type, chunk_data in jarvis.process_text_streaming(cmd):
            if chunk_type == "tts_chunk" and first_audio_time is None:
                first_audio_time = (time.perf_counter() - t_start) * 1000
            if chunk_type == "tts_chunk":
                audio_chunks += 1
            if chunk_type in ("done", "error"):
                break

    try:
        loop.run_until_complete(asyncio.wait_for(measure(), timeout=30))
    except TimeoutError:
        print("  TIMEOUT (30s)")

    total = (time.perf_counter() - t_start) * 1000
    if first_audio_time:
        print(f"  First audio chunk: {fmt_time(first_audio_time)}")
        print(f"  Total time:        {fmt_time(total)}")
        print(f"  Audio chunks:      {audio_chunks}")
    else:
        print("  No audio chunks received")

    return first_audio_time


# ── Main ──────────────────────────────────────────────────────────────────
def main():
    banner("JARVIS MK-X — BASELINE BENCHMARK")
    print(f"  Python {sys.version.split()[0]}")
    print(f"  PID {os.getpid()}")

    quick = "--quick" in sys.argv
    cold_only = "--cold-only" in sys.argv

    # 1. Cold start
    jarvis, cold_start, rss = measure_cold_start()

    if cold_only:
        print(f"\n{'=' * 60}")
        print("  SUMMARY")
        print(f"{'=' * 60}")
        print(f"  Cold start:  {fmt_time(cold_start)}")
        print(f"  RSS:         {fmt_bytes(rss)}")
        return

    # 2–3. Idle
    idle_rss, idle_cpu = measure_idle(jarvis)

    # 4. TTFT
    ttfts = measure_ttft(jarvis)

    # 5. First audio (skip with --quick)
    first_audio = None
    if not quick:
        first_audio = measure_first_audio(jarvis)

    # ── Summary ───────────────────────────────────────────────────────
    banner("SUMMARY")
    print(f"  Cold start:         {fmt_time(cold_start)}")
    print(f"  Idle RSS:           {fmt_bytes(idle_rss)}")
    print(f"  Idle CPU:           {idle_cpu:.1f}%")
    if ttfts:
        avg_ttft = sum(ttfts) / len(ttfts)
        print(f"  Avg TTFT:           {fmt_time(avg_ttft)}")
    if first_audio:
        print(f"  First audio:        {fmt_time(first_audio)}")
    print(f"{'=' * 60}")

    # Cleanup
    try:
        jarvis.shutdown()
    except Exception:
        pass


if __name__ == "__main__":
    main()
