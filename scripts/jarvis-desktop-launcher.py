#!/usr/bin/env python3
"""JARVIS Desktop launcher — resolves install layout and starts the app.

Resolves the app package from this file's own directory first (so the
working tree runs when invoked in-place), then falls back to the
installed layout under JARVIS_DESKTOP_HOME.

**Contract:** `jarvis-desktop` launches the full-window JARVIS client using
`dynamic-island/app/main.py`. The island overlay is launched separately via
`jarvis-desktop-island` / `jarvis-island` which uses `dynamic-island/app/island_main.py`.
"""

import os
import sys


def _resolve(island: bool = False) -> tuple[str, str]:
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    local_desktop = os.path.join(repo, "dynamic-island")
    # If island mode is requested, we still resolve from the desktop launcher
    # but use the island entry point. The caller decides which entry point.
    if os.path.isfile(os.path.join(local_desktop, "app", "island_main.py")):
        return local_desktop, repo
    home = os.environ.get(
        "JARVIS_DESKTOP_HOME",
        os.path.expanduser("~/.local/share/jarvis-desktop"),
    )
    repo = os.path.join(home, "jarvis-repo")
    return os.path.join(repo, "dynamic-island"), repo


def main() -> int:
    desktop, repo = _resolve()

    for p in (desktop, repo):
        if p not in sys.path:
            sys.path.insert(0, p)

    # Use dynamic-island app entry point for the full desktop client.
    # jarvis-desktop launches the FULL-WINDOW client using main.py.
    # The island overlay is launched separately via jarvis-island / jarvis-desktop-island.
    desktop_main = os.path.join(desktop, "app", "main.py")

    if not os.path.isfile(desktop_main):
        print(f"JARVIS Desktop not found at {desktop} (main.py missing). "
              "Use 'jarvis-island' or 'jarvis-desktop-island' for the island.", file=sys.stderr)
        return 1

    from app.main import main as app_main
    return app_main()


if __name__ == "__main__":
    sys.exit(main())
