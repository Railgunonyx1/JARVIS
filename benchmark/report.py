"""Baseline report rendering + JSON persistence for the benchmark harness."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from benchmark.tasks import TASK_FIELDS

REPORT_DIR = Path(__file__).resolve().parent / "results"


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    """Extract the plan's headline numbers from a benchmark result dict."""
    startup = data.get("startup", {})
    micro = data.get("micro", {})
    tasks = data.get("tasks", [])
    if tasks:
        total_latency = sum(t.get("total_latency", 0) for t in tasks)
        task_sec = round(total_latency / len(tasks) / 1000.0, 3)
        llm_calls = sum(t.get("LLM_calls", 0) for t in tasks)
        tool_calls = sum(t.get("tool_calls", 0) for t in tasks)
        context_tokens = sum(t.get("context_tokens", 0) for t in tasks) / max(1, len(tasks))
    else:
        task_sec = 0.0
        llm_calls = 0
        tool_calls = 0
        context_tokens = 0

    online = data.get("online", False)
    return {
        "startup_ms": round(startup.get("launcher_ms", 0.0), 1),
        "kernel_ms": round(startup.get("kernel_ms", 0.0), 1),
        "prompt_ready_ms": round(startup.get("prompt_ready_ms", 0.0), 1),
        "idle_ram_mb": round(startup.get("rss_mb", 0.0), 1),
        "context_build_ms": round(micro.get("context_build_ms", 0.0), 2),
        "memory_retrieve_ms": round(micro.get("memory_retrieve_ms", 0.0), 2),
        "provider_chain_ms": round(micro.get("provider_chain_ms", 0.0), 2),
        "providers_available": int(micro.get("providers_available", 0)),
        "task_sec": task_sec,
        "llm_calls": int(llm_calls),
        "tool_calls": int(tool_calls),
        "context_tokens": int(context_tokens),
        "online": bool(online),
    }


def render_baseline(data: dict[str, Any]) -> str:
    """Render the plan's baseline report block."""
    s = summarize(data)
    ttft = "n/a (offline)" if not s["online"] else "see task records"
    lines = [
        "JARVIS PERFORMANCE BASELINE",
        "────────────────────────────",
        f"Startup (launcher): {s['startup_ms']:>7.1f} ms",
        f"Kernel ready:       {s['kernel_ms']:>7.1f} ms",
        f"Prompt-ready (est): {s['prompt_ready_ms']:>7.1f} ms",
        f"Idle RAM:           {s['idle_ram_mb']:>7.1f} MB",
        f"TTFT:               {ttft}",
        f"Task (avg):         {s['task_sec']:>7.3f} sec",
        f"LLM calls:          {s['llm_calls']:>7d}",
        f"Tool calls:         {s['tool_calls']:>7d}",
        f"Context (avg):      {s['context_tokens']:>7d} tokens",
        f"Context build:      {s['context_build_ms']:>7.2f} ms",
        f"Memory retrieve:    {s['memory_retrieve_ms']:>7.2f} ms",
        f"Provider chain:     {s['provider_chain_ms']:>7.2f} ms",
        f"Providers online:   {s['providers_available']:>7d}",
    ]
    return "\n".join(lines)


def render_task_table(tasks: list[dict[str, Any]]) -> str:
    """One line per task with the full Phase-1 metric set."""
    header = "  " + " | ".join(TASK_FIELDS)
    lines = ["PER-TASK RECORDS", header, "-" * 40]
    for task in tasks:
        cells = []
        for field in TASK_FIELDS:
            value = task.get(field, 0)
            if isinstance(value, float):
                cells.append(f"{value:.2f}")
            else:
                cells.append(str(value))
        lines.append("  " + " | ".join(cells))
    return "\n".join(lines)


def default_output_path() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return REPORT_DIR / f"benchmark_{stamp}.json"


def write_json(data: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
