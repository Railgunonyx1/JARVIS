"""Measurement harness for the JARVIS performance baseline (Phase 1).

Runs fixed deterministic tasks through the real permission gate + tool
executor (no LLM) so every number reflects the actual runtime pipeline:

    startup  → fresh-interpreter cold boot (subprocess probe)
    context  → AgentContextBuilder.build + token estimate
    memory   → retrieve + format_for_prompt latency
    provider → dry chain resolution (keys/circuit-breakers only, no network)
    task     → deterministic steps end-to-end, per-task metric record

``--online`` mode additionally runs full AgentLoop tasks (LLM) and captures
provider/model/iteration/token metrics from the returned state.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from benchmark.tasks import TASK_FIELDS, deterministic_tasks

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_STARTUP_PROBE = ROOT / "benchmark" / "_startup_probe.py"


class ResourceMonitor:
    """Samples RSS (MB) and CPU% of the current process during a block."""

    def __init__(self, interval: float = 0.05) -> None:
        self.interval = interval
        self.peak_rss_mb = 0.0
        self.peak_cpu = 0.0
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        import psutil

        proc = psutil.Process()
        self._stop = threading.Event()

        def _sample() -> None:
            while not self._stop.is_set():
                try:
                    rss = proc.memory_info().rss
                    if rss > self.peak_rss_mb * 1e6:
                        self.peak_rss_mb = rss / 1e6
                    cpu = proc.cpu_percent(interval=None)
                    if cpu > self.peak_cpu:
                        self.peak_cpu = cpu
                except Exception:
                    pass
                time.sleep(self.interval)

        self._thread = threading.Thread(target=_sample, daemon=True)
        self._thread.start()

    def stop(self) -> tuple[float, float]:
        if self._thread is not None and self._stop is not None:
            self._stop.set()
            self._thread.join(timeout=self.interval * 2 + 0.2)
        return round(self.peak_rss_mb, 1), round(self.peak_cpu, 1)

    def __enter__(self) -> "ResourceMonitor":
        self.start()
        return self

    def __exit__(self, *exc) -> bool:
        self.stop()
        return False


def _default_record(task_id: str) -> dict[str, Any]:
    record = {field: 0 for field in TASK_FIELDS}
    record["task_id"] = task_id
    record["provider"] = ""
    record["model"] = ""
    return record


def measure_startup() -> dict[str, Any]:
    """Fresh-interpreter cold boot: launcher import + kernel ready + idle RSS."""
    start = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(_STARTUP_PROBE)],
        capture_output=True, text=True, timeout=300, cwd=str(ROOT),
    )
    wall_ms = (time.perf_counter() - start) * 1000.0
    if proc.returncode != 0:
        raise RuntimeError(f"startup probe failed ({proc.returncode}):\n{proc.stderr[-2000:]}")
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    data = json.loads(lines[-1])
    data["wall_ms"] = round(wall_ms, 1)
    data["stdout_len"] = len(proc.stdout)
    return data


def measure_context_build(loop) -> dict[str, Any]:
    from core.context.budget import estimate_tokens

    goal = "Benchmark context construction with a realistic multi-step goal string."
    t0 = time.perf_counter()
    messages, system_prompt = loop.context_builder.build(goal, loop.project, loop.mem)
    ms = (time.perf_counter() - t0) * 1000.0
    tokens = estimate_tokens(system_prompt or "") + estimate_tokens(json.dumps(messages, default=str))
    return {
        "context_build_ms": round(ms, 2),
        "context_tokens": tokens,
        "tool_count": len(loop.registry.to_openai_tools()),
    }


def measure_memory(loop) -> dict[str, Any]:
    if loop.mem is None:
        return {"memory_retrieve_ms": 0.0, "memory_format_ms": 0.0, "memory_items": 0}
    project = str(loop.project.root_path)
    t0 = time.perf_counter()
    items = loop.mem.retrieve("git branch benchmark", project=project, top_k=3)
    retrieve_ms = (time.perf_counter() - t0) * 1000.0
    t0 = time.perf_counter()
    loop.mem.format_for_prompt(project, max_tokens=800)
    fmt_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "memory_retrieve_ms": round(retrieve_ms, 2),
        "memory_format_ms": round(fmt_ms, 2),
        "memory_items": len(items),
    }


def measure_provider_dry(loop) -> dict[str, Any]:
    router = loop.router
    t0 = time.perf_counter()
    chain = router._get_available_chain()
    ms = (time.perf_counter() - t0) * 1000.0
    return {
        "provider_chain_ms": round(ms, 2),
        "providers_available": len(chain),
        "providers": list(chain),
    }


async def _run_offline_task(loop, task: dict[str, Any]) -> dict[str, Any]:
    """Execute a deterministic task through permission gate + executor."""
    record = _default_record(task["id"])
    with ResourceMonitor() as monitor:
        trace_id = f"bench_{task['id']}"
        t0 = time.perf_counter()

        t = time.perf_counter()
        messages, system_prompt = loop.context_builder.build(task["goal"], loop.project, loop.mem)
        from core.context.budget import estimate_tokens
        record["context_tokens"] = estimate_tokens(system_prompt or "") + estimate_tokens(
            json.dumps(messages, default=str))
        context_ms = (time.perf_counter() - t) * 1000.0

        tool_ms = 0.0
        outputs: list[str] = []
        steps = task.get("steps", [])
        for step in steps:
            tool = loop.registry.get(step["tool"])
            if tool is None:
                raise RuntimeError(f"tool not registered: {step['tool']}")
            t = time.perf_counter()
            allowed, reason = await loop.permissions.check(tool, step["args"], trace_id)
            if not allowed:
                raise RuntimeError(f"permission denied for {step['tool']}: {reason}")
            result = await loop.executor.execute(step["tool"], step["args"], trace_id,
                                                 mode=loop.permissions.mode)
            tool_ms += (time.perf_counter() - t) * 1000.0
            if not result.success:
                raise RuntimeError(f"{step['tool']} failed: {result.error}")
            outputs.append(result.output or "")

        total_ms = (time.perf_counter() - t0) * 1000.0

    record["iterations"] = max(1, len(steps))
    record["tool_calls"] = len(steps)
    record["input_tokens"] = record["context_tokens"]
    record["tool_latency"] = round(tool_ms, 2)
    record["total_latency"] = round(total_ms, 2)
    record["RAM_peak"] = monitor.peak_rss_mb
    record["CPU_peak"] = monitor.peak_cpu

    expected = task.get("expected", "")
    if expected and not any(expected in out for out in outputs):
        joined = " | ".join(outputs)[:200]
        raise RuntimeError(f"task {task['id']}: expected {expected!r}, got {joined!r}")
    return record


async def _simulated_iteration(loop, task: dict[str, Any]) -> dict[str, Any]:
    """Offline agent-iteration probe: context build + permission + one tool call."""
    record = _default_record(task["id"])
    with ResourceMonitor() as monitor:
        t0 = time.perf_counter()
        t = time.perf_counter()
        messages, system_prompt = loop.context_builder.build(task["goal"], loop.project, loop.mem)
        from core.context.budget import estimate_tokens
        record["context_tokens"] = estimate_tokens(system_prompt or "") + estimate_tokens(
            json.dumps(messages, default=str))
        t = time.perf_counter()
        tool = loop.registry.get("filesystem.read")
        allowed, reason = await loop.permissions.check(tool, {"path": "pyproject.toml"}, "bench_iter")
        if not allowed:
            raise RuntimeError(f"permission denied in simulated iteration: {reason}")
        result = await loop.executor.execute("filesystem.read", {"path": "pyproject.toml"},
                                             "bench_iter", mode=loop.permissions.mode)
        tool_ms = (time.perf_counter() - t) * 1000.0
        total_ms = (time.perf_counter() - t0) * 1000.0
        if not result.success:
            raise RuntimeError(f"filesystem.read failed: {result.error}")

    record["iterations"] = 1
    record["tool_calls"] = 1
    record["input_tokens"] = record["context_tokens"]
    record["tool_latency"] = round(tool_ms, 2)
    record["total_latency"] = round(total_ms, 2)
    record["RAM_peak"] = monitor.peak_rss_mb
    record["CPU_peak"] = monitor.peak_cpu
    return record


async def _run_online_task(loop, task: dict[str, Any]) -> dict[str, Any]:
    """Full AgentLoop.run with the LLM; metrics pulled from the returned state."""
    record = _default_record(task["id"])
    with ResourceMonitor() as monitor:
        t0 = time.perf_counter()
        result = await loop.run(task["goal"], session_id="bench")
        total_ms = (time.perf_counter() - t0) * 1000.0
    record["success"] = bool(result.success)
    record["error"] = result.error[:200] if result.error else ""
    state = result.state
    record["provider"] = state.provider
    record["model"] = state.model
    record["iterations"] = state.iteration
    record["LLM_calls"] = max(1, state.iteration)
    record["tool_calls"] = len(state.tool_calls)
    record["input_tokens"] = state.tokens_used
    usage = state.context_usage or {}
    record["context_tokens"] = usage.get("total_tokens", state.tokens_used) or state.tokens_used
    record["total_latency"] = round(total_ms, 2)
    record["RAM_peak"] = monitor.peak_rss_mb
    record["CPU_peak"] = monitor.peak_cpu
    return record


def run_offline_benchmark() -> dict[str, Any]:
    """Full offline pass: startup + microbenchmarks + deterministic tasks."""
    from runtime.kernel import build_kernel, close_kernel

    loop = build_kernel("agent", 10)
    try:
        startup = measure_startup()
        micro: dict[str, Any] = {}
        micro.update(measure_context_build(loop))
        micro.update(measure_memory(loop))
        micro.update(measure_provider_dry(loop))

        tasks = []
        for task in deterministic_tasks():
            if task["id"] == "context-iteration":
                record = asyncio.run(_simulated_iteration(loop, task))
            else:
                record = asyncio.run(_run_offline_task(loop, task))
            tasks.append(record)

        return {"startup": startup, "micro": micro, "tasks": tasks, "online": False}
    finally:
        close_kernel(loop)


def run_online_benchmark() -> dict[str, Any]:
    """Online pass: full AgentLoop tasks (requires a configured LLM provider)."""
    from providers.router import ProviderRouter
    from runtime.kernel import build_kernel, close_kernel

    loop = build_kernel("agent", 10)
    try:
        if not loop.router._get_available_chain():
            raise RuntimeError("No LLM providers available — online benchmark skipped.")
        from benchmark.tasks import agent_tasks
        tasks = [asyncio.run(_run_online_task(loop, task)) for task in agent_tasks()]
        return {"startup": measure_startup(), "micro": {}, "tasks": tasks, "online": True}
    finally:
        close_kernel(loop)
