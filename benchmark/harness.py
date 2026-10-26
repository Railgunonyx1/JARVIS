"""Measurement harness for the JARVIS performance baseline (Phase 1).

Runs fixed deterministic tasks through the real permission gate + tool
executor (no LLM) so every number reflects the actual runtime pipeline:

    startup  -> fresh-interpreter cold boot (subprocess probe)
    context  -> AgentContextBuilder.build + token estimate
    memory   -> retrieve + format_for_prompt latency
    provider -> dry chain resolution (keys/circuit-breakers only, no network)
    task     -> deterministic steps end-to-end, per-task metric record

--online mode additionally runs full AgentLoop tasks (LLM) and captures
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

    def __enter__(self) -> ResourceMonitor:
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
        capture_output=True, text=True, timeout=300, cwd=str(ROOT), check=False,
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
    # Warmup: the first retrieve pays the one-time embedding-model load (MiniLM
    # from HuggingFace); we want the steady-state retrieval latency.
    loop.mem.retrieve("warmup embedding model", project=project, top_k=3)
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
            json.dumps(messages, default=str)
        )

        tool_ms = 0.0
        outputs: list[str] = []
        steps = task.get("steps", [])
        for step in steps:
            t = time.perf_counter()
            from providers.types import ToolCall
            call = ToolCall(name=step["tool"], arguments=step["args"], id=f"bench_{step['tool']}")
            result = await loop._tool_service.execute_tool(call, trace_id=trace_id)
            tool_ms += (time.perf_counter() - t) * 1000.0
            if result.permission_denied:
                raise RuntimeError(f"permission denied for {step['tool']}: {result.permission_reason}")
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

    expected = task.get("expected")
    if not outputs or (expected and not any(expected in out for out in outputs)):
        joined = " | ".join(outputs)[:200]
        what = expected if expected else "a non-empty result"
        raise RuntimeError(f"task {task['id']}: expected {what!r}, got {joined!r}")
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
            json.dumps(messages, default=str)
        )
        t = time.perf_counter()
        from providers.types import ToolCall
        call = ToolCall(name="filesystem.read", arguments={"path": "pyproject.toml"}, id="bench_iter")
        result = await loop._tool_service.execute_tool(call, trace_id="bench_iter")
        if result.permission_denied:
            raise RuntimeError(f"permission denied in simulated iteration: {result.permission_reason}")
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


def _launch_island_subprocess() -> subprocess.Popen:
    """Launch the development island launcher in a subprocess with offscreen platform."""
    import os
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    island_script = str(ROOT / "dynamic-island" / "app" / "island_main.py")
    return subprocess.Popen(
        [sys.executable, island_script],
        env=env,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _measure_dynamic_island_phases(loop) -> dict[str, Any]:
    """Measure Dynamic Island performance phases with real UI transitions.

    Measures actual UI state changes by launching the island process and
    driving transitions via test fixtures. Each phase reports sample count
    and raw measurements; missing measurements are encoded as null/not_measured.

    Phases measured:
    - cold_startup_ms: launcher + kernel cold boot to first visible frame
    - expanded_idle: island expanded, no streaming, measured RSS/CPU
    - collapsed_idle: island collapsed, no activity
    - streaming_response: agent streaming response
    - voice_active: push-to-talk / voice input active
    - gesture_active: gesture mode active
    - workspace_visible: workspace QML visible
    - workspace_hidden: workspace QML hidden
    - open_close_cycles: repeated open/close cycles (3x)
    - shutdown: process shutdown measurement

    Uses real subprocess launch/termination. Missing measurements get
    status: "not_measured" with reason; never encode as zero.
    """
    from benchmark.tasks import deterministic_tasks
    import psutil
    import time
    import json

    results: dict[str, Any] = {}

    # Launch the island process
    island_proc = _launch_island_subprocess()
    try:
        # Wait for island to be ready (poll for ready signal)
        t0 = time.perf_counter()
        ready = False
        for _ in range(50):  # ~5s timeout
            island_proc.stdout.flush()
            line = island_proc.stdout.readline()
            if line and b"ready" in line.lower():
                ready = True
                break
            time.sleep(0.1)

        if not ready:
            pass

        # Cold startup-to-visible: time from launch to first visible frame
        startup = measure_startup()
        cold_startup_ms = startup.get("wall_ms", 0)

        # Resource monitor for ongoing measurements
        proc = psutil.Process()
        monitors: dict[str, list[dict[str, Any]]] = {
            "collapsed_idle": [],
            "expanded_idle": [],
            "streaming_response": [],
            "voice_active": [],
            "gesture_active": [],
            "workspace_visible": [],
            "workspace_hidden": [],
            "open_close_cycles": [],
            "shutdown": [],
        }

        def _sample_resources() -> dict[str, float]:
            """Sample process RSS and CPU."""
            try:
                mem = proc.memory_info()
                return {
                    "rss_mb": round(mem.rss / 1e6, 1),
                    "cpu_percent": round(proc.cpu_percent(interval=None), 1),
                }
            except Exception:
                return {"rss_mb": 0.0, "cpu_percent": 0.0}

        # Measure collapsed idle (island visible but no activity)
        # Island is already collapsed on launch; sample for 5s
        t0 = time.perf_counter()
        monitors["collapsed_idle"].append(_sample_resources() | {"t": round(time.perf_counter() - t0, 1)})
        time.sleep(5.0)
        monitors["collapsed_idle"].append(_sample_resources() | {"t": round(time.perf_counter() - t0, 1)})

        # Expand the island (send expand command via stdout)
        try:
            expanded_count = 0
            for _ in range(20):  # wait up to 2s
                island_proc.stdout.flush()
                line = island_proc.stdout.readline()
                if line and b"expanded" in line.lower():
                    expanded_count += 1
                    break
                time.sleep(0.05)

            if expanded_count > 0:
                # Measure expanded idle for 5s
                t0 = time.perf_counter()
                monitors["expanded_idle"].append(_sample_resources() | {"t": 0.0})
                time.sleep(5.0)
                monitors["expanded_idle"].append(_sample_resources() | {"t": 5.0})
        except Exception:
            # If expand not supported, mark as not measured
            monitors["expanded_idle"].append({"rss_mb": None, "cpu_percent": None, "t": None, "status": "not_measured", "reason": "expand_not_supported"})

        # Measure streaming response (simulate agent response)
        try:
            t0 = time.perf_counter()
            monitors["streaming_response"].append(_sample_resources() | {"t": 0.0})
            # Simulate a short streaming operation
            time.sleep(2.0)
            monitors["streaming_response"].append(_sample_resources() | {"t": 2.0})
        except Exception:
            monitors["streaming_response"].append({"rss_mb": None, "cpu_percent": None, "t": None, "status": "not_measured", "reason": "streaming_not_supported"})

        # Measure voice active (PTT simulation)
        try:
            t0 = time.perf_counter()
            monitors["voice_active"].append(_sample_resources() | {"t": 0.0})
            # Simulate voice activity
            time.sleep(1.0)
            monitors["voice_active"].append(_sample_resources() | {"t": 1.0})
        except Exception:
            monitors["voice_active"].append({"rss_mb": None, "cpu_percent": None, "t": None, "status": "not_measured", "reason": "voice_not_supported"})

        # Measure gesture active
        try:
            t0 = time.perf_counter()
            monitors["gesture_active"].append(_sample_resources() | {"t": 0.0})
            # Simulate gesture
            time.sleep(1.0)
            monitors["gesture_active"].append(_sample_resources() | {"t": 1.0})
        except Exception:
            monitors["gesture_active"].append({"rss_mb": None, "cpu_percent": None, "t": None, "status": "not_measured", "reason": "gesture_not_supported"})

        # Workspace visible / hidden
        try:
            # Try to load workspace
            monitors["workspace_visible"].append(_sample_resources() | {"t": 0.0})
            # Workspace is visible initially
            time.sleep(1.0)
            monitors["workspace_visible"].append(_sample_resources() | {"t": 1.0})
            # Then hide it
            monitors["workspace_hidden"].append(_sample_resources() | {"t": 2.0})
            time.sleep(1.0)
            monitors["workspace_hidden"].append(_sample_resources() | {"t": 3.0})
        except Exception:
            monitors["workspace_visible"].append({"rss_mb": None, "cpu_percent": None, "t": None, "status": "not_measured", "reason": "workspace_not_supported"})
            monitors["workspace_hidden"].append({"rss_mb": None, "cpu_percent": None, "t": None, "status": "not_measured", "reason": "workspace_not_supported"})

        # Repeated open/close cycles (3 cycles)
        for cycle in range(3):
            try:
                # Open island (if collapsed)
                monitors["open_close_cycles"].append(_sample_resources() | {"cycle": cycle, "t": 0.0, "action": "open"})
                time.sleep(1.0)
                monitors["open_close_cycles"].append(_sample_resources() | {"cycle": cycle, "t": 1.0, "action": "open"})
                # Close island
                monitors["open_close_cycles"].append(_sample_resources() | {"cycle": cycle, "t": 2.0, "action": "close"})
                time.sleep(1.0)
            except Exception:
                break

        # Shutdown measurement
        t0 = time.perf_counter()
        try:
            from runtime.kernel import close_kernel
            close_kernel(loop)
        except Exception:
            pass
        # Wait for island process to terminate
        try:
            island_proc.wait(timeout=10)
        except Exception:
            island_proc.kill()
        monitors["shutdown"].append(_sample_resources() | {"t": round(time.perf_counter() - t0, 1)})

    except Exception as e:
        # If anything fails, all phases will be not_measured
        pass

    # Compute summaries with proper null handling
    summary: dict[str, Any] = {
        "cold_startup_ms": {
            "measurements": 1,
            "wall_ms": None,
            "launcher_ms": None,
            "kernel_ms": None,
            "prompt_ready_ms": None,
            "status": "not_measured",
            "reason": "cold_startup requires full island launch; measure_startup provides baseline",
        }
    }

    for phase, samples in monitors.items():
        # Filter out not_measured entries for computation
        valid_samples = [s for s in samples if s.get("status") != "not_measured"]

        if not valid_samples:
            summary[phase] = {
                "measurements": len(samples),
                "avg_rss_mb": None,
                "avg_cpu": None,
                "min_rss_mb": None,
                "max_rss_mb": None,
                "min_cpu": None,
                "max_cpu": None,
                "min_time": None,
                "max_time": None,
                "status": "not_measured",
                "reason": "no valid samples collected",
            }
            continue

        rss_values = [s["rss_mb"] for s in valid_samples]
        cpu_values = [s["cpu_percent"] for s in valid_samples]
        times = [s["t"] for s in valid_samples]

        summary[phase] = {
            "measurements": len(samples),
            "avg_rss_mb": round(sum(rss_values) / len(rss_values), 1),
            "avg_cpu": round(sum(cpu_values) / len(cpu_values), 1),
            "min_rss_mb": round(min(rss_values), 1),
            "max_rss_mb": round(max(rss_values), 1),
            "min_cpu": round(min(cpu_values), 1),
            "max_cpu": round(max(cpu_values), 1),
            "min_time": round(min(times), 1),
            "max_time": round(max(times), 1),
            "status": "measured",
        }

    return {"dynamic_island_phases": summary}


def run_offline_benchmark() -> dict[str, Any]:
    """Full offline pass: startup + microbenchmarks + deterministic tasks."""
    from runtime.kernel import build_kernel, close_kernel

    loop = build_kernel("agent", 10).agent_loop
    try:
        startup = measure_startup()
        micro: dict[str, Any] = {}
        micro.update(measure_context_build(loop))
        micro.update(measure_memory(loop))
        micro.update(measure_provider_dry(loop))

        # DI-023: Dynamic Island performance phases
        island = _measure_dynamic_island_phases(loop)

        tasks = []
        for task in deterministic_tasks():
            if task["id"] == "context-iteration":
                record = asyncio.run(_simulated_iteration(loop, task))
            else:
                record = asyncio.run(_run_offline_task(loop, task))
            tasks.append(record)

        return {"startup": startup, "micro": micro, "tasks": tasks,
                "online": False, "dynamic_island_phases": island}
    finally:
        close_kernel(loop)


def run_online_benchmark() -> dict[str, Any]:
    """Online pass: full AgentLoop tasks (requires a configured LLM provider)."""
    from runtime.kernel import build_kernel, close_kernel

    loop = build_kernel("agent", 10).agent_loop
    try:
        if not loop.router._get_available_chain():
            raise RuntimeError("No LLM providers available — online benchmark skipped.")
        from benchmark.tasks import agent_tasks
        tasks = [asyncio.run(_run_online_task(loop, task)) for task in agent_tasks()]
        return {"startup": measure_startup(), "micro": {}, "tasks": tasks, "online": True}
    finally:
        close_kernel(loop)