"""Minimal PySide6 chat window for JARVIS Desktop — Apple-inspired design.

Layout follows Apple Human Interface Guidelines: San Francisco typography,
monochrome palette, depth through layering not shadows, subtle micro-interactions,
and system-native components. Lightweight implementation with zero external deps.
"""

from __future__ import annotations

import sys

from app.integration.coordinator import AppCoordinator
from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ChatWindow(QMainWindow):
    """Main application window — minimal chat interface with Apple HIG design."""

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
        header.setFixedHeight(44)
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(16, 0, 16, 0)
        hlayout.setSpacing(0)

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
        input_bar.setFixedHeight(56)
        ilayout = QHBoxLayout(input_bar)
        ilayout.setContentsMargins(16, 8, 16, 8)
        ilayout.setSpacing(12)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Message JARVIS...")
        self.input_field.setObjectName("input_field")
        self.input_field.setMinimumHeight(36)
        ilayout.addWidget(self.input_field, 1)

        self.mic_btn = QPushButton("Mic")
        self.mic_btn.setObjectName("mic_btn")
        self.mic_btn.setEnabled(False)
        self.mic_btn.setFixedSize(72, 36)
        ilayout.addWidget(self.mic_btn)

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("send_btn")
        self.send_btn.setFixedSize(72, 36)
        ilayout.addWidget(self.send_btn)

        root.addWidget(input_bar)

        # ── Bottom toolbar ──────────────────────────────────────
        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        toolbar.setFixedHeight(44)
        tlayout = QHBoxLayout(toolbar)
        tlayout.setContentsMargins(16, 0, 16, 0)
        tlayout.setSpacing(16)

        self.gesture_btn = QPushButton("Gesture Mode")
        self.gesture_btn.setObjectName("gesture_btn")
        self.gesture_btn.setCheckable(True)
        self.gesture_btn.setEnabled(False)
        self.gesture_btn.setFixedSize(120, 34)
        tlayout.addWidget(self.gesture_btn)

        self.workspace_btn = QPushButton("3D Workspace")
        self.workspace_btn.setObjectName("workspace_btn")
        self.workspace_btn.setEnabled(False)
        self.workspace_btn.setFixedSize(120, 34)
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
        """Apple-inspired monochrome theme — lightweight, high quality."""
        self.setStyleSheet("""
            QMainWindow {
                background: #FFFFFF;
            }
            #header {
                background: #F5F5F7;
                border-bottom: 1px solid #D1D1D6;
            }
            #title {
                color: #1D1D1F;
                font-size: 17px;
                font-weight: 600;
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', sans-serif;
            }
            #status {
                color: #8E8E93;
                font-size: 12px;
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', sans-serif;
            }
            QPushButton {
                background: #F5F5F7;
                color: #007AFF;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 13px;
                font-weight: 500;
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', sans-serif;
                min-height: 34px;
            }
            QPushButton:hover {
                background: #E5E5EA;
            }
            QPushButton:pressed {
                background: #D1D1D6;
            }
            QPushButton:disabled {
                color: #AEAEB2;
                background: #F2F2F2;
            }
            QPushButton:checked {
                background: #007AFF;
                color: #FFFFFF;
            }
            #settings_btn {
                background: transparent;
                border: none;
                color: #8E8E93;
                padding: 0;
                min-height: auto;
            }
            #settings_btn:hover {
                color: #007AFF;
                background: transparent;
            }
            #chat_area {
                background: #FFFFFF;
                color: #1D1D1F;
                border: none;
                font-size: 14px;
                line-height: 1.5;
                padding: 16px;
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', sans-serif;
            }
            #input_bar {
                background: #F5F5F7;
                border-top: 1px solid #D1D1D6;
            }
            #input_field {
                background: #FFFFFF;
                color: #1D1D1F;
                border: 1px solid #D1D1D6;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 14px;
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', sans-serif;
            }
            #input_field:focus {
                border-color: #007AFF;
            }
            #toolbar {
                background: #F5F5F7;
                border-top: 1px solid #D1D1D6;
            }
            #mic_btn {
                background: #FFFFFF;
                border: 1px solid #D1D1D6;
                color: #1D1D1F;
            }
            #mic_btn:checked {
                background: #FF3B30;
                color: #FFFFFF;
                border-color: #FF3B30;
            }
            #send_btn {
                background: #007AFF;
                color: #FFFFFF;
            }
            #send_btn:disabled {
                color: #AEAEB2;
                background: #E5E5EA;
            }
            #gesture_btn, #workspace_btn {
                background: #FFFFFF;
                border: 1px solid #D1D1D6;
                color: #1D1D1F;
            }
            #gesture_btn:checked, #workspace_btn:checked {
                background: #007AFF;
                color: #FFFFFF;
                border-color: #007AFF;
            }
        """)

    def start_backend(self, mode: str = "agent") -> None:
        """Initialize and start the agent backend via coordinator."""
        from app.settings import load
        from PySide6.QtCore import QMetaObject, Qt, Q_ARG
        from PySide6.QtWidgets import QMessageBox

        settings = load()

        def _confirm(tool_name: str, arguments: dict) -> str:
            result = []

            def _ask() -> None:
                reply = QMessageBox.question(
                    self, "Confirm Action",
                    f"Allow JARVIS to execute: {tool_name}?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                result.append("once" if reply == QMessageBox.Yes else "deny")

            # Marshal to the GUI thread; deny on timeout/cancellation
            QMetaObject.invokeMethod(
                self, _ask, Qt.ConnectionType.QueuedConnection,
            )
            import time as _time
            deadline = _time.time() + 10.0
            while not result and _time.time() < deadline:
                _time.sleep(0.05)
            return result[0] if result else "deny"

        self._coordinator = AppCoordinator(mode=mode, confirmation_handler=_confirm)
        if settings.get("voice_enabled", True):
            self._coordinator.set_voice_enabled(True)
        if settings.get("model"):
            self._coordinator.set_model(settings["model"])
        self._coordinator.state_changed.connect(self._on_app_state)
        self._coordinator.chat_message.connect(self._on_chat_message)
        self._coordinator.voice_state_changed.connect(self._on_voice_state)
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
        from app.settings import load, save
        from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QLabel, QPushButton, QVBoxLayout

        current = load()

        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setFixedSize(420, 380)
        dialog.setStyleSheet("""
            QDialog {
                background: #FFFFFF;
            }
            QLabel {
                color: #1D1D1F;
                font-size: 13px;
                font-weight: 500;
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', sans-serif;
            }
            QComboBox {
                background: #FFFFFF;
                color: #1D1D1F;
                border: 1px solid #D1D1D6;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', sans-serif;
                min-height: 34px;
            }
            QCheckBox {
                color: #1D1D1F;
                font-size: 13px;
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', sans-serif;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #D1D1D6;
                border-radius: 4px;
                background: #FFFFFF;
            }
            QCheckBox::indicator:checked {
                background: #007AFF;
                border-color: #007AFF;
            }
            QPushButton {
                background: #F5F5F7;
                color: #007AFF;
                border: none;
                border-radius: 8px;
                padding: 0 16px;
                font-size: 13px;
                font-weight: 500;
                font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', 'Helvetica Neue', sans-serif;
                min-height: 34px;
            }
            QPushButton:hover {
                background: #E5E5EA;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        header_label = QLabel("Settings")
        header_label.setStyleSheet("font-size: 17px; font-weight: 600; border: none; padding: 0;")
        layout.addWidget(header_label)

        MODEL_OPTIONS = [
            ("Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-72B-Instruct (default)"),
            ("deepseek-ai/DeepSeek-R1", "deepseek-ai/DeepSeek-R1"),
            ("openai/gpt-oss-120b", "openai/gpt-oss-120b"),
            ("Qwen/Qwen3-4B-Thinking-2507", "Qwen/Qwen3-4B-Thinking-2507"),
            ("mistralai/Mistral-Nemo-Instruct-2407", "mistralai/Mistral-Nemo-Instruct-2407"),
        ]

        layout.addWidget(QLabel("Model:"))
        model_combo = QComboBox()
        model_combo.addItems([label for _, label in MODEL_OPTIONS])
        if current.get("model"):
            ids = [id_ for id_, _ in MODEL_OPTIONS]
            if current["model"] in ids:
                model_combo.setCurrentIndex(ids.index(current["model"]))
        layout.addWidget(model_combo)

        voice_cb = QCheckBox("Enable voice (push-to-talk)")
        voice_cb.setChecked(current.get("voice_enabled", True))
        layout.addWidget(voice_cb)

        gesture_cb = QCheckBox("Enable gesture control")
        gesture_cb.setChecked(current.get("gesture_enabled", False))
        layout.addWidget(gesture_cb)

        layout.addStretch()

        def _save():
            model_id = MODEL_OPTIONS[model_combo.currentIndex()][0]
            new_settings = {
                "model": model_id,
                "voice_enabled": voice_cb.isChecked(),
                "gesture_enabled": gesture_cb.isChecked(),
            }
            save(new_settings)
            if self._coordinator:
                self._coordinator.set_voice_enabled(voice_cb.isChecked())
                self._coordinator.set_model(model_id)
                if gesture_cb.isChecked() and not self._coordinator._gesture_active:
                    self._coordinator.toggle_gestures()
                elif not gesture_cb.isChecked() and self._coordinator._gesture_active:
                    self._coordinator.toggle_gestures()
            dialog.accept()

        def _cancel():
            dialog.reject()

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(_save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(_cancel)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

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
        self.status_label.setStyleSheet("color: #AF52DE;")

    def _append_message(self, role: str, text: str) -> None:
        if role == "user":
            self.chat_area.append(
                f'<p style="color:#007AFF;margin:8px 0;"><b>You:</b> {self._escape(text)}</p>'
            )
        elif role == "jarvis":
            self.chat_area.append(
                f'<p style="color:#1D1D1F;margin:8px 0;"><b>JARVIS:</b> {self._escape(text)}</p>'
            )
        elif role == "system":
            self.chat_area.append(
                f'<p style="color:#8E8E93;margin:8px 0;font-style:italic;">{self._escape(text)}</p>'
            )
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
            self.mic_btn.setText("Listening…")
            self.status_label.setText("● Listening")
            self.status_label.setStyleSheet("color: #FF3B30;")
        elif state_val == "speaking":
            self.mic_btn.setChecked(False)
            self.mic_btn.setText("Mic")
            self.status_label.setText("● Speaking")
            self.status_label.setStyleSheet("color: #AF52DE;")
        elif state_val == "error":
            self.mic_btn.setChecked(False)
            self.mic_btn.setText("Mic")
            self.status_label.setText("● Voice Error")
            self.status_label.setStyleSheet("color: #FF3B30;")
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

    # Apply system font
    font = QFont("-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', sans-serif", 13)
    app.setFont(font)

    window = ChatWindow()
    window.show()
    window.start_backend()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
