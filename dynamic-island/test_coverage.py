#!/usr/bin/env python3
"""Coverage run script (kept in sync with the repo layout).

Run with the repo root on PYTHONPATH, e.g.:

    PYTHONPATH=. python dynamic-island/test_coverage.py

This is a small convenience wrapper around the hermetic desktop tests so that
packaging and startup changes are caught by coverage before a release.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("PYTHONPATH", str(root))

    print(f"[coverage] root={root}")
    print("[coverage] stage1: hermetic desktop tests")

    import pytest
    rc = pytest.main([
        "-c", str(root / "pytest.ini"),
        "-q", "--maxfail=1", "--tb=short",
        "-k", "not live",
        "tests/desktop",
    ])
    if rc != 0:
        print("[coverage] stage1 failed")
        return 1

    print("[coverage] stage1 OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
