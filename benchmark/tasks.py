"""Fixed benchmark tasks for the JARVIS performance harness.

Each task records the plan's full metric set:

    task_id, provider, model, iterations, LLM_calls, tool_calls,
    parallel_tool_calls, input_tokens, output_tokens, context_tokens,
    memory_latency, tool_latency, LLM_latency, total_latency,
    RAM_peak, CPU_peak

``kind`` splits the two execution modes:

- ``deterministic`` — answerable without an LLM. The offline harness runs the
  ``steps`` straight through the permission engine + tool executor and checks
  the result against ``expected``. These are the Phase 3 deterministic path.
- ``agent`` — requires an LLM; only run in ``--online`` mode (skipped when no
  provider is available).
"""

from __future__ import annotations

from typing import Any

# Per-task fields required by the optimization plan's baseline record.
TASK_FIELDS: tuple[str, ...] = (
    "task_id",
    "provider",
    "model",
    "iterations",
    "LLM_calls",
    "tool_calls",
    "parallel_tool_calls",
    "input_tokens",
    "output_tokens",
    "context_tokens",
    "memory_latency",
    "tool_latency",
    "LLM_latency",
    "total_latency",
    "RAM_peak",
    "CPU_peak",
)


BENCHMARK_TASKS: list[dict[str, Any]] = [
    {
        "id": "git-branch",
        "goal": "What is the current Git branch?",
        "kind": "deterministic",
        "tools": ["shell.execute"],
        # Branch name varies per checkout; None = any non-empty output.
        "expected": None,
        "steps": [
            {"tool": "shell.execute", "args": {"executable": "git", "args": ["branch", "--show-current"]}},
        ],
    },
    {
        "id": "file-read",
        "goal": "Read pyproject.toml and report the ruff line-length.",
        "kind": "deterministic",
        "tools": ["filesystem.read"],
        "expected": "line-length",
        "steps": [
            {"tool": "filesystem.read", "args": {"path": "pyproject.toml"}},
        ],
    },
    {
        "id": "dir-list",
        "goal": "List the top-level files of the project.",
        "kind": "deterministic",
        "tools": ["filesystem.list"],
        "expected": "pyproject.toml",
        "steps": [
            {"tool": "filesystem.list", "args": {"path": "."}},
        ],
    },
    {
        "id": "system-status",
        "goal": "Report host CPU and RAM usage.",
        "kind": "deterministic",
        "tools": ["system.status"],
        "expected": "",
        "steps": [
            {"tool": "system.status", "args": {}},
        ],
    },
    {
        "id": "context-iteration",
        "goal": "Simulated agent iteration: context build + one tool call (offline).",
        "kind": "deterministic",
        "tools": ["filesystem.read"],
        "expected": "",
        "steps": [
            {"tool": "filesystem.read", "args": {"path": "pyproject.toml"}},
        ],
    },
    # ── LLM tasks (online only) ──────────────────────────────────────
    {
        "id": "explain-function",
        "goal": "Explain the purpose of core/agent/loop.py.",
        "kind": "agent",
        "tools": ["filesystem.read"],
    },
    {
        "id": "implement-feature",
        "goal": "Add a --version flag that prints the version to the benchmark runner.",
        "kind": "agent",
        "tools": ["filesystem.write"],
    },
    {
        "id": "fix-failing-test",
        "goal": "Run the test suite and fix any failing tests.",
        "kind": "agent",
        "tools": ["shell.execute"],
    },
]


def get_task(task_id: str) -> dict[str, Any]:
    for task in BENCHMARK_TASKS:
        if task["id"] == task_id:
            return task
    raise KeyError(f"unknown benchmark task: {task_id!r}")


def deterministic_tasks() -> list[dict[str, Any]]:
    return [t for t in BENCHMARK_TASKS if t["kind"] == "deterministic"]


def agent_tasks() -> list[dict[str, Any]]:
    return [t for t in BENCHMARK_TASKS if t["kind"] == "agent"]
