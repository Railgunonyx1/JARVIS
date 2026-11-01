""""
JARVIS Dynamic Island — entry point.

Launches the Dynamic Island overlay (the sole user-facing interface).
The separate desktop companion window was removed; the island is the
authoritative UI for all interaction.
"""

import sys

from app.island_main import main as island_main

if __name__ == "__main__":
    sys.exit(island_main())
