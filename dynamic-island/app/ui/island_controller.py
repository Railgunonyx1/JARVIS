"""Island presentation controller — maps runtime events to island state.

Owns *presentation* state only. Subscribes to AppCoordinator/backend signals
and emits island-level status updates. Holds no agent, permission, or tool
logic — those stay in the coordinator and kernel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, QTimer, Signal

logger = logging.getLogger("jarvis.desktop.island.controller")

_CHUNK_FLUSH_MS = 33  # ~30 fps coalescing window for streamed tokens


class IslandStatus(Enum):
    IDLE = "idle"
    STARTING = "starting"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    WORKING = "working"
    APPROVAL = "approval"
    ERROR = "error"

    @property
    def label(self) -> str:
        return {
            IslandStatus.IDLE: "Ready",
            IslandStatus.STARTING: "Starting JARVIS\u2026",
            IslandStatus.LISTENING: "Listening",
            IslandStatus.THINKING: "Thinking",
            IslandStatus.SPEAKING: "Speaking",
            IslandStatus.WORKING: "Working",
            IslandStatus.APPROVAL: "Approval required",
            IslandStatus.ERROR: "Error",
        }[self]

    @property
    def color(self) -> str:
        return {
            IslandStatus.IDLE: "#8E8E93",
            IslandStatus.STARTING: "#FF9F0A",
            IslandStatus.LISTENING: "#FF3B30",
            IslandStatus.THINKING: "#FF9F0A",
            IslandStatus.SPEAKING: "#AF52DE",
            IslandStatus.WORKING: "#0A84FF",
            IslandStatus.APPROVAL: "#FFD60A",
            IslandStatus.ERROR: "#FF3B30",
        }[self]

    @property
    def busy(self) -> bool:
        return self in (
            IslandStatus.STARTING,
            IslandStatus.THINKING,
            IslandStatus.WORKING,
        )


@dataclass
class IslandView:
    """Snapshot handed to the window for rendering."""

    status: IslandStatus
    detail: str = ""


class IslandController(QObject):
    """Presentation adapter between the agent runtime and the island UI."""

    view_changed = Signal(object)  # IslandView
    chat_message = Signal(str, str)  # role, text
    transcription = Signal(str)
    stream_chunk = Signal(str)  # coalesced streamed model text

    def __init__(self, coordinator=None) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._status = IslandStatus.IDLE
        self._detail = ""
        self._connected = False
        self._backend_ready = False
        self._stream_buf: list[str] = []
        self._streaming = False  # track active streaming turn
        self._stream_timer = QTimer(self)
        self._stream_timer.setSingleShot(True)
        self._stream_timer.setInterval(_CHUNK_FLUSH_MS)
        self._stream_timer.timeout.connect(self._flush_stream)

    @property
    def coordinator(self):
        return self._coordinator

    @property
    def view(self) -> IslandView:
        return IslandView(self._status, self._detail)

    def attach(self, coordinator) -> None:
        """Bind to a coordinator and subscribe to its signals.

        Must be called AFTER ``coordinator.start()`` so the backend exists.
        The backend is created lazily inside ``start()``; binding before that
        would silently drop status/state signals.
        """
        self._coordinator = coordinator
        coordinator.state_changed.connect(self._on_app_state)
        coordinator.voice_state_changed.connect(self._on_voice_state)
        coordinator.voice_transcription.connect(self._on_transcription)
        coordinator.chat_message.connect(self._on_chat_message)
        backend = getattr(coordinator, "_backend", None)
        if backend is None:
            logger.warning("Coordinator backend missing at attach; status signals not bound")
        else:
            backend.status_changed.connect(self._on_backend_status)
            backend.state_changed.connect(self._on_backend_state)
        self._connected = True

    # ── Event handlers ───────────────────────────────────────────
    def _set(self, status: IslandStatus, detail: str = "") -> None:
        if status is self._status and detail == self._detail:
            return
        self._status = status
        self._detail = detail
        self.view_changed.emit(self.view)

    def _on_app_state(self, state) -> None:
        val = getattr(state, "value", str(state))
        if val == "listening":
            self._set(IslandStatus.LISTENING)
        elif val == "speaking":
            self._set(IslandStatus.SPEAKING)
        elif val == "chatting":
            self._set(IslandStatus.THINKING)

    def _on_voice_state(self, state) -> None:
        val = getattr(state, "value", str(state))
        if val == "listening":
            self._set(IslandStatus.LISTENING)
        elif val == "transcribing":
            self._set(IslandStatus.THINKING, "Transcribing")
        elif val == "thinking":
            self._set(IslandStatus.THINKING)
        elif val == "speaking":
            self._set(IslandStatus.SPEAKING)
        elif val == "error":
            self._set(IslandStatus.ERROR)
        elif val == "idle" and not self._status.busy:
            self._set(IslandStatus.IDLE)

    def _on_transcription(self, text: str) -> None:
        self.transcription.emit(text)
        self._set(IslandStatus.THINKING, text[:60])

    def _on_chat_message(self, role: str, text: str) -> None:
        if role == "chunk":
            # Coalesce streamed tokens: one GUI update per ~33ms instead of
            # one per token (measured ~46x fewer widget redraws).
            self._stream_buf.append(text)
            if not self._stream_timer.isActive():
                self._stream_timer.start()
            # Mark that we are currently in a streaming response for this turn
            self._streaming = True
            return
        # A completed assistant response has arrived.
        # If we were streaming, mark the turn as no longer streaming.
        if role == "jarvis":
            was_streaming = self._streaming
            self._streaming = False
        else:
            was_streaming = False
        # Flush pending stream text before an ordered message so the transcript
        # never interleaves.
        self._flush_stream()
        # The coordinator emits streamed chunks AND then the full response text.
        # If we were streaming, the full response is a duplicate of the
        # coalesced chunks; skip it. Otherwise show it.
        if role == "jarvis" and was_streaming:
            return
        self.chat_message.emit(role, text)
        if role == "user":
            self._set(IslandStatus.THINKING, text[:60])

    def _flush_stream(self) -> bool:
        if self._stream_timer.isActive():
            self._stream_timer.stop()
        if not self._stream_buf:
            return False
        text = "".join(self._stream_buf)
        self._stream_buf.clear()
        self.stream_chunk.emit(text)
        return True

    def _on_backend_status(self, status: str) -> None:
        if status:
            self._set(IslandStatus.WORKING, status[:60])

    def _on_backend_state(self, state) -> None:
        val = getattr(state, "value", str(state))
        if val == "starting":
            self._set(IslandStatus.STARTING)
        elif val in ("ready", "running"):
            self._backend_ready = True
            if not self._status.busy and self._status is not IslandStatus.ERROR:
                self._set(IslandStatus.IDLE)
        elif val == "error":
            self._set(IslandStatus.ERROR)

    def set_status(self, status: IslandStatus, detail: str = "") -> None:
        self._set(status, detail)
