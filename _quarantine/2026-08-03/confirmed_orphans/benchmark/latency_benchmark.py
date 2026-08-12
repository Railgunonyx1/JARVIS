"""Latency Benchmark — Measures TTFT, total response, provider fallback, intent classification."""
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@dataclass
class LatencyResult:
    ttft_values_ms: list[float] = field(default_factory=list)
    total_response_ms: list[float] = field(default_factory=list)
    intent_classify_ms: list[float] = field(default_factory=list)
    tokens_per_sec: list[float] = field(default_factory=list)
    provider_used: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)

    @property
    def avg_ttft(self) -> float:
        return statistics.mean(self.ttft_values_ms) if self.ttft_values_ms else 0

    @property
    def p50_ttft(self) -> float:
        if not self.ttft_values_ms:
            return 0
        s = sorted(self.ttft_values_ms)
        return s[len(s) // 2]

    @property
    def p95_ttft(self) -> float:
        if not self.ttft_values_ms:
            return 0
        s = sorted(self.ttft_values_ms)
        idx = int(len(s) * 0.95)
        return s[min(idx, len(s) - 1)]

    @property
    def avg_tokens_per_sec(self) -> float:
        return statistics.mean(self.tokens_per_sec) if self.tokens_per_sec else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "avg_ttft_ms": round(self.avg_ttft, 1),
            "p50_ttft_ms": round(self.p50_ttft, 1),
            "p95_ttft_ms": round(self.p95_ttft, 1),
            "min_ttft_ms": round(min(self.ttft_values_ms), 1) if self.ttft_values_ms else 0,
            "max_ttft_ms": round(max(self.ttft_values_ms), 1) if self.ttft_values_ms else 0,
            "avg_total_response_ms": round(statistics.mean(self.total_response_ms), 1) if self.total_response_ms else 0,
            "avg_intent_classify_ms": round(statistics.mean(self.intent_classify_ms), 1) if self.intent_classify_ms else 0,
            "avg_tokens_per_sec": round(self.avg_tokens_per_sec, 1),
            "provider_used": list(set(self.provider_used)),
            "errors": self.errors,
            "sample_count": len(self.ttft_values_ms),
        }


DEFAULT_TEST_COMMANDS = [
    "Hello, how are you?",
    "What time is it?",
    "Tell me a joke",
    "What's the weather like?",
    "Open notepad",
    "Search for Python tutorials",
    "What's in my memory?",
    "Take a screenshot",
    "How much RAM am I using?",
    "Thank you",
]


def run_latency_benchmark(rounds: int = 1, commands: list[str] = None) -> LatencyResult:
    if commands is None:
        commands = DEFAULT_TEST_COMMANDS

    result = LatencyResult(test_commands=commands)

    for _ in range(rounds):
        _run_single_latency_benchmark(result, commands)

    return result


def _run_single_latency_benchmark(result: LatencyResult, commands: list[str]):
    from core.jarvis import JarvisMKX

    jarvis = JarvisMKX()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(jarvis.startup())
    except Exception:
        pass

    for cmd in commands:
        try:
            _measure_command(jarvis, cmd, result)
        except Exception as e:
            result.errors.append(f"{cmd}: {e}")

    try:
        jarvis.shutdown()
    except Exception:
        pass
    try:
        loop.close()
    except Exception:
        pass


def _measure_command(jarvis, cmd: str, result: LatencyResult):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    first_token_time = None
    t_start = time.perf_counter()
    token_count = 0
    token_times = []
    provider = "unknown"
    response_text = ""

    async def _collect():
        nonlocal first_token_time, token_count, provider, response_text
        async for chunk_type, chunk_data in jarvis.process_text_streaming(cmd):
            if chunk_type == "intent":
                intent_ms = (time.perf_counter() - t_start) * 1000
                result.intent_classify_ms.append(intent_ms)
                if hasattr(chunk_data, 'provider'):
                    provider = chunk_data.provider
            elif chunk_type == "text":
                now = time.perf_counter()
                if first_token_time is None:
                    first_token_time = (now - t_start) * 1000
                token_times.append(now)
                token_count += 1
                if isinstance(chunk_data, str):
                    response_text += chunk_data
            elif chunk_type in ("done", "error"):
                break

    try:
        loop.run_until_complete(asyncio.wait_for(_collect(), timeout=30))
    except TimeoutError:
        result.errors.append(f"{cmd}: timeout")
        return
    finally:
        try:
            loop.close()
        except Exception:
            pass

    total_ms = (time.perf_counter() - t_start) * 1000

    if first_token_time:
        result.ttft_values_ms.append(first_token_time)
        result.total_response_ms.append(total_ms)
        result.provider_used.append(provider)

        if len(token_times) > 1:
            stream_duration = token_times[-1] - token_times[0]
            if stream_duration > 0:
                tps = (len(token_times) - 1) / stream_duration
                result.tokens_per_sec.append(tps)


def print_latency_result(result: LatencyResult):
    print(f"\n{'=' * 60}")
    print("  LATENCY BENCHMARK RESULTS")
    print(f"{'=' * 60}")

    if result.ttft_values_ms:
        print("  TTFT (First Token Latency):")
        print(f"    Average:  {result.avg_ttft:.0f}ms")
        print(f"    P50:      {result.p50_ttft:.0f}ms")
        print(f"    P95:      {result.p95_ttft:.0f}ms")
        print(f"    Min:      {min(result.ttft_values_ms):.0f}ms")
        print(f"    Max:      {max(result.ttft_values_ms):.0f}ms")
        print(f"    Samples:  {len(result.ttft_values_ms)}")
    else:
        print("  No TTFT data collected")

    if result.total_response_ms:
        avg_total = statistics.mean(result.total_response_ms)
        print("\n  Total Response Time:")
        print(f"    Average:  {avg_total:.0f}ms")

    if result.intent_classify_ms:
        avg_intent = statistics.mean(result.intent_classify_ms)
        print("\n  Intent Classification:")
        print(f"    Average:  {avg_intent:.0f}ms")

    if result.tokens_per_sec:
        avg_tps = statistics.mean(result.tokens_per_sec)
        print("\n  Token Throughput:")
        print(f"    Average:  {avg_tps:.1f} tokens/sec")

    if result.provider_used:
        providers = {}
        for p in result.provider_used:
            providers[p] = providers.get(p, 0) + 1
        print("\n  Provider Distribution:")
        for p, count in sorted(providers.items(), key=lambda x: -x[1]):
            print(f"    {p:20s} {count} requests")

    if result.errors:
        print(f"\n  Errors ({len(result.errors)}):")
        for err in result.errors[:5]:
            print(f"    - {err}")

    print(f"{'=' * 60}")
