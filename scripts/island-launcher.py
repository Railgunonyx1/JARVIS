#!/usr/bin/env python3
"""JARVIS Desktop Island launcher — starts the Dynamic Island overlay.

Resolves the app package from this file's own directory first (so the
working tree runs when invoked in-place), then falls back to the
installed layout under JARVIS_DESKTOP_HOME.

**Contract:** `jarvis-desktop-island` / `jarvis-island` launches the Dynamic
Island overlay using `dynamic-island/app/island_main.py`. This is a separate
entry point from `jarvis-desktop` which launches the full-window client.
"""

import os
import sys


def _resolve() -> tuple[str, str]:
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    local_island = os.path.join(repo, "dynamic-island")
    if os.path.isfile(os.path.join(local_island, "app", "island_main.py")):
        return local_island, repo
    home = os.environ.get(
        "JARVIS_DESKTOP_HOME",
        os.path.expanduser("~/.local/share/jarvis-desktop"),
    )
    repo = os.path.join(home, "jarvis-repo")
    return os.path.join(repo, "dynamic-island"), repo


def main() -> int:
    island, repo = _resolve()

    for p in (island, repo):
        if p not in sys.path:
            sys.path.insert(0, p)

    island_main = os.path.join(island, "app", "island_main.py")
    if not os.path.isfile(island_main):
        print(f"JARVIS Island not found at {island} (island_main.py missing)", file=sys.stderr)
        return 1

    from app.island_main import main as island_main
    return island_main()


if __name__ == "__main__":
    sys.exit(main())
