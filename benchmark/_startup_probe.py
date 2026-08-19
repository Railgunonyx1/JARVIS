"""Fresh-interpreter startup probe — prints one JSON line.

Measures the plan's cold-boot numbers in a pristine process:
    launcher       time to import the CLI module
    kernel         time to boot the full agent loop (config+tools+project+router+memory)
    prompt_ready   estimated time until the interactive prompt is visible
    rss_mb         resident set after kernel boot (idle RAM)

Run by benchmark/harness.py::measure_startup. No dependencies on the harness
module so only the real boot cost is measured.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

t0 = time.perf_counter()
import cli.main  # noqa: F401

launcher_ms = (time.perf_counter() - t0) * 1000.0

import psutil  # noqa: E402

from runtime.kernel import build_kernel, close_kernel  # noqa: E402
from runtime.startup_profile import get_profiler  # noqa: E402

profiler = get_profiler()
t1 = time.perf_counter()
loop = build_kernel("agent", 5)
kernel_ms = (time.perf_counter() - t1) * 1000.0
rss_mb = psutil.Process().memory_info().rss / 1e6
close_kernel(loop)

phases = {
    name: round((end - start) * 1000.0, 1)
    for name, start, end in profiler._phases  # noqa: SLF001
}

print(json.dumps({
    "launcher_ms": round(launcher_ms, 1),
    "kernel_ms": round(kernel_ms, 1),
    "prompt_ready_ms": round(launcher_ms + 5.0, 1),
    "rss_mb": round(rss_mb, 1),
    "phases": phases,
    "python": sys.version.split()[0],
}))
