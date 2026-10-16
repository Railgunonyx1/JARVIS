"""Normalized performance ledger — one schema for cold start, memory, latency.

P2 (audit): the performance story was spread across several artifacts with
different field names (`startup.launcher_ms`, per-task `total_latency`,
`orbit_timing` P50/P95/P99). This module folds them into a single ledger with a
stable schema so cold-start, memory, and latency numbers live in one place and
can be diffed over time.

Everything here is hermetic: cold start runs the existing startup probe
subprocess, latency runs the existing hermetic Orbit gate. No network, no LLM.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from benchmark.harness import measure_startup
from benchmark.orbit_timing import run_orbit_gate

LEDGER_SCHEMA_VERSION = 1
LEDGER_PATH = Path(__file__).resolve().parent / "results" / "ledger.json"


def _sampled_peak_rss_mb(fn: Callable[[], Any]) -> tuple[Any, float | None]:
    """Run ``fn`` and return (result, peak RSS in MB observed around the run)."""
    try:
        import psutil
    except ImportError:  # pragma: no cover - psutil is a hard dep in practice
        return fn(), None
    proc = psutil.Process()
    before = proc.memory_info().rss
    result = fn()
    after = proc.memory_info().rss
    return result, round(max(before, after) / 1e6, 1)


def build_ledger(iterations: int = 25, measure_cold_start: bool = True) -> dict[str, Any]:
    """Produce the normalized ledger dict (no I/O)."""
    cold = measure_startup() if measure_cold_start else {}
    gate, peak_rss = _sampled_peak_rss_mb(
        lambda: run_orbit_gate(iterations=iterations, quiet=True)
    )
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "cold_start_ms": {
            "launcher": cold.get("launcher_ms"),
            "kernel": cold.get("kernel_ms"),
            "prompt_ready": cold.get("prompt_ready_ms"),
            "wall": cold.get("wall_ms"),
        },
        "memory_mb": {
            "idle_rss": cold.get("rss_mb"),
            "peak_rss_sampling": peak_rss,
        },
        "latency_ms": {
            name: {
                "n": summary.get("n"),
                "p50": summary.get("p50_ms"),
                "p95": summary.get("p95_ms"),
                "p99": summary.get("p99_ms"),
            }
            for name, summary in gate.get("phases", {}).items()
        },
    }


def render_ledger(ledger: dict[str, Any]) -> str:
    """Render the ledger as a human-readable block."""
    cs = ledger.get("cold_start_ms", {})
    mem = ledger.get("memory_mb", {})
    lines = [
        "JARVIS PERFORMANCE LEDGER",
        "─────────────────────────",
        f"Cold start launcher: {cs.get('launcher')} ms",
        f"Cold start kernel:   {cs.get('kernel')} ms",
        f"Prompt-ready (est):  {cs.get('prompt_ready')} ms",
        f"Idle RAM:            {mem.get('idle_rss')} MB",
        f"Peak RAM (sampling): {mem.get('peak_rss_sampling')} MB",
        "Latency (ms):",
    ]
    for name, s in sorted(ledger.get("latency_ms", {}).items()):
        lines.append(
            f"  {name:20s} n={s.get('n')}  "
            f"p50={s.get('p50')}  p95={s.get('p95')}  p99={s.get('p99')}"
        )
    return "\n".join(lines)


def write_ledger(ledger: dict[str, Any], path: str | Path = LEDGER_PATH) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return out


def main(iterations: int = 25, json_path: str | Path = LEDGER_PATH) -> int:
    t0 = time.perf_counter()
    ledger = build_ledger(iterations=iterations)
    out = write_ledger(ledger, json_path)
    print(render_ledger(ledger))
    print(f"\nledger written: {out}  ({time.perf_counter() - t0:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
