"""Minimal PySide6 chat window for JARVIS Desktop.

Layout follows the master plan §2: header, chat area, input bar, bottom toolbar.
All subsystems are managed by AppCoordinator (Phase 6 integration).
All UI updates happen on the GUI thread via Qt signals from the coordinator.
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

from app.integration.coordinator import AppCoordinator, AppState
from app.voice.voice_manager import VoiceState


class ChatWindow(QMainWindow):
    """Main application window — minimal chat interface."""

    voice_state_changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS")
        self.setMinimumSize(900, 650)
        self._coordinator: AppCoordinator | None = None
        self._max_messages = 500
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
        self.mic_btn.clicked.connect(self._on_mic_toggle)
        self.gesture_btn.clicked.connect(self._on_gesture_toggle)
        self.workspace_btn.clicked.connect(self._on_workspace_toggle)
        self.settings_btn.clicked.connect(self._on_settings)
        self.voice_state_changed.connect(self._on_voice_state)

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
        """Initialize and start the agent backend via coordinator."""
        self._coordinator = AppCoordinator(mode=mode)
        self._coordinator.state_changed.connect(self._on_app_state)
        self._coordinator.chat_message.connect(self._on_chat_message)
        self._coordinator.voice_transcription.connect(self._on_voice_transcription)
        self._coordinator.gesture_action.connect(self._on_gesture_action)
        self._coordinator.workspace_update.connect(self._on_workspace_update)
        self._coordinator.start()
        self.mic_btn.setEnabled(True)
        self.gesture_btn.setEnabled(True)
        self.workspace_btn.setEnabled(True)

    def _on_send(self) -> None:
        text = self.input_field.text().strip()
        if not text or not self._coordinator:
            return
        self._append_message("user", text)
        self.input_field.clear()
        self._coordinator.send_message(text)

    def _on_mic_toggle(self) -> None:
        if self._coordinator:
            self._coordinator.toggle_voice()

    def _on_gesture_toggle(self) -> None:
        if self._coordinator:
            self._coordinator.toggle_gestures()

    def _on_workspace_toggle(self) -> None:
        if self._coordinator:
            self._coordinator.toggle_workspace()

    def _on_settings(self) -> None:
        """Handle settings button click."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QComboBox, QCheckBox

        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("Settings"))

        # Model selection
        layout.addWidget(QLabel("Model:"))
        model_combo = QComboBox()
        model_combo.addItems([
            "Qwen/Qwen2.5-72B-Instruct (default)",
            "deepseek-ai/DeepSeek-R1",
            "openai/gpt-oss-120b",
            "Qwen/Qwen3-4B-Thinking-2507",
            "mistralai/Mistral-Nemo-Instruct-2407",
        ])
        layout.addWidget(model_combo)

        layout.addWidget(QLabel(""))

        # Voice
        voice_cb = QCheckBox("Enable voice (push-to-talk)")
        voice_cb.setChecked(self._coordinator is not None and self._coordinator.voice is not None)
        layout.addWidget(voice_cb)

        # Gestures
        gesture_cb = QCheckBox("Enable gesture control")
        gesture_cb.setChecked(self._gesture_active)
        layout.addWidget(gesture_cb)

        btn = QPushButton("Close")
        btn.clicked.connect(dialog.accept)
        layout.addWidget(btn)

        dialog.exec()

    def _on_chat_message(self, role: str, text: str) -> None:
        if role == "user":
            self._append_message("user", text)
        elif role == "jarvis":
            self._append_message("jarvis", text)
        elif role == "chunk":
            self._append_chunk(text)

    def _on_voice_transcription(self, text: str) -> None:
        self._append_message("user", text)
        self.input_field.clear()

    def _on_gesture_action(self, action: str) -> None:
        self._append_message("system", f"[Gesture: {action}]")

    def _on_workspace_update(self, panel: str, text: str) -> None:
        self.status_label.setText(f"● {panel}: {text[:40]}")
        self.status_label.setStyleSheet("color: #a371f7;")

    def _append_message(self, role: str, text: str) -> None:
        if role == "user":
            self.chat_area.append(f'<p style="color:#4fc3f7;margin:4px 0;"><b>You:</b> {self._escape(text)}</p>')
        elif role == "jarvis":
            self.chat_area.append(f'<p style="color:#c9d1d9;margin:4px 0;"><b>JARVIS:</b> {self._escape(text)}</p>')
        elif role == "system":
            self.chat_area.append(f'<p style="color:#8b949e;margin:4px 0;font-style:italic;">{self._escape(text)}</p>')
        self.chat_area.moveCursor(QTextCursor.End)
        self._trim_messages()

    def _append_chunk(self, chunk: str) -> None:
        self.chat_area.insertPlainText(chunk)
        self.chat_area.moveCursor(QTextCursor.End)
        self._trim_messages()

    def _trim_messages(self) -> None:
        """Keep chat history bounded to prevent unbounded memory growth."""
        document = self.chat_area.document()
        if document.blockCount() > self._max_messages:
            cursor = self.chat_area.textCursor()
            cursor.movePosition(QTextCursor.Start)
            for _ in range(document.blockCount() - self._max_messages):
                cursor.select(QTextCursor.BlockUnderCursor)
                cursor.removeSelectedText()
                cursor.deletePreviousChar()
            self.chat_area.setTextCursor(cursor)

    def _on_voice_state(self, state) -> None:
        state_val = state.value if hasattr(state, "value") else str(state)
        if state_val == "listening":
            self.mic_btn.setChecked(True)
            self.mic_btn.setText("Listening...")
            self.status_label.setText("● Listening")
            self.status_label.setStyleSheet("color: #f0883e;")
        elif state_val == "speaking":
            self.mic_btn.setChecked(False)
            self.mic_btn.setText("Mic")
            self.status_label.setText("● Speaking")
            self.status_label.setStyleSheet("color: #a371f7;")
        elif state_val == "error":
            self.mic_btn.setChecked(False)
            self.mic_btn.setText("Mic")
            self.status_label.setText("● Voice Error")
            self.status_label.setStyleSheet("color: #f85149;")
        else:
            self.mic_btn.setChecked(False)
            self.mic_btn.setText("Mic")

    def _on_app_state(self, state) -> None:
        state_val = state.value if hasattr(state, "value") else str(state)
        if state_val == "gesture_active":
            self.gesture_btn.setChecked(True)
            self.gesture_btn.setText("Stop Gestures")
        elif state_val == "workspace_open":
            self.workspace_btn.setChecked(True)
            self.workspace_btn.setText("Close 3D")
        else:
            self.gesture_btn.setChecked(False)
            self.gesture_btn.setText("Gesture Mode")
            self.workspace_btn.setChecked(False)
            self.workspace_btn.setText("3D Workspace")

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def closeEvent(self, event) -> None:
        if self._coordinator:
            self._coordinator.shutdown()
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