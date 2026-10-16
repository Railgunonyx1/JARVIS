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
from app.voice.voice_manager import VoiceManager, VoiceState
from app.gestures.camera import Camera
from app.gestures.tracking import HandTracker
from app.gestures.recognition import GestureRecognizer, GestureEvent, GestureType
from app.gestures.mappings import GestureMapper
from app.desktop.actions import DesktopActionLayer


class ChatWindow(QMainWindow):
    """Main application window — minimal chat interface."""

    chunk_received = Signal(str)
    response_received = Signal(object)
    status_changed = Signal(str)
    voice_state_changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS")
        self.setMinimumSize(900, 650)
        self._backend: JarvisBackend | None = None
        self._voice: VoiceManager | None = None
        self._camera: Camera | None = None
        self._tracker: HandTracker | None = None
        self._recognizer: GestureRecognizer | None = None
        self._mapper: GestureMapper | None = None
        self._actions: DesktopActionLayer | None = None
        self._workspace = None
        self._gesture_active = False
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
        self.chunk_received.connect(self._append_chunk)
        self.response_received.connect(self._on_response)
        self.status_changed.connect(self._on_status)
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
        """Initialize and start the agent backend."""
        self._backend = JarvisBackend(
            mode=mode,
            on_chunk=self.chunk_received.emit,
            on_response=self.response_received.emit,
            on_status=self.status_changed.emit,
        )
        self._backend.start()
        self._init_voice()

    def _init_voice(self) -> None:
        """Initialize the voice manager (push-to-talk + TTS)."""
        if not self._backend:
            return
        self._voice = VoiceManager(
            agent_backend=self._backend,
            on_state_change=self.voice_state_changed.emit,
            on_transcription=self._on_voice_transcription,
            on_response=self._on_voice_response,
        )
        self._voice.warmup()
        self.mic_btn.setEnabled(True)

    def _init_gestures(self) -> None:
        """Initialize gesture pipeline components (camera starts on demand)."""
        from app.gestures.camera import Camera
        from app.gestures.tracking import HandTracker
        from app.gestures.recognition import GestureRecognizer
        from app.gestures.mappings import GestureMapper
        from app.desktop.actions import DesktopActionLayer

        self._actions = DesktopActionLayer()
        self._recognizer = GestureRecognizer(on_gesture=self._on_gesture)
        self._mapper = GestureMapper(on_action=self._on_action)
        self._camera = Camera()
        self._tracker = HandTracker()
        self._tracker.set_frame_source(lambda: self._camera.latest_frame)
        self._gesture_btn.setEnabled(True)

    def _on_gesture_toggle(self) -> None:
        if self._gesture_active:
            self._stop_gestures()
        else:
            self._start_gestures()

    def _start_gestures(self) -> None:
        if not self._camera or not self._tracker:
            self._init_gestures()
        if self._camera.start() and self._tracker.start():
            self._gesture_active = True
            self._gesture_btn.setChecked(True)
            self._gesture_btn.setText("Stop Gestures")
            self.status_label.setText("● Gestures Active")
            self.status_label.setStyleSheet("color: #a371f7;")
        else:
            self._stop_gestures()

    def _stop_gestures(self) -> None:
        if self._tracker:
            self._tracker.stop()
        if self._camera:
            self._camera.stop()
        self._gesture_active = False
        self._gesture_btn.setChecked(False)
        self._gesture_btn.setText("Gesture Mode")
        self.status_label.setText("● Ready")

    def _on_hands(self, hands) -> None:
        if self._recognizer:
            self._recognizer.process(hands)

    def _on_gesture(self, event) -> None:
        if self._mapper:
            self._mapper.handle(event)

    def _on_action(self, action: str, event) -> None:
        if self._actions:
            self._actions.execute(action)

    def _on_send(self) -> None:
        text = self.input_field.text().strip()
        if not text or not self._backend:
            return
        self._append_message("user", text)
        self.input_field.clear()
        self._backend.send_message(text)

    def _on_mic_toggle(self) -> None:
        """Push-to-talk: toggle recording on/off."""
        if not self._voice:
            return
        self._voice.toggle_listening()

    def _on_gesture_toggle(self) -> None:
        """Toggle gesture mode on/off."""
        if self._gesture_active:
            self._stop_gestures()
        else:
            self._start_gestures()

    def _on_workspace_toggle(self) -> None:
        """Toggle 3D workspace on/off."""
        if not self._workspace:
            self._init_workspace()
        if self._workspace.is_visible:
            self._workspace.hide()
            self.workspace_btn.setChecked(False)
            self.workspace_btn.setText("3D Workspace")
        else:
            self._workspace.show()
            self.workspace_btn.setChecked(True)
            self.workspace_btn.setText("Close 3D")

    def _init_workspace(self) -> None:
        """Initialize the 3D workspace."""
        from app.workspace3d.workspace3d import Workspace3D
        self._workspace = Workspace3D()
        self._workspace.load()
        self.workspace_btn.setEnabled(True)

    def _start_gestures(self) -> None:
        """Initialize and start the gesture pipeline."""
        self._actions = DesktopActionLayer()
        self._recognizer = GestureRecognizer(on_gesture=self._on_gesture)
        self._mapper = GestureMapper(on_action=self._on_gesture_action)
        self._camera = Camera()
        self._tracker = HandTracker(on_hands=self._on_hands)
        self._tracker.set_frame_source(lambda: self._camera.latest_frame if self._camera else None)

        if not self._camera.start():
            self.status_label.setText("● Camera Error")
            self.status_label.setStyleSheet("color: #f85149;")
            return
        if not self._tracker.start():
            self._camera.stop()
            self.status_label.setText("● Tracking Error")
            self.status_label.setStyleSheet("color: #f85149;")
            return

        self._gesture_active = True
        self.gesture_btn.setChecked(True)
        self.gesture_btn.setText("Stop Gestures")
        self.status_label.setText("● Gestures Active")
        self.status_label.setStyleSheet("color: #a371f7;")

    def _stop_gestures(self) -> None:
        """Stop gesture pipeline and release camera."""
        if self._tracker:
            self._tracker.stop()
            self._tracker = None
        if self._camera:
            self._camera.stop()
            self._camera = None
        self._recognizer = None
        self._gesture_active = False
        self.gesture_btn.setChecked(False)
        self.gesture_btn.setText("Gesture Mode")
        if self._backend and self._backend.is_running:
            self.status_label.setText("● Ready")
            self.status_label.setStyleSheet("color: #3fb950;")

    def _on_hands(self, hands) -> None:
        """Process tracked hands through the recognizer."""
        if self._recognizer:
            self._recognizer.process(hands)

    def _on_gesture(self, event: GestureEvent) -> None:
        """Handle a recognized gesture event."""
        if self._mapper:
            self._mapper.handle(event)

    def _on_gesture_action(self, action: str, event: GestureEvent) -> None:
        """Execute a desktop action from a gesture."""
        if self._actions:
            self._actions.execute(action)

    def _on_voice_transcription(self, text: str) -> None:
        """Handle transcribed speech from push-to-talk."""
        self._append_message("user", text)
        self.input_field.clear()

    def _on_voice_response(self, text: str) -> None:
        """Handle voice response (TTS or error)."""
        if text.startswith("[Voice error"):
            self._append_message("jarvis", text)
        else:
            self._append_message("jarvis", text)
            if self._voice:
                self._voice.speak(text)

    def _on_voice_state(self, state) -> None:
        """Update UI based on voice state."""
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
        elif state_val == "thinking":
            self.status_label.setText("● Thinking")
            self.status_label.setStyleSheet("color: #4fc3f7;")
        elif state_val == "error":
            self.mic_btn.setChecked(False)
            self.mic_btn.setText("Mic")
            self.status_label.setText("● Voice Error")
            self.status_label.setStyleSheet("color: #f85149;")
        else:
            self.mic_btn.setChecked(False)
            self.mic_btn.setText("Mic")
            if self._backend and self._backend.is_running:
                self.status_label.setText("● Ready")
                self.status_label.setStyleSheet("color: #3fb950;")

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
            # Speak response if voice manager is active
            if self._voice and response.text:
                self._voice.speak(response.text)
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
        if self._gesture_active:
            self._stop_gestures()
        if self._voice:
            self._voice.stop_speaking()
        if self._workspace:
            self._workspace.shutdown()
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
