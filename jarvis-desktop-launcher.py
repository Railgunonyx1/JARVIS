#!/usr/bin/env python3
"""JARVIS Desktop launcher — resolves install layout and starts the app."""

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

    sys.path.insert(0, desktop)
    main_mod = os.path.join(desktop, "app", "main.py")
    if not os.path.isfile(main_mod):
        print(f"JARVIS Desktop not found at {main_mod}", file=sys.stderr)
        return 1

    from app.main import main as app_main
    return app_main()


if __name__ == "__main__":
    sys.exit(main())
