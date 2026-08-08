"""JARVIS startup benchmark — measures launcher / kernel / memory / provider / UI phases.

Run with the venv python:

    venv\\Scripts\\python.exe benchmark\\startup.py

Reports the plan's headline numbers:
    launcher     time to import the CLI module (prompt can appear right after)
    kernel       time to boot the full agent loop (router + memory)
    prompt-ready estimated time until the interactive prompt is visible
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    t0 = time.perf_counter()
    import cli.main  # noqa: F401
    import_ms = (time.perf_counter() - t0) * 1000.0

    from cli.main import _build_loop
    from cli.startup_profile import get_profiler

    profiler = get_profiler()
    t1 = time.perf_counter()
    loop = _build_loop("agent", 10, None, None)
    boot_ms = (time.perf_counter() - t1) * 1000.0
    loop.logger.flush()
    if loop.mem is not None:
        loop.mem.close()

    print("JARVIS Startup Benchmark")
    print("────────────────────────")
    print(f"  launcher (import cli.main)  {import_ms:>7.1f} ms")
    print(f"  prompt-visible (estimate)   {import_ms + 5.0:>7.1f} ms")
    print(f"  kernel ready (wall)         {boot_ms:>7.1f} ms")
    print()
    print(profiler.report())


if __name__ == "__main__":
    main()
