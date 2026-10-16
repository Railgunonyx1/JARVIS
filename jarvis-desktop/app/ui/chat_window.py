"""Minimal PySide6 chat window for JARVIS Desktop.

Layout follows the master plan §2: header, chat area, input bar, bottom toolbar.
"""

from __future__ import annotations

import sys
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QTextCursor, QFont, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QFrame, QScrollArea,
    QSizePolicy,
)

from app.integration.jarvis_backend import JarvisBackend, AgentResponse


class ChatWindow(QMainWindow):
    """Main application window — minimal chat interface."""

    chunk_received = Signal(str)
    response_received = Signal(object)
    status_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS")
        self.setMinimumSize(900, 650)
        self._backend: JarvisBackend | None = None
        self._init_ui()
        self._connect_signals()
        self._apply_theme()

    def _init_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(52)
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(16, 0, 16, 0)

        title = QLabel("JARVIS")
        title.setObjectName("title")
        hlayout.addWidget(title)
        hlayout.addStretch()

        self.status_label = QLabel("● Initializing")
        self.status_label.setObjectName("status")
        hlayout.addWidget(self.status_label)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setObjectName("settings_btn")
        hlayout.addWidget(self.settings_btn)

        root.addWidget(header)

        # ── Chat area ───────────────────────────────────────────
        self.chat_area = QTextEdit()
        self.chat_area.setReadOnly(True)
        self.chat_area.setFrameShape(QFrame.NoFrame)
        self.chat_area.setPlaceholderText("")
        self.chat_area.setObjectName("chat_area")
        root.addWidget(self.chat_area, 1)

        # ── Input bar ───────────────────────────────────────────
        input_bar = QFrame()
        input_bar.setObjectName("input_bar")
        ilayout = QHBoxLayout(input_bar)
        ilayout.setContentsMargins(12, 8, 12, 8)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Message JARVIS...")
        self.input_field.setObjectName("input_field")
        ilayout.addWidget(self.input_field, 1)

        self.mic_btn = QPushButton("Mic")
        self.mic_btn.setObjectName("mic_btn")
        self.mic_btn.setEnabled(False)
        ilayout.addWidget(self.mic_btn)

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("send_btn")
        ilayout.addWidget(self.send_btn)

        root.addWidget(input_bar)

        # ── Bottom toolbar ──────────────────────────────────────
        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        tlayout = QHBoxLayout(toolbar)
        tlayout.setContentsMargins(16, 0, 16, 0)

        self.gesture_btn = QPushButton("Gesture Mode")
        self.gesture_btn.setCheckable(True)
        self.gesture_btn.setEnabled(False)
        tlayout.addWidget(self.gesture_btn)

        self.workspace_btn = QPushButton("3D Workspace")
        self.workspace_btn.setEnabled(False)
        tlayout.addWidget(self.workspace_btn)

        tlayout.addStretch()
        root.addWidget(toolbar)

    def _connect_signals(self) -> None:
        self.send_btn.clicked.connect(self._on_send)
        self.input_field.returnPressed.connect(self._on_send)
        self.chunk_received.connect(self._append_chunk)
        self.response_received.connect(self._on_response)
        self.status_changed.connect(self._on_status)

    def _apply_theme(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background: #0a0e14; }
           #header { background: #0d1117; border-bottom: 1px solid #1e2530; }
            #title { color: #4fc3f7; font-size: 18px; font-weight: bold; }
            #status { color: #8b949e; font-size: 12px; }
            QPushButton {
                background: #1e2530; color: #c9d1d9; border: 1px solid #30363d;
                border-radius: 4px; padding: 6px 14px; font-size: 13px;
            }
            QPushButton:hover { background: #283041; }
            QPushButton:pressed { background: #1e2530; }
            QPushButton:disabled { color: #484f58; }
            QPushButton:checked { background: #0d419d; border-color: #1f6feb; color: #fff; }
            #settings_btn { background: transparent; border: none; color: #8b949e; }
            #settings_btn:hover { color: #c9d1d9; }
            #chat_area { background: #0a0e14; color: #c9d1d9; border: none;
                         font-size: 14px; padding: 12px; }
            #input_bar { background: #0d1117; border-top: 1px solid #1e2530; }
            #input_field {
                background: #161b22; color: #c9d1d9; border: 1px solid #30363d;
                border-radius: 6px; padding: 8px 12px; font-size: 14px;
            }
            #input_field:focus { border-color: #1f6feb; }
            #toolbar { background: #0d1117; border-top: 1px solid #1e2530; }
        """)

    def start_backend(self, mode: str = "agent") -> None:
        """Initialize and start the agent backend."""
        self._backend = JarvisBackend(
            mode=mode,
            on_chunk=self.chunk_received.emit,
            on_response=self.response_received.emit,
            on_status=self.status_changed.emit,
        )
        self._backend.start()

    def _on_send(self) -> None:
        text = self.input_field.text().strip()
        if not text or not self._backend:
            return
        self._append_message("user", text)
        self.input_field.clear()
        self._backend.send_message(text)

    def _append_message(self, role: str, text: str) -> None:
        if role == "user":
            self.chat_area.append(f'<p style="color:#4fc3f7;margin:4px 0;"><b>You:</b> {self._escape(text)}</p>')
        elif role == "jarvis":
            self.chat_area.append(f'<p style="color:#c9d1d9;margin:4px 0;"><b>JARVIS:</b> {self._escape(text)}</p>')
        self.chat_area.moveCursor(QTextCursor.End)

    def _append_chunk(self, chunk: str) -> None:
        # Append streaming text inline (simplified: just append)
        self.chat_area.insertPlainText(chunk)
        self.chat_area.moveCursor(QTextCursor.End)

    def _on_response(self, response: AgentResponse) -> None:
        if response.success:
            self._append_message("jarvis", response.text)
        else:
            self._append_message("jarvis", f"[Error: {response.error}]")
        self.status_label.setText("● Ready")

    def _on_status(self, status: str) -> None:
        if status == "ready":
            self.status_label.setText("● Ready")
            self.status_label.setStyleSheet("color: #3fb950;")
        else:
            self.status_label.setText(f"● {status}")

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def closeEvent(self, event) -> None:
        if self._backend:
            self._backend.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("JARVIS Desktop")
    window = ChatWindow()
    window.show()
    window.start_backend()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
