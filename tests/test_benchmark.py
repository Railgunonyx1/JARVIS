"""Tests for the benchmark harness, report, and regression gate (Phase 1)."""

from __future__ import annotations

import pytest


def _synthetic_data(tasks=None):
    tasks = tasks or [
        {"task_id": "git-branch", "provider": "", "model": "", "iterations": 1,
         "LLM_calls": 0, "tool_calls": 1, "parallel_tool_calls": 0,
         "input_tokens": 700, "output_tokens": 0, "context_tokens": 700,
         "memory_latency": 0.0, "tool_latency": 100.0, "LLM_latency": 0.0,
         "total_latency": 101.0, "RAM_peak": 100.0, "CPU_peak": 10.0},
    ]
    return {
        "online": False,
        "startup": {"launcher_ms": 200.0, "kernel_ms": 300.0, "prompt_ready_ms": 205.0, "rss_mb": 50.0},
        "micro": {"context_build_ms": 1.0, "memory_retrieve_ms": 5.0,
                  "provider_chain_ms": 0.1, "providers_available": 2},
        "tasks": tasks,
    }


# ── task definitions ───────────────────────────────────────────────────

def test_task_registry_schema():
    from benchmark.tasks import BENCHMARK_TASKS

    ids = [t["id"] for t in BENCHMARK_TASKS]
    assert len(ids) == len(set(ids)), "task ids must be unique"
    for task in BENCHMARK_TASKS:
        assert {"id", "goal", "kind", "tools"} <= set(task)
        assert task["kind"] in ("deterministic", "agent")
        if task["kind"] == "deterministic":
            assert task["steps"], f"{task['id']} needs steps"
            assert "expected" in task
        assert set(task["tools"]) <= {"shell.execute", "filesystem.read", "filesystem.list",
                                      "filesystem.write", "system.status"}


def test_get_task_unknown():
    from benchmark.tasks import get_task

    with pytest.raises(KeyError):
        get_task("nope")


# ── report ─────────────────────────────────────────────────────────────

def test_render_baseline_has_headline_numbers():
    from benchmark.report import render_baseline

    text = render_baseline(_synthetic_data())
    assert "JARVIS PERFORMANCE BASELINE" in text
    for needle in ("Startup", "Idle RAM", "Task", "Tool calls", "Context"):
        assert needle in text


def test_render_task_table_all_fields():
    from benchmark.report import render_task_table

    text = render_task_table(_synthetic_data()["tasks"])
    assert "task_id" in text
    assert "git-branch" in text


def test_summarize_counts():
    from benchmark.report import summarize

    s = summarize(_synthetic_data())
    assert s["startup_ms"] == 200.0
    assert s["idle_ram_mb"] == 50.0
    assert s["llm_calls"] == 0
    assert s["tool_calls"] == 1
    assert s["online"] is False


# ── regression gate ────────────────────────────────────────────────────

def _gate_data(startup_ms=200.0, context_build=1.0, tool_latency=100.0):
    data = _synthetic_data()
    data["startup"]["launcher_ms"] = startup_ms
    data["micro"]["context_build_ms"] = context_build
    data["tasks"][0]["tool_latency"] = tool_latency
    data["tasks"][0]["total_latency"] = tool_latency + 1.0
    return data


def test_gate_pass_when_within_thresholds():
    from benchmark.gate import check_regression

    current = _gate_data()
    baseline = _gate_data()
    assert check_regression(current, baseline) == []


def test_gate_fails_on_startup_regression():
    from benchmark.gate import check_regression

    current = _gate_data(startup_ms=260.0)  # +30% > 20% fail
    baseline = _gate_data(startup_ms=200.0)
    issues = check_regression(current, baseline)
    assert any(i["metric"] == "startup_ms" and i["level"] == "fail" for i in issues)


def test_gate_warns_on_ram_increase():
    from benchmark.gate import check_regression

    current = _gate_data()
    current["startup"]["rss_mb"] = 60.0  # +20% > 15% warn
    baseline = _gate_data()
    issues = check_regression(current, baseline)
    assert any(i["metric"] == "idle_ram_mb" and i["level"] == "warn" for i in issues)


def test_gate_strict_promotes_warnings():
    from benchmark.gate import check_regression

    current = _gate_data()
    current["startup"]["rss_mb"] = 60.0
    baseline = _gate_data()
    issues = check_regression(current, baseline, strict=True)
    assert any(i["metric"] == "idle_ram_mb" and i["level"] == "fail" for i in issues)


def test_gate_min_abs_floors_subms_noise():
    from benchmark.gate import check_regression

    # 0.8ms vs 1.1ms is >20% but below the 2ms floor → no issue.
    current = _gate_data(context_build=1.1)
    baseline = _gate_data(context_build=0.8)
    assert check_regression(current, baseline) == []


# ── run merge ──────────────────────────────────────────────────────────

def test_merge_runs_averages_numerics():
    from benchmark.run import _merge_runs

    a = _synthetic_data()
    b = _synthetic_data()
    a["startup"]["launcher_ms"] = 100.0
    b["startup"]["launcher_ms"] = 200.0
    merged = _merge_runs([a, b])
    assert merged["startup"]["launcher_ms"] == 150.0
    assert merged["tasks"][0]["total_latency"] == 101.0  # same in both


# ── runtime singleton reopen (found by --repeats) ──────────────────────

def test_mem_singleton_reopens_after_close():
    """get_mem() must return a working instance after close(); the module
    singletons were left pointing at closed backends, crashing the second
    kernel build in one process (benchmark --repeats 2)."""
    from memory.api import get_mem

    first = get_mem()
    first.close()
    second = get_mem()
    try:
        # Knowledge + decisions backends must be live, not the closed instances.
        assert second._controller._knowledge._conn is not None
        assert second._controller._decisions._conn is not None
        assert isinstance(second.format_for_prompt(""), str)
        assert isinstance(second.retrieve("reopen test"), list)
    finally:
        second.close()
