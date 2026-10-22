"""JARVIS Desktop Island — entry point for the Dynamic Island overlay.

Top-center morphing pill: idle -> hover peek -> click to expand into the full
chat panel. Also the target of the OS autostart entry.
"""

import argparse
import os
import sys

from PySide6.QtWidgets import QApplication

_DESKTOP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "jarvis-desktop"))
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)

from app.ui.overlay_window import IslandWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS Island")
    app.setQuitOnLastWindowClosed(False)

    parser = argparse.ArgumentParser(description="JARVIS Desktop Island")
    parser.add_argument("--no-autostart", action="store_true",
                        help="Do not register the login autostart entry")
    args, _ = parser.parse_known_args()

    from app import autostart
    if not args.no_autostart:
        autostart.enable()

    island = IslandWindow()
    island.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
