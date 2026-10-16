"""JARVIS Desktop Companion — entry point."""

import sys
import os

# Ensure the parent JARVIS repo is importable
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.ui.chat_window import main

if __name__ == "__main__":
    main()
