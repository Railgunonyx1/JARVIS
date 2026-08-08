"""Kernel boot trace — one cold kernel build with per-phase timing.

Run:  venv\\Scripts\\python.exe scripts\\kernel_trace.py [--project-dir DIR] [--rounds N]

Prints the StartupProfiler report plus import/total wall time. Add ``--rounds``
to compare warm (subsequent) builds against the cold one.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _run_one(project_dir):
    import_start = time.perf_counter()
    from runtime.kernel import build_kernel
    from runtime.startup_profile import get_profiler

    import_ms = (time.perf_counter() - import_start) * 1000.0
    started = time.perf_counter()
    loop = build_kernel(project_dir=project_dir)
    total_ms = (time.perf_counter() - started) * 1000.0

    report = get_profiler().report()
    lines = report.splitlines()
    lines.insert(2, f"  {'import runtime.kernel':<24} {import_ms:>7.1f} ms")
    lines.append(f"  {'build total':<24} {total_ms:>7.1f} ms")
    print("\n".join(lines))
    print(f"\nloop: mode={loop.permissions.mode} tools={len(loop.registry.list())} "
          f"project={loop.project.root_path}")
    return total_ms


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", default=None)
    parser.add_argument("--rounds", type=int, default=1,
                        help="run N builds and print per-round totals")
    args = parser.parse_args()

    totals = []
    for i in range(args.rounds):
        print(f"── round {i + 1}/{args.rounds} ──────────────")
        totals.append(_run_one(args.project_dir))
    if args.rounds > 1:
        print(f"\ncold={totals[0]:.1f}ms  warm(avg)="
              f"{sum(totals[1:]) / max(len(totals) - 1, 1):.1f}ms")


if __name__ == "__main__":
    sys.exit(main())
