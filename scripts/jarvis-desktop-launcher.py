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


def _resolve_desktop() -> tuple[str, str]:
    """Resolve the full-window desktop launcher layout.

    Returns (desktop_dir, repo_dir) where desktop_dir contains
    dynamic-island/app/main.py (the full-window entry point).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    local_desktop = os.path.join(repo, "dynamic-island")

    # Check for the full-window entry point first
    desktop_main = os.path.join(local_desktop, "app", "main.py")
    if os.path.isfile(desktop_main):
        return local_desktop, repo

    # Fall back to JARVIS_DESKTOP_HOME installed layout
    home = os.environ.get(
        "JARVIS_DESKTOP_HOME",
        os.path.expanduser("~/.local/share/jarvis-desktop"),
    )
    repo = os.path.join(home, "jarvis-repo")
    return os.path.join(repo, "dynamic-island"), repo


def _resolve_island() -> tuple[str, str]:
    """Resolve the island launcher layout.

    Returns (island_dir, repo_dir) where island_dir contains
    dynamic-island/app/island_main.py (the island overlay entry point).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    local_island = os.path.join(repo, "dynamic-island")

    # Check for the island entry point
    island_main = os.path.join(local_island, "app", "island_main.py")
    if os.path.isfile(island_main):
        return local_island, repo

    # Fall back to JARVIS_DESKTOP_HOME installed layout
    home = os.environ.get(
        "JARVIS_DESKTOP_HOME",
        os.path.expanduser("~/.local/share/jarvis-desktop"),
    )
    repo = os.path.join(home, "jarvis-repo")
    return os.path.join(repo, "dynamic-island"), repo


def main() -> int:
    # The script is invoked as jarvis-desktop, so use the desktop resolver
    desktop, repo = _resolve_desktop()

    for p in (desktop, repo):
        if p not in sys.path:
            sys.path.insert(0, p)

    # Launch the full-window client using main.py
    desktop_main = os.path.join(desktop, "app", "main.py")

    if not os.path.isfile(desktop_main):
        print(
            f"JARVIS Desktop not found at {desktop} (main.py missing). "
            "Use 'jarvis-island' or 'jarvis-desktop-island' for the island.",
            file=sys.stderr,
        )
        return 1

    from app.main import main as app_main
    return app_main()


if __name__ == "__main__":
    sys.exit(main())