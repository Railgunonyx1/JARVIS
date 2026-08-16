"""Performance regression gate (Phase 22).

Compares a fresh benchmark run against a committed baseline and fails when a
metric regresses beyond its threshold:

    startup regression   > 20%  → FAIL
    kernel boot regression > 20% → FAIL
    idle RAM increase    > 15%  → WARN
    context build        > 20%  → WARN
    memory retrieve      > 20%  → WARN
    tool latency (avg)   > 20%  → WARN
    task latency (avg)   > 20%  → WARN (FAIL with --strict)
    context tokens       > 20%  → WARN

Exit code: 0 = pass, 1 = fail. --strict promotes warnings to failures.

Usage:
    python -m benchmark.gate --baseline benchmark/baseline.json
    python -m benchmark.gate --baseline benchmark/baseline.json --strict
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.report import load_json, summarize  # noqa: E402

DEFAULT_THRESHOLDS: dict[str, dict[str, float]] = {
    "startup_ms": {"fail": 0.20},
    "kernel_ms": {"fail": 0.20},
    "idle_ram_mb": {"warn": 0.15},
    # min_abs floors the relative check: a 20% swing on a ~1ms operation is
    # machine noise, not a regression.
    "context_build_ms": {"warn": 0.20, "min_abs": 2.0},
    "memory_retrieve_ms": {"warn": 0.20, "min_abs": 2.0},
    "tool_latency_ms": {"warn": 0.20, "min_abs": 5.0},
    "task_sec": {"warn": 0.20},
    "context_tokens": {"warn": 0.20},
}

# Machine-specific timing metrics. The committed baseline is captured on the
# developer machine, so in CI these deltas are warn-only (never fail).
TIMING_METRICS = frozenset({
    "startup_ms", "kernel_ms", "idle_ram_mb", "context_build_ms",
    "memory_retrieve_ms", "tool_latency_ms", "task_sec",
})


def check_regression(
    current: dict[str, Any],
    baseline: dict[str, Any],
    strict: bool = False,
    thresholds: dict[str, dict[str, float]] | None = None,
) -> list[dict[str, Any]]:
    """Return issues [{metric, current, baseline, delta_pct, level}], empty if clean."""
    thresholds = thresholds or DEFAULT_THRESHOLDS
    cur = summarize(current)
    base = summarize(baseline)

    avg_tool_latency = None
    for task in current.get("tasks", []):
        if "tool_latency" in task:
            vals = [t.get("tool_latency", 0.0) for t in current["tasks"] if "tool_latency" in t]
            avg_tool_latency = sum(vals) / len(vals) if vals else 0.0
    if avg_tool_latency is not None:
        cur["tool_latency_ms"] = round(avg_tool_latency, 3)

    issues: list[dict[str, Any]] = []
    for metric, rule in thresholds.items():
        if metric not in cur or metric not in base:
            continue
        bv = base[metric]
        if not isinstance(bv, (int, float)) or bv <= 0:
            continue
        if bv < rule.get("min_abs", 0.0):
            continue
        cv = cur[metric]
        if not isinstance(cv, (int, float)):
            continue
        delta_pct = (cv - bv) / bv * 100.0
        fail_thresh = rule.get("fail", 1.0) * 100.0
        warn_thresh = rule.get("warn", 1.0) * 100.0
        level = None
        if "fail" in rule and delta_pct > fail_thresh:
            level = "fail"
        elif "warn" in rule and delta_pct > warn_thresh:
            level = "warn"
        if level is not None:
            issues.append({
                "metric": metric,
                "current": cv,
                "baseline": bv,
                "delta_pct": round(delta_pct, 1),
                "level": level,
            })
    if strict:
        for issue in issues:
            if issue["level"] == "warn":
                issue["level"] = "fail"
    return issues


def render_issues(issues: list[dict[str, Any]], strict: bool) -> str:
    if not issues:
        return "PERF GATE: OK — all metrics within thresholds."
    lines = ["PERF GATE ISSUES:"]
    for issue in issues:
        lines.append(
            f"  [{issue['level'].upper():<4}] {issue['metric']:<20} "
            f"current={issue['current']:<10} baseline={issue['baseline']:<10} "
            f"delta={issue['delta_pct']:+.1f}%"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="benchmark.gate", description="Performance regression gate.")
    parser.add_argument("--baseline", type=str, default=str(ROOT / "benchmark" / "baseline.json"))
    parser.add_argument("--run", type=str, default=None, help="Existing benchmark JSON; default runs a fresh offline pass.")
    parser.add_argument("--repeats", type=int, default=3, help="Repeats for the fresh offline pass (averaged; default 3).")
    parser.add_argument("--strict", action="store_true", help="Promote warnings to failures.")
    parser.add_argument("--ci", action="store_true", help="CI mode: timing deltas warn-only (machine-specific baseline); "
                                                         "fails only on benchmark errors.")
    parser.add_argument("--allow-missing", action="store_true", help="Exit 0 if the baseline file does not exist yet.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        if args.allow_missing:
            if not args.quiet:
                print(f"PERF GATE: no baseline at {baseline_path} — skipping (use --baseline to write one).")
            return 0
        print(f"PERF GATE: baseline not found at {baseline_path} (run --offline --baseline to create it).")
        return 1

    if args.run:
        current = load_json(args.run)
    else:
        from benchmark import harness
        from benchmark.run import _merge_runs

        repeats = max(1, args.repeats)
        if not args.quiet:
            print(f"PERF GATE: running offline benchmark ({repeats} repeat(s))…")
        runs = [harness.run_offline_benchmark() for _ in range(repeats)]
        current = _merge_runs(runs)

    baseline = load_json(baseline_path)
    issues = check_regression(current, baseline, strict=args.strict)
    if args.ci:
        for issue in issues:
            if issue["metric"] in TIMING_METRICS and issue["level"] == "fail":
                issue["level"] = "warn"
    print(render_issues(issues, args.strict))
    failures = [i for i in issues if i["level"] == "fail"]
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
