"""Placeholder for the full desktop chat window stub.

The dynamic-island overlay is the authoritative UI today; this module exists
so older import paths do not raise during migrations. The real chat surface
lives in ``app/ui/conversation_panel.py`` and is embedded inside the island.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


class ChatWindow(QWidget):
    """Stand-in for the removed full chat window.

    The dynamic-island overlay is the authoritative UI today; this module exists
    so older import paths do not raise during migrations. The real chat surface
    lives in ``app/ui/conversation_panel.py`` and is embedded inside the island.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWindowTitle("JARVIS Chat (deprecated stub)")
