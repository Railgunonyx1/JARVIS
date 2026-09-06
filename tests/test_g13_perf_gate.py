"""G13 — orbit perf gate: P50/P95/P99 over the hermetic latency paths.

Hermetic. Proves percentile math, the statistical invariants (p50 <= p95 <=
p99, n consistency), that every measured path runs on this machine without a
browser, and that the JSON report artifact matches the benchmark convention.
No wall-clock thresholds beyond a generous absolute sanity bound (a real
regression, e.g. an accidental sleep or quadratic blowup, must trip it).
"""

from __future__ import annotations

import json
import math

import pytest  # noqa: F401

from benchmark.orbit_timing import (
    controller_facade_latency,
    memory_store_latency,
    percentile,
    run_orbit_gate,
    summarize,
    tool_dispatch_latency,
    wizard_parse_latency,
)

# Generous absolute bounds (seconds): only genuine regressions trip these.
_GENEROUS_P99_CEILINGS = {
    "tool_dispatch": 2.0,
    "controller_facade": 2.0,
    "memory_store": 2.0,
    "wizard_parse_100": 5.0,
}


class TestPercentiles:
    def test_nearest_rank_basics(self):
        assert percentile([], 50) == 0.0
        samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        # Nearest-rank: ceil(0.5 * 10) = 5 -> the 5th ordered sample.
        assert percentile(samples, 50) == 5.0
        assert percentile(samples, 100) == 10.0
        assert percentile(samples, 0) == 1.0

    def test_summary_shape_and_order(self):
        s = summarize([0.001, 0.002, 0.003, 0.004, 0.005])
        assert s["n"] == 5
        assert s["p50_ms"] <= s["p95_ms"] <= s["p99_ms"]
        assert s["min_ms"] <= s["max_ms"]
        assert summarize([])["n"] == 0


class TestMeasuredPaths:
    def test_every_path_runs_hermetically(self):
        assert len(tool_dispatch_latency(3)) == 3
        assert len(controller_facade_latency(3)) == 3
        assert len(memory_store_latency(3)) == 3
        assert len(wizard_parse_latency(3)) == 3

    def test_samples_are_real_timings(self):
        for samples in (tool_dispatch_latency(5), controller_facade_latency(5),
                        memory_store_latency(5), wizard_parse_latency(3)):
            assert all(s >= 0.0 for s in samples)
            assert sum(samples) > 0.0


class TestGate:
    def test_full_gate_report_shape_and_bounds(self, tmp_path):
        out = tmp_path / "orbit.json"
        report = run_orbit_gate(iterations=4, json_path=out, quiet=True)
        assert report["benchmark"] == "orbit-latency-gate"
        assert set(report["phases"]) == set(_GENEROUS_P99_CEILINGS)
        # Every phase obeys the percentile order and the generous ceiling.
        for name, summary in report["phases"].items():
            assert summary["n"] == 4
            assert summary["p50_ms"] <= summary["p95_ms"] <= summary["p99_ms"]
            assert summary["p99_ms"] / 1000 < _GENEROUS_P99_CEILINGS[name], name

    def test_json_artifact_round_trips(self, tmp_path):
        out = tmp_path / "orbit.json"
        run_orbit_gate(iterations=2, json_path=out, quiet=True)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["phases"]["tool_dispatch"]["p50_ms"] >= 0
        assert isinstance(data["phases"]["memory_store"]["p99_ms"], float)
        assert not math.isnan(data["phases"]["wizard_parse_100"]["p95_ms"])
