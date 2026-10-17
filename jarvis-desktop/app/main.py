"""JARVIS Desktop Companion — entry point."""

import sys
import os
import argparse

from PySide6.QtWidgets import QApplication

# Ensure the parent JARVIS repo is importable
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.ui.chat_window import ChatWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS Desktop")
    window = ChatWindow()
    window.show()
    window.start_backend()

    # Handle command-line actions from .desktop file shortcuts
    parser = argparse.ArgumentParser(description="JARVIS Desktop Companion")
    parser.add_argument("--settings", action="store_true",
                        help="Open settings panel")
    parser.add_argument("--gesture", action="store_true",
                        help="Toggle gesture mode")
    parser.add_argument("--workspace", action="store_true",
                        help="Toggle 3D workspace")
    args, _ = parser.parse_known_args()

    if args.settings:
        window._on_settings()
    if args.gesture:
        window._on_gesture_toggle()
    if args.workspace:
        window._on_workspace_toggle()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())