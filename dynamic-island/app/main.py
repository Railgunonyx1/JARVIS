""""
JARVIS Dynamic Island — entry point.

Launches the Dynamic Island overlay (the sole user-facing interface).
The separate desktop companion window was removed; the island is the
authoritative UI for all interaction.
"""

import os
import sys

from PySide6.QtWidgets import QApplication

_DESKTOP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)

from app.island_main import main as island_main

if __name__ == "__main__":
    sys.exit(island_main())
