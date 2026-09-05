"""Orbit path latency measurement — P50/P95/P99 (G13).

Hermetic by construction: it measures the *real* Python path a live browser
run exercises (ToolExecutionService dispatch + audit, constellation-memory
store round trips, wizard parsing, and the controller → CDP-backend facade
against a fake transport) so the gate runs on any machine without Chromium.
End-to-end *live* Chromium timings are captured by the opt-in suites
(``JARVIS_RUN_BROWSER_LIVE=1``) which this module complements.

Percentiles use the nearest-rank method over the sampled distribution.
"""

from __future__ import annotations

import asyncio
import json
import math
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

MAX_SAMPLES = 500


def percentile(samples: list[float], p: float) -> float:
    """Nearest-rank percentile (p in 0..100) over a sorted copy."""
    if not samples:
        return 0.0
    ordered = sorted(samples)
    rank = max(1, math.ceil(len(ordered) * p / 100))
    return ordered[min(rank, len(ordered)) - 1]


def summarize(samples: list[float]) -> dict[str, Any]:
    """P50/P95/P99 + basic shape of a sample set (values in input units)."""
    if not samples:
        return {"n": 0, "min_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0,
                "p99_ms": 0.0, "max_ms": 0.0}
    return {
        "n": len(samples),
        "min_ms": round(min(samples) * 1000, 3),
        "p50_ms": round(percentile(samples, 50) * 1000, 3),
        "p95_ms": round(percentile(samples, 95) * 1000, 3),
        "p99_ms": round(percentile(samples, 99) * 1000, 3),
        "max_ms": round(max(samples) * 1000, 3),
    }


def _time(iterations: int, fn: Callable[[], Any]) -> list[float]:
    samples: list[float] = []
    for _ in range(max(1, min(iterations, MAX_SAMPLES))):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return samples


# ── measured paths ──────────────────────────────────────────────────────────

def tool_dispatch_latency(iterations: int = 30) -> list[float]:
    """ToolExecutionService dispatch + permission + audit overhead."""
    from core.agent.permissions import PermissionEngine
    from core.agent.tool_service import ToolExecutionService
    from core.decision_logger import DecisionLogger
    from providers.types import ToolCall
    from tools.registry import ToolRegistry

    from orbit.tools import build_orbit_tools

    logger = DecisionLogger()
    registry = ToolRegistry()
    registry.register_many(build_orbit_tools())
    service = ToolExecutionService(
        registry=registry,
        permissions=PermissionEngine(logger, mode="agent"),
        decision_logger=logger,
        mode="agent",
    )

    def call() -> None:
        asyncio.run(service.execute_tool(
            ToolCall(name="orbit.permissions", arguments={}, id=f"perf-{time.time_ns()}"),
            trace_id="g13_perf", session_id="perf",
        ))

    return _time(iterations, call)


def controller_facade_latency(iterations: int = 30) -> list[float]:
    """BrowserController -> CDP backend facade round trip (fake transport)."""
    from orbit.cdp import CDPBackend
    from jbrowser.controller import BrowserController

    class FakePage:
        url = "https://example.com/"
        title = "Perf"
        body = "latency probe page body"

    class FakeBackend(CDPBackend):
        def __init__(self) -> None:  # noqa: D107 - benchmark stub
            super().__init__(chrome="fake", headless=True, auto_launch=True)
            self._page = FakePage()
            self._browser_conn = object()

        def get_url(self, tab_id=None):  # noqa: ARG002
            return self._page.url

        def get_title(self, tab_id=None):  # noqa: ARG002
            return self._page.title

        def get_page_text(self, tab_id=None):  # noqa: ARG002
            return self._page.body

        def get_dom_snapshot(self, tab_id=None):  # noqa: ARG002
            return {"interactives": [], "links": [], "forms": [],
                    "viewport": {"w": 800, "h": 600}}

    controller = BrowserController(backend=FakeBackend(), profile_root=Path(tempfile.gettempdir()))
    return _time(iterations, lambda: controller.read())


def memory_store_latency(iterations: int = 30) -> list[float]:
    """Constellation memory: owned write + recall + blob put/get per sample."""
    from memory.store import MemoryStore

    store = MemoryStore(data_dir=Path(tempfile.mkdtemp(prefix="orbit-perf-")))

    def once() -> None:
        key = f"agent.perf.note.{time.time_ns()}"
        store.store_owned(key, "benchmark value", owner="agent:perf")
        store.recall(key, owner="agent:perf")
        bkey = f"agent.perf.art.{time.time_ns()}"
        store.put_blob(bkey, b"\x00\x01bench", owner="agent:perf", mime="application/octet-stream")
        store.get_blob(bkey, owner="agent:perf")

    return _time(iterations, once)


def wizard_parse_latency(iterations: int = 30) -> list[float]:
    """G11 wizard: 100-row credentials CSV -> masked ImportPlan per sample."""
    from orbit.wizard import parse_password_csv

    rows = [f"Site{i},https://site{i}.example/login,user{i},Secret-Pw-{i}!" for i in range(100)]
    csv_text = "site,url,username,password\n" + "\n".join(rows)

    def once() -> None:
        plan = parse_password_csv(csv_text)
        assert plan.total == 100

    return _time(iterations, once)


def run_orbit_gate(iterations: int = 25, json_path: str | Path | None = None,
                   quiet: bool = False) -> dict[str, Any]:
    """Sample every hermetic Orbit path and report P50/P95/P99.

    Writes a JSON report to ``json_path`` (e.g. ``benchmark/results/orbit.json``)
    when provided, mirroring the existing benchmark artifacts.
    """
    phases: dict[str, list[float]] = {
        "tool_dispatch": tool_dispatch_latency(iterations),
        "controller_facade": controller_facade_latency(iterations),
        "memory_store": memory_store_latency(iterations),
        "wizard_parse_100": wizard_parse_latency(iterations),
    }
    report = {
        "benchmark": "orbit-latency-gate",
        "iterations": iterations,
        "phases": {name: summarize(s) for name, s in phases.items()},
    }
    if json_path is not None:
        out = Path(json_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not quiet:
        for name, s in phases.items():
            summary = report["phases"][name]
            print(f"{name:24s} n={summary['n']:3d}  "
                  f"p50={summary['p50_ms']:8.3f}ms  p95={summary['p95_ms']:8.3f}ms  "
                  f"p99={summary['p99_ms']:8.3f}ms")
    return report


if __name__ == "__main__":
    run_orbit_gate(iterations=25, json_path=Path("benchmark/results/orbit.json"))
