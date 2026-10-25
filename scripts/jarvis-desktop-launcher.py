#!/usr/bin/env python3
"""JARVIS Desktop launcher — resolves install layout and starts the app.

Resolves the app package from this file's own directory first (so the
working tree runs when invoked in-place), then falls back to the
installed layout under JARVIS_DESKTOP_HOME.
"""

import os
import sys


def _resolve() -> tuple[str, str]:
    here = os.path.dirname(os.path.abspath(__file__))
    local_desktop = os.path.join(here, "jarvis-desktop")
    if os.path.isfile(os.path.join(local_desktop, "app", "main.py")):
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

    main_mod = os.path.join(desktop, "app", "main.py")
    if not os.path.isfile(main_mod):
        print(f"JARVIS Desktop not found at {main_mod}", file=sys.stderr)
        return 1

    from app.main import main as app_main
    return app_main()


if __name__ == "__main__":
    sys.exit(main())
