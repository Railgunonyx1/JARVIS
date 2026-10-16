"""3D workspace renderer for JARVIS Desktop.

Loads the Qt Quick 3D scene on demand. When the workspace is hidden,
rendering is paused to save GPU/CPU. Panels are updated via properties.

QQuickWidget is imported lazily so this module is importable on machines
without Qt Quick system libraries (e.g. headless CI).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QUrl, QObject, Signal

logger = logging.getLogger("jarvis.desktop.workspace3d")

_QML_PATH = Path(__file__).resolve().parent / "scene.qml"


class Workspace3D(QObject):
    """Manages the 3D holographic workspace.

    Usage:
        ws = Workspace3D()
        ws.load()           # loads QML, starts rendering
        ws.set_panel_text("chat", "Hello")
        ws.hide()           # pauses rendering
        ws.show()           # resumes rendering
    """

    panel_updated = Signal(str, str)  # panel_name, text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widget = None  # QQuickWidget, created lazily on load()
        self._loaded = False
        self._visible = False
        self._panel_data: dict[str, str] = {
            "chat": "JARVIS Chat\n\nAwaiting input...",
            "system": "System Monitor\n\nCPU: --%\nRAM: --%\nGPU: --%",
            "voice": "Voice\n\nStatus: Idle",
            "tasks": "Tasks\n\nNo active tasks",
            "workspace": "Workspace\n\nNo windows",
            "settings": "Settings\n\nNo settings",
        }
        self._fps = 0
        self._frame_count = 0
        self._last_fps_time = time.time()

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def is_visible(self) -> bool:
        return self._visible

    @property
    def fps(self) -> int:
        return self._fps

    def load(self) -> bool:
        """Load the QML scene. Returns True on success."""
        if self._loaded:
            return True
        try:
            from PySide6.QtQuickWidgets import QQuickWidget
            self._widget = QQuickWidget()
            self._widget.setResizeMode(QQuickWidget.SizeRootObjectToView)
            self._widget.setSource(QUrl.fromLocalFile(str(_QML_PATH)))
            if self._widget.status() == QQuickWidget.Error:
                logger.error("QML load failed: %s", self._widget.errors())
                self._widget = None
                return False
            self._loaded = True
            logger.info("3D workspace loaded")
            return True
        except Exception as e:
            logger.error("3D workspace load failed: %s", e)
            self._widget = None
            return False

    def show(self) -> None:
        """Show the workspace (resume rendering)."""
        if self._widget:
            self._widget.show()
            self._visible = True

    def hide(self) -> None:
        """Hide the workspace (pause rendering)."""
        if self._widget:
            self._widget.hide()
            self._visible = False

    def set_panel_text(self, panel: str, text: str) -> None:
        """Update a panel's text content."""
        self._panel_data[panel] = text
        self.panel_updated.emit(panel, text)
        if self._widget and self._loaded:
            root = self._widget.rootObject()
            if root:
                root.setProperty(f"panel_{panel}", text)

    def get_panel_text(self, panel: str) -> str:
        return self._panel_data.get(panel, "")

    def update_system_stats(self, cpu: float, ram: float, gpu: float = 0.0) -> None:
        """Update the system monitor panel."""
        text = f"System Monitor\n\nCPU: {cpu:.0f}%\nRAM: {ram:.0f}%\nGPU: {gpu:.0f}%"
        self.set_panel_text("system", text)

    def update_voice_status(self, status: str) -> None:
        """Update the voice panel."""
        text = f"Voice\n\nStatus: {status}"
        self.set_panel_text("voice", text)

    def update_tasks(self, tasks: list[str]) -> None:
        """Update the tasks panel."""
        text = "Tasks\n\n" + "\n".join(tasks) if tasks else "Tasks\n\nNo active tasks"
        self.set_panel_text("tasks", text)

    def update_chat(self, messages: list[str]) -> None:
        """Update the chat panel."""
        text = "JARVIS Chat\n\n" + "\n".join(messages[-5:]) if messages else "JARVIS Chat\n\nAwaiting input..."
        self.set_panel_text("chat", text)

    def get_widget(self):
        """Get the underlying QQuickWidget for embedding in the UI."""
        return self._widget

    def shutdown(self) -> None:
        """Release all resources."""
        self.hide()
        if self._widget:
            self._widget.deleteLater()
            self._widget = None
        self._loaded = False
