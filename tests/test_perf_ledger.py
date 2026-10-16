"""Hermetic tests for the normalized performance ledger (P2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark import ledger  # noqa: E402


def _fake_startup() -> dict:
    return {
        "launcher_ms": 120.0,
        "kernel_ms": 340.0,
        "prompt_ready_ms": 125.0,
        "rss_mb": 210.5,
        "wall_ms": 700.0,
    }


def _fake_gate(**kwargs) -> dict:
    assert kwargs.get("quiet") is True
    return {
        "benchmark": "orbit-latency-gate",
        "iterations": kwargs.get("iterations", 25),
        "phases": {
            "tool_dispatch": {"n": 25, "min_ms": 1.0, "p50_ms": 2.0,
                              "p95_ms": 3.0, "p99_ms": 4.0, "max_ms": 5.0},
            "memory_store": {"n": 25, "min_ms": 0.1, "p50_ms": 0.2,
                             "p95_ms": 0.3, "p99_ms": 0.4, "max_ms": 0.5},
        },
    }


@pytest.fixture()
def patched(monkeypatch):
    monkeypatch.setattr(ledger, "measure_startup", _fake_startup)
    monkeypatch.setattr(ledger, "run_orbit_gate", _fake_gate)


def test_ledger_schema_shape(patched):
    led = ledger.build_ledger(iterations=25)
    assert led["schema_version"] == ledger.LEDGER_SCHEMA_VERSION
    assert led["cold_start_ms"] == {
        "launcher": 120.0, "kernel": 340.0, "prompt_ready": 125.0, "wall": 700.0,
    }
    assert led["memory_mb"]["idle_rss"] == 210.5
    assert set(led["latency_ms"]) == {"tool_dispatch", "memory_store"}
    assert led["latency_ms"]["tool_dispatch"] == {"n": 25, "p50": 2.0, "p95": 3.0, "p99": 4.0}


def test_ledger_latency_percentiles_are_flat(patched):
    led = ledger.build_ledger()
    for name, s in led["latency_ms"].items():
        assert set(s) == {"n", "p50", "p95", "p99"}
        assert s["p50"] <= s["p95"] <= s["p99"]


def test_write_ledger_roundtrip(patched, tmp_path):
    led = ledger.build_ledger()
    out = ledger.write_ledger(led, tmp_path / "ledger.json")
    assert out.exists()
    assert json.loads(out.read_text()) == led


def test_render_ledger_mentions_every_metric(patched):
    text = ledger.render_ledger(ledger.build_ledger())
    for token in ("Cold start", "Idle RAM", "Peak RAM", "tool_dispatch", "p99"):
        assert token in text


def test_cold_start_can_be_skipped(monkeypatch):
    def _boom():
        raise AssertionError("measure_startup should not run when disabled")

    monkeypatch.setattr(ledger, "measure_startup", _boom)
    monkeypatch.setattr(ledger, "run_orbit_gate", _fake_gate)
    led = ledger.build_ledger(measure_cold_start=False)
    assert led["cold_start_ms"]["launcher"] is None
    assert led["memory_mb"]["idle_rss"] is None
