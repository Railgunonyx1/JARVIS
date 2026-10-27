# -*- coding: utf-8 -*-
"""Desktop Dynamic Island release smoke check.

Runs only the hermetic desktop tests plus a quick start/shutdown path
for the island process, so packaging changes are caught early.
"""

from __future__ import annotations

import os
import sys
import subprocess
import time
import textwrap
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    root = _root()
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(root))
    env.setdefault(
        "PYTEST_ARGS",
        "tests/desktop -q --maxfail=1 --tb=short -k 'not live'",
    )

    print(f"[release-smoke] root={root}")
    print("[release-smoke] stage1: hermetic desktop tests")

    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-c", str(root / "pytest.ini"), "-q", "--maxfail=1", "--tb=short", "-k", "not live", "tests/desktop"],
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=300,
    )
    if r.returncode != 0:
        print(r.stdout[-4000:])
        return 1

    print("[release-smoke] stage1 OK")
    print("[release-smoke] stage2: launcher module + main import")

    r = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent("""\
                import site, sys
                from pathlib import Path
                root = Path(sys.argv[1]).resolve()
                site.addsitedir(str(root / 'dynamic-island' / 'app'))

                import app.main   # type: ignore[import-untyped]
                import app.island_main  # type: ignore[import-untyped]
                import app.ui.overlay_window  # type: ignore[import-untyped]
                import app.ui.conversation_panel  # type: ignore[import-untyped]
                import app.ui.island_controller  # type: ignore[import-untyped]
                import app.settings  # type: ignore[import-untyped]
                import app.autostart  # type: ignore[import-untyped]
            """),
            str(root),
        ],
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        print(r.stdout[-4000:])
        return 1

    print("[release-smoke] stage2 OK")
    print("[release-smoke] stage3: island process start/shutdown")

    proc = subprocess.Popen(
        [sys.executable, str(root / "scripts" / "island-launcher.py")],
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.time() + 20
        ready = False
        for _ in range(40):
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                print("[island]", line.rstrip())
                if "JARVIS" in line or "Island" in line or "ready" in line.lower():
                    ready = True
            if proc.poll() is not None:
                break
            if time.time() > deadline:
                break
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            print("[release-smoke] stage3: forced terminate")
        else:
            print("[release-smoke] stage3: exit-code", proc.returncode)
    except Exception as e:  # noqa: BLE001
        print("[release-smoke] stage3 error:", e)
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        return 1

    print("[release-smoke] stage3 OK")
    print("[release-smoke] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
