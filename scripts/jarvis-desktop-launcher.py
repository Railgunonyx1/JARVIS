#!/usr/bin/env python3
"""JARVIS Desktop launcher — resolves install layout and starts the app.

Resolves the app package from this file's own directory first (so the
working tree runs when invoked in-place), then falls back to the
installed layout under JARVIS_DESKTOP_HOME.

Launches the Dynamic Island. The Dynamic Island is the sole user-facing
interface. The separate desktop chat window was removed; all functionality
flows through the island's ConversationPanel as it expands from the pill.
"""

import os
import sys


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
    # Resolve the island entry point
    island, repo = _resolve_island()

    for p in (island, repo):
        if p not in sys.path:
            sys.path.insert(0, p)

    island_main = os.path.join(island, "app", "island_main.py")
    if not os.path.isfile(island_main):
        print(
            f"JARVIS Island not found at {island} (island_main.py missing).",
            file=sys.stderr,
        )
        return 1

    from app.island_main import main as island_main_func
    return island_main_func()


if __name__ == "__main__":
    sys.exit(main())