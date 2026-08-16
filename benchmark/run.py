"""Benchmark runner CLI — Python -m benchmark.run.

Offline (default, no LLM required):

    python -m benchmark.run --offline --repeats 3 --baseline benchmark/baseline.json

Online (requires a configured LLM provider):

    python -m benchmark.run --online
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.report import (  # noqa: E402
    default_output_path,
    load_json,
    render_baseline,
    render_task_table,
    write_json,
)

VERSION = "0.1.0"


def _merge_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Average numeric fields across repeat runs; keep the last strings."""
    if not runs:
        return {}
    merged = {"tasks": [], "online": runs[0].get("online", False)}
    for key in ("startup", "micro"):
        buckets: dict[str, list[Any]] = {}
        for run in runs:
            block = run.get(key) or {}
            for k, v in block.items():
                buckets.setdefault(k, []).append(v)
        merged[key] = {
            k: round(sum(float(v) for v in vals) / len(vals), 4) if isinstance(vals[0], (int, float)) else vals[-1]
            for k, vals in buckets.items()
        }
    n = len(runs)
    for i, task in enumerate(runs[0]["tasks"]):
        merged_task: dict[str, Any] = {}
        for field in task:
            vals = [r["tasks"][i][field] for r in runs]
            if all(isinstance(v, (int, float)) for v in vals):
                merged_task[field] = round(sum(float(v) for v in vals) / n, 3)
            else:
                merged_task[field] = vals[-1]
        merged["tasks"].append(merged_task)
    return merged


def _filter_tasks(data: dict[str, Any], task_ids: list[str]) -> dict[str, Any]:
    if not task_ids:
        return data
    wanted = set(task_ids)
    data = dict(data)
    data["tasks"] = [t for t in data["tasks"] if t["task_id"] in wanted]
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="benchmark", description="JARVIS performance benchmark.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="Deterministic tasks, no LLM (default).")
    mode.add_argument("--online", action="store_true", help="Full AgentLoop tasks via the LLM.")
    parser.add_argument("--repeats", type=int, default=1, help="Repeat the benchmark and average (default 1).")
    parser.add_argument("--save", type=str, default=None, help="Output JSON path (default benchmark/results/...).")
    parser.add_argument("--baseline", type=str, default=None, help="Also write this path as the committed baseline.")
    parser.add_argument("--tasks", type=str, default="", help="Comma-separated task ids to run.")
    parser.add_argument("--quiet", action="store_true", help="Suppress the report; only write JSON.")
    parser.add_argument("--version", action="version", version=f"benchmark {VERSION}")
    args = parser.parse_args(argv)

    if args.repeats < 1:
        parser.error("--repeats must be >= 1")

    from benchmark import harness

    task_ids = [t.strip() for t in args.tasks.split(",") if t.strip()]
    if args.online:
        data = harness.run_online_benchmark()
        data = _filter_tasks(data, task_ids)
        runs = [data]
    else:
        runs = [harness.run_offline_benchmark() for _ in range(args.repeats)]
        data = _merge_runs(runs)
        data = _filter_tasks(data, task_ids)

    out_path = Path(args.save) if args.save else default_output_path()
    write_json(data, out_path)

    if args.baseline:
        write_json(data, args.baseline)
        print(f"baseline written: {args.baseline}")

    if not args.quiet:
        print()
        print(render_baseline(data))
        print()
        print(render_task_table(data["tasks"]))
    print(f"saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
