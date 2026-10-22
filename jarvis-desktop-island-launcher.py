#!/usr/bin/env python3
"""JARVIS Desktop Island launcher — starts the Dynamic Island overlay.

Resolves the app package from this file's own directory first (so the
working tree runs when invoked in-place), then falls back to the
installed layout under JARVIS_DESKTOP_HOME.
"""

import os
import sys


def _resolve() -> tuple[str, str]:
    here = os.path.dirname(os.path.abspath(__file__))
    local_desktop = os.path.join(here, "jarvis-desktop")
    if os.path.isfile(os.path.join(local_desktop, "app", "island_main.py")):
        return local_desktop, here
    home = os.environ.get(
        "JARVIS_DESKTOP_HOME",
        os.path.expanduser("~/.local/share/jarvis-desktop"),
    )
    repo = os.path.join(home, "jarvis-repo")
    return os.path.join(repo, "jarvis-desktop"), repo


def main() -> int:
    desktop, repo = _resolve()

    for p in (desktop, repo):
        if p not in sys.path:
            sys.path.insert(0, p)

    from app.island_main import main as island_main
    return island_main()


if __name__ == "__main__":
    sys.exit(main())
