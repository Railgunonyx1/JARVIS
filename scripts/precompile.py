"""Precompile JARVIS packages so startup avoids bytecode generation.

Run after updates or during installation:

    venv\\Scripts\\python.exe scripts\\precompile.py
"""

from __future__ import annotations

import compileall
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKGS = ["cli", "core", "memory", "providers", "runtime", "tools", "benchmark"]


def main() -> None:
    t0 = time.perf_counter()
    compiled = 0
    for pkg in PKGS:
        root = ROOT / pkg
        if not root.is_dir():
            continue
        ok = compileall.compile_dir(str(root), quiet=1, force=False)
        compiled += int(bool(ok))
    print(f"precompiled {compiled}/{len(PKGS)} packages "
          f"in {(time.perf_counter() - t0) * 1000:.0f} ms")


if __name__ == "__main__":
    sys.exit(main())
