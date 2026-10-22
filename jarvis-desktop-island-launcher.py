#!/usr/bin/env python3
"""JARVIS Desktop Island launcher — starts the Dynamic Island overlay."""

import os
import sys


def main() -> int:
    home = os.environ.get(
        "JARVIS_DESKTOP_HOME",
        os.path.expanduser("~/.local/share/jarvis-desktop"),
    )
    repo = os.path.join(home, "jarvis-repo")
    desktop = os.path.join(repo, "jarvis-desktop")

    for p in (desktop, repo):
        if p not in sys.path:
            sys.path.insert(0, p)

    from app.island_main import main as island_main
    return island_main()


if __name__ == "__main__":
    sys.exit(main())
