"""Central application coordinator — wires all subsystems together.

Manages the full integration flow:
  Chat ↔ Voice ↔ Gestures ↔ 3D Workspace ↔ Desktop Actions

Ensures subsystems don't conflict (e.g., voice and gestures don't both
try to control the same action simultaneously).
"""

from __future__ import annotations

import logging
import threading
import time
from enum import StrEnum
from typing import Callable

from app.integration.jarvis_backend import JarvisBackend, AgentResponse
from app.voice.voice_manager import VoiceManager, VoiceState
from app.gestures.camera import Camera
from app.gestures.tracking import HandTracker
from app.gestures.recognition import GestureRecognizer, GestureEvent, GestureType
from app.gestures.mappings import GestureMapper
from app.desktop.actions import DesktopActionLayer, ActionRisk
from app.workspace3d.workspace3d import Workspace3D

logger = logging.getLogger("jarvis.desktop.integration")


class AppState(StrEnum):
    IDLE = "idle"
    CHATTING = "chatting"
    LISTENING = "listening"
    SPEAKING = "speaking"
    GESTURE_ACTIVE = "gesture_active"
    WORKSPACE_OPEN = "workspace_open"


class AppCoordinator:
    """Central coordinator for all desktop subsystems.

    Owns the backend, voice, gestures, workspace, and action layer.
    Routes events between them and prevents conflicts.

    Usage:
        coord = AppCoordinator()
        coord.start()
        coord.send_message("Hello")
        coord.toggle_voice()
        coord.toggle_gestures()
        coord.toggle_workspace()
        coord.shutdown()
    """

    def __init__(self, *, mode: str = "agent",
                 on_state_change: Callable[[AppState], None] | None = None,
                 on_chat_message: Callable[[str, str], None] | None = None,
                 on_voice_transcription: Callable[[str], None] | None = None,
                 on_gesture_action: Callable[[str], None] | None = None,
                 on_workspace_update: Callable[[str, str], None] | None = None,
                 confirmation_handler: Callable[[str], bool] | None = None):
        self._mode = mode
        self._on_state = on_state_change
        self._on_chat = on_chat_message
        self._on_voice_transcription = on_voice_transcription
        self._on_gesture_action = on_gesture_action
        self._on_workspace_update = on_workspace_update
        self._confirmation_handler = confirmation_handler

        self._state = AppState.IDLE
        self._state_lock = threading.Lock()

        # Subsystems (initialized in start())
        self._backend: JarvisBackend | None = None
        self._voice: VoiceManager | None = None
        self._camera: Camera | None = None
        self._tracker: HandTracker | None = None
        self._recognizer: GestureRecognizer | None = None
        self._mapper: GestureMapper | None = None
        self._actions: DesktopActionLayer | None = None
        self._workspace: Workspace3D | None = None

        self._gesture_active = False
        self._workspace_visible = False
        self._running = False

    @property
    def state(self) -> AppState:
        with self._state_lock:
            return self._state

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def backend(self) -> JarvisBackend | None:
        return self._backend

    @property
    def voice(self) -> VoiceManager | None:
        return self._voice

    @property
    def workspace(self) -> Workspace3D | None:
        return self._workspace

    @property
    def actions(self) -> DesktopActionLayer | None:
        return self._actions

    def _set_state(self, state: AppState) -> None:
        with self._state_lock:
            self._state = state
        if self._on_state:
            try:
                self._on_state(state)
            except Exception:
                pass

    def start(self) -> None:
        """Initialize and start all subsystems."""
        if self._running:
            return
        self._running = True

        # Backend
        self._backend = JarvisBackend(
            mode=self._mode,
            on_chunk=self._on_backend_chunk,
            on_response=self._on_backend_response,
            on_status=self._on_backend_status,
        )
        self._backend.start()

        # Voice
        self._voice = VoiceManager(
            agent_backend=self._backend,
            on_state_change=self._on_voice_state,
            on_transcription=self._on_voice_transcription,
            on_response=self._on_voice_response,
        )
        self._voice.warmup()

        # Actions
        self._actions = DesktopActionLayer(
            confirmation_handler=self._confirmation_handler,
        )

        # Workspace
        self._workspace = Workspace3D()
        self._workspace.load()

        self._set_state(AppState.IDLE)
        logger.info("AppCoordinator started")

    def shutdown(self) -> None:
        """Stop all subsystems gracefully."""
        self._running = False
        self._stop_gestures()
        if self._voice:
            self._voice.stop_speaking()
        if self._workspace:
            self._workspace.shutdown()
        if self._backend:
            self._backend.stop()
        logger.info("AppCoordinator shutdown")

    # ── Chat ────────────────────────────────────────────────────
    def send_message(self, text: str) -> None:
        """Send a text message to the agent."""
        if not self._backend or not text.strip():
            return
        self._set_state(AppState.CHATTING)
        if self._on_chat:
            self._on_chat("user", text)
        self._backend.send_message(text)

    def _on_backend_chunk(self, chunk: str) -> None:
        if self._on_chat:
            self._on_chat("chunk", chunk)

    def _on_backend_response(self, response: AgentResponse) -> None:
        if response.success:
            if self._on_chat:
                self._on_chat("jarvis", response.text)
            # Speak response if voice is active
            if self._voice and self._voice.state == VoiceState.IDLE:
                self._voice.speak(response.text)
        else:
            if self._on_chat:
                self._on_chat("jarvis", f"[Error: {response.error}]")
        self._set_state(AppState.IDLE)

    def _on_backend_status(self, status: str) -> None:
        pass

    # ── Voice ───────────────────────────────────────────────────
    def toggle_voice(self) -> None:
        """Toggle push-to-talk on/off."""
        if self._voice:
            self._voice.toggle_listening()

    def stop_speaking(self) -> None:
        """Interrupt TTS."""
        if self._voice:
            self._voice.stop_speaking()

    def _on_voice_state(self, state: VoiceState) -> None:
        if state == VoiceState.LISTENING:
            self._set_state(AppState.LISTENING)
        elif state == VoiceState.SPEAKING:
            self._set_state(AppState.SPEAKING)
        elif state == VoiceState.IDLE:
            self._set_state(AppState.IDLE)

    def _on_voice_response(self, text: str) -> None:
        if self._on_chat:
            self._on_chat("jarvis", text)

    # ── Gestures ────────────────────────────────────────────────
    def toggle_gestures(self) -> None:
        """Toggle gesture mode on/off."""
        if self._gesture_active:
            self._stop_gestures()
        else:
            self._start_gestures()

    def _start_gestures(self) -> None:
        if not self._actions:
            return
        self._recognizer = GestureRecognizer(on_gesture=self._on_gesture)
        self._mapper = GestureMapper(on_action=self._on_gesture_action_event)
        self._camera = Camera()
        self._tracker = HandTracker()
        self._tracker.set_frame_source(lambda: self._camera.latest_frame if self._camera else None)

        if self._camera.start() and self._tracker.start():
            self._gesture_active = True
            self._set_state(AppState.GESTURE_ACTIVE)
        else:
            self._stop_gestures()

    def _stop_gestures(self) -> None:
        if self._tracker:
            self._tracker.stop()
            self._tracker = None
        if self._camera:
            self._camera.stop()
            self._camera = None
        self._recognizer = None
        self._gesture_active = False
        self._set_state(AppState.IDLE)

    def _on_gesture(self, event: GestureEvent) -> None:
        if self._mapper:
            self._mapper.handle(event)

    def _on_gesture_action_event(self, action: str, event: GestureEvent) -> None:
        if self._actions:
            self._actions.execute(action)
        if self._on_gesture_action:
            self._on_gesture_action(action)

    # ── Workspace ───────────────────────────────────────────────
    def toggle_workspace(self) -> None:
        """Toggle 3D workspace on/off."""
        if not self._workspace:
            return
        if self._workspace.is_visible:
            self._workspace.hide()
            self._workspace_visible = False
            self._set_state(AppState.IDLE)
        else:
            self._workspace.show()
            self._workspace_visible = True
            self._set_state(AppState.WORKSPACE_OPEN)

    def update_workspace_panel(self, panel: str, text: str) -> None:
        """Update a workspace panel."""
        if self._workspace:
            self._workspace.set_panel_text(panel, text)
        if self._on_workspace_update:
            self._on_workspace_update(panel, text)

    # ── Desktop Actions ─────────────────────────────────────────
    def execute_action(self, action: str, *, confirmed: bool = False) -> bool:
        """Execute a desktop action through the controlled layer."""
        if not self._actions:
            return False
        return self._actions.execute(action, confirmed=confirmed)

    def get_available_actions(self, category: str | None = None) -> list:
        """List available desktop actions."""
        if not self._actions:
            return []
        return self._actions.get_actions(category)

    # ── Status ──────────────────────────────────────────────────
    def get_status(self) -> dict:
        """Return full system status."""
        return {
            "state": self.state.value,
            "backend_running": self._backend.is_running if self._backend else False,
            "voice_state": self._voice.state.value if self._voice else "none",
            "gesture_active": self._gesture_active,
            "workspace_visible": self._workspace_visible,
            "stt_engine": self._voice.stt_engine if self._voice else "none",
            "tts_engine": self._voice.tts_engine if self._voice else "none",
        }
