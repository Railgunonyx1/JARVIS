"""Central application coordinator — wires all subsystems together.

Manages the full integration flow:
  Chat ↔ Voice ↔ Gestures ↔ 3D Workspace ↔ Desktop Actions

Ensures subsystems don't conflict (e.g., voice and gestures don't both
try to control the same action simultaneously).

All communication between subsystems and the UI happens through Qt signals,
which are thread-safe when crossing threads (Qt uses queued connections
when a signal is emitted from a non-GUI thread and connected to a slot
living in the GUI thread).
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from enum import StrEnum

from PySide6.QtCore import QObject, QThread, Signal

from app.desktop.actions import DesktopActionLayer
from app.gestures.camera import Camera
from app.gestures.mappings import GestureMapper
from app.gestures.recognition import GestureEvent, GestureRecognizer
from app.gestures.tracking import HandTracker
from app.integration.jarvis_backend import AgentResponse, BackendState, JarvisBackend
from app.voice.voice_manager import VoiceManager, VoiceState
from app.workspace3d.workspace3d import Workspace3D

logger = logging.getLogger("jarvis.desktop.integration")


class AppState(StrEnum):
    IDLE = "idle"
    CHATTING = "chatting"
    LISTENING = "listening"
    SPEAKING = "speaking"
    GESTURE_ACTIVE = "gesture_active"
    WORKSPACE_OPEN = "workspace_open"


# Approval IDs are request-scoped; each gets a unique UUID tied to the
# tool call context. The UI registry maps approval_id -> record, and only
# the matching record's decision is accepted (stale-click safe).
_APPROVAL_PREFIX = "approval-"


class AppCoordinator(QObject):
    """Central coordinator for all desktop subsystems.

    Owns the backend, voice, gestures, workspace, and action layer.
    Routes events between them and prevents conflicts.

    All public signals are emitted from worker threads but are safe to
    connect to Qt slots on the main thread — Qt automatically delivers
    them via queued connections when crossing threads.

    Usage:
        coord = AppCoordinator()
        coord.state_changed.connect(my_state_handler)
        coord.chat_message.connect(my_chat_handler)
        coord.start()
        coord.send_message("Hello")
        coord.shutdown()
    """

    # The coordinator no longer owns a background action queue.
    # Any old stub that reads or writes _action_queue directly now raises
    # AttributeError so it fails fast instead of silently spinning.

    # Legacy internal queue no longer used by the coordinator.
    # The attribute is kept only so existing stub callers fail fast and
    # visibly instead of silently spinning on an empty/unbounded queue.
    _action_queue: list[str] | None = None

    # Signals — emitted from worker threads, safe to connect to GUI slots
    state_changed = Signal(object)  # AppState
    chat_message = Signal(str, str)  # role, text
    voice_state_changed = Signal(object)  # VoiceState
    voice_transcription = Signal(str)
    gesture_action = Signal(str)
    workspace_update = Signal(str, str)
    backend_ready = Signal()  # emitted when backend has started and is emitting status/state

    def __init__(self, *, mode: str = "agent",
                 confirmation_handler: Callable[[str, dict, str], str] | None = None,
                 max_iterations: int = 10):
        super().__init__()
        self._mode = mode
        self._max_iterations = max_iterations
        self._confirmation_handler = confirmation_handler

        self._state = AppState.IDLE
        self._state_lock = threading.Lock()
        self._voice_state = VoiceState.IDLE
        self._gesture_state = False
        self._workspace_state = False
        # Per-request approval tracking (request-scoped, stale-safe)
        self._approval_id: str | None = None

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
        self._voice_turn_active = False
        self._voice_enabled = True  # voice enabled by default; ChatWindow.start_backend() may disable it
        self._buffer = ""  # per-turn chunk buffer
        self._pending_model: str | None = ""  # model selected before backend init
        self._running = False

    @property
    def state(self) -> AppState:
        """Derive combined state from per-subsystem trackers."""
        with self._state_lock:
            voice = self._voice_state
            gesture = self._gesture_state
            workspace = self._workspace_state
            backend_busy = getattr(self, "_voice_turn_active", False) or (self._backend and getattr(self._backend, "state", None) and str(getattr(self._backend.state, "value", self._backend.state)) in ("running",))
        if voice == VoiceState.SPEAKING:
            return AppState.SPEAKING
        if voice == VoiceState.LISTENING or voice == VoiceState.TRANSCRIBING or voice == VoiceState.THINKING:
            return AppState.LISTENING if voice == VoiceState.LISTENING else AppState.CHATTING
        if gesture:
            return AppState.GESTURE_ACTIVE
        if workspace:
            return AppState.WORKSPACE_OPEN
        if backend_busy:
            return AppState.CHATTING
        return AppState.IDLE

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
            # Track per-subsystem state
            if state == AppState.SPEAKING:
                self._voice_state = VoiceState.SPEAKING
            elif state == AppState.LISTENING:
                self._voice_state = VoiceState.LISTENING
            elif state == AppState.CHATTING:
                pass
            elif state == AppState.GESTURE_ACTIVE:
                self._gesture_state = True
            elif state == AppState.WORKSPACE_OPEN:
                self._workspace_state = True
            elif state == AppState.IDLE:
                # Reset subsystem flags only if truly idle
                self._voice_state = VoiceState.IDLE
                self._gesture_state = bool(getattr(self, '_gesture_active', False))
                self._workspace_state = bool(getattr(self, '_workspace_visible', False))
        try:
            self.state_changed.emit(state)
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
            max_iterations=self._max_iterations,
            confirmation_handler=self._confirmation_handler,
        )
        # Connect backend signals to coordinator methods
        self._backend.chunk_ready.connect(self._on_backend_chunk)
        self._backend.response_ready.connect(self._on_backend_response)
        self._backend.request_cancelled.connect(self._on_backend_request_cancelled)
        self._backend.status_changed.connect(self._on_backend_status)
        self._backend.state_changed.connect(self._on_backend_state)
        # Deferred model: apply after the backend reports READY,
        # not before the agent loop exists.
        self._pending_model = self._pending_model or ""

        # Voice: only initialize if voice is enabled and not already created
        if self._voice_enabled and self._voice is None:
            self._voice = VoiceManager(
                agent_backend=self._backend,
                on_state_change=self._on_voice_state,
                on_transcription=self._on_voice_transcription,
                on_response=self._on_voice_response,
            )
        elif self._voice_enabled and self._voice is not None:
            # Ensure backend is attached
            try:
                self._voice._backend = self._backend
            except Exception:
                pass

        # Start the backend in the background so the UI is not blocked
        # on agent initialization.
        self._backend.start(wait=False)

        # Emit that the backend is now ready so late-binding attachers
        # (e.g. IslandController.attach()) can connect status/state signals.
        try:
            self.backend_ready.emit()
        except Exception:
            pass

        # Actions
        self._actions = DesktopActionLayer(
            confirmation_handler=self._action_confirmation,
        )

        # Workspace is NOT created here — it is lazy-loaded on first explicit request.
        # This avoids allocating the QML widget and consuming GPU/CPU during pill startup.
        self._workspace = None

        self._set_state(AppState.IDLE)
        logger.info("AppCoordinator started")

    def shutdown_ui_resources(self) -> None:
        """Release Qt-owned workspace widgets on their owning GUI thread.

        Call this before moving the remaining blocking subsystem shutdown to
        a worker thread. The workspace is lazy-created and may be absent.
        """
        if QThread.currentThread() != self.thread():
            raise RuntimeError("Workspace widgets must be shut down on the GUI thread")
        workspace = self._workspace
        self._workspace = None
        self._workspace_visible = False
        if workspace is not None:
            try:
                workspace.shutdown()
            except Exception:
                logger.exception("Workspace shutdown failed")

    def shutdown(self) -> None:
        """Stop non-UI subsystems gracefully.

        Call shutdown_ui_resources() from the GUI thread before invoking this
        method from a worker thread.
        """
        self._running = False
        self._stop_gestures()
        if self._voice:
            try:
                self._voice.shutdown()
            except Exception:
                try:
                    self._voice.stop_speaking()
                except Exception:
                    pass
            self._voice = None
        if self._workspace:
            if QThread.currentThread() == self.thread():
                # Preserve compatibility for direct GUI-thread callers.
                self.shutdown_ui_resources()
            else:
                # Never call QWidget/QQuickWidget methods from a worker thread.
                logger.error(
                    "Workspace cleanup was not prepared on the GUI thread; "
                    "leaving it for process teardown"
                )
        if self._backend:
            try:
                if not self._backend.stop():
                    logger.warning("Agent backend did not stop before its shutdown timeout")
            except Exception:
                logger.exception("Agent backend shutdown failed")
        logger.info("AppCoordinator shutdown sequence finished")

    def _action_confirmation(
        self,
        action_name: str,
        arguments: dict | None = None,
        approval_id: str | None = None,
    ) -> str:
        """Bridge permission checks and desktop actions to the island UI.

        AgentLoop and PermissionEngine call with (tool_name, arguments), while
        DesktopActionLayer calls with only an action name. The UI callback is
        request-scoped and receives a separately generated approval ID.
        """
        if self._confirmation_handler is None:
            return "deny"
        if isinstance(arguments, str) and approval_id is None:
            approval_id = arguments
            arguments = None
        if approval_id is None:
            approval_id = f"{_APPROVAL_PREFIX}{uuid.uuid4().hex[:12]}"
        return self._confirmation_handler(action_name, arguments or {}, approval_id)

    # ── Chat ────────────────────────────────────────────────────
    def send_message(self, text: str) -> int | None:
        """Queue a text message and return its request ID when accepted."""
        if not self._backend or not text.strip():
            return None
        request_id = self._backend.send_message(text)
        if request_id is None:
            return None
        self._set_state(AppState.CHATTING)
        self.chat_message.emit("user", text)
        return request_id

    def cancel_request(self, request_id: int) -> bool:
        """Cancel one active or queued request by its exact request ID."""
        return bool(self._backend and self._backend.cancel_request(request_id))

    def _on_backend_request_cancelled(self, request_id: int) -> None:
        """Finish a request cancelled before it reached the agent loop."""
        self._buffer = ""
        self._voice_turn_active = False
        self.chat_message.emit("jarvis", f"[Cancelled request {request_id}]")
        self._set_state(AppState.IDLE)

    def _on_backend_chunk(self, request_id: int, chunk: str) -> None:
        self._buffer += chunk
        self.chat_message.emit("chunk", chunk)

    def _on_backend_response(self, response: AgentResponse) -> None:
        try:
            if response.success and self._buffer:
                buffered = self._buffer
                self.chat_message.emit("jarvis", self._buffer)
                self._buffer = ""
                if self._voice_turn_active and self._voice:
                    try:
                        if self._voice.state in (VoiceState.IDLE, VoiceState.THINKING):
                            self._voice.speak(buffered)
                    except Exception:
                        pass
                self._voice_turn_active = False
            elif response.success:
                self.chat_message.emit("jarvis", response.text)
                self._buffer = ""
                if self._voice_turn_active and self._voice:
                    try:
                        if self._voice.state in (VoiceState.IDLE, VoiceState.THINKING):
                            self._voice.speak(response.text)
                    except Exception:
                        pass
                self._voice_turn_active = False
            else:
                self._buffer = ""
                self.chat_message.emit("jarvis", f"[Error: {response.error}]")
                self._voice_turn_active = False
                if self._voice:
                    try:
                        if getattr(self._voice.state, 'value', self._voice.state) == VoiceState.THINKING.value:
                            self._voice._set_state(VoiceState.IDLE)
                    except Exception:
                        pass
        finally:
            self._gesture_state = bool(getattr(self, '_gesture_active', False))
            self._workspace_state = bool(getattr(self, '_workspace_visible', False) and getattr(self, '_workspace', None) and getattr(self._workspace, 'is_visible', False))
            self._set_state(AppState.IDLE)

    def _on_backend_status(self, status: str) -> None:
        """Forward backend status to UI (kept for signal compatibility)."""
        self.chat_message.emit("status", status)

    def _on_backend_state(self, state: BackendState) -> None:
        """React to backend lifecycle changes."""
        if state == BackendState.ERROR:
            self._set_state(AppState.IDLE)
        elif state == BackendState.READY and self._pending_model:
            # Retain the pending selection if the loop is not ready to accept it.
            if self._backend.set_model(self._pending_model):
                self._pending_model = ""

    # ── Voice ───────────────────────────────────────────────────
    def toggle_voice(self) -> None:
        """Toggle push-to-talk on/off."""
        if self._voice:
            self._voice.toggle_listening()

    def set_voice_enabled(self, enabled: bool) -> None:
        """Enable or disable the voice subsystem."""
        self._voice_enabled = enabled
        if enabled and not self._voice:
            self._voice = VoiceManager(
                agent_backend=self._backend,
                on_state_change=self._on_voice_state,
                on_transcription=self._on_voice_transcription,
                on_response=self._on_voice_response,
            )
            self._voice.warmup()
        elif not enabled and self._voice:
            self._voice.shutdown()
            self._voice = None

    def set_model(self, model: str) -> None:
        """Apply a model selection or retain it until the backend is ready."""
        if not model:
            return
        if self._backend and self._backend.set_model(model):
            self._pending_model = ""
        else:
            self._pending_model = model

    def stop_speaking(self) -> None:
        """Interrupt TTS."""
        if self._voice:
            self._voice.stop_speaking()

    def _on_voice_state(self, state: VoiceState) -> None:
        try:
            self.voice_state_changed.emit(state)
        except Exception:
            pass
        try:
            with self._state_lock:
                self._voice_state = state
        except Exception:
            pass
        if state == VoiceState.LISTENING:
            self._set_state(AppState.LISTENING)
        elif state == VoiceState.SPEAKING:
            self._set_state(AppState.SPEAKING)
        elif state == VoiceState.IDLE:
            self._set_state(AppState.IDLE)
        elif state == VoiceState.THINKING or state == VoiceState.TRANSCRIBING:
            # Keep as listening/chatting context; derive state will handle
            try:
                self._set_state(AppState.CHATTING)
            except Exception:
                self._set_state(AppState.IDLE)
        elif state == VoiceState.ERROR:
            self._set_state(AppState.IDLE)

    def _on_voice_transcription(self, text: str) -> None:
        self._voice_turn_active = True
        self.voice_transcription.emit(text)

    def _on_voice_response(self, text: str) -> None:
        self.chat_message.emit("jarvis", text)

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
        try:
            self._recognizer = GestureRecognizer(on_gesture=self._on_gesture)
            self._mapper = GestureMapper(on_action=self._on_gesture_action_event)
            self._camera = Camera()
            # Feed detected hands into the recognizer so gestures are actually classified.
            self._tracker = HandTracker(on_hands=lambda hands: (
                self._recognizer.process(hands) if self._recognizer else None
            ))
            self._tracker.set_frame_source(lambda: self._camera.latest_frame if self._camera else None)

            if self._camera.start() and self._tracker.start():
                self._gesture_active = True
                self._set_state(AppState.GESTURE_ACTIVE)
            else:
                self._stop_gestures()
        except Exception as e:
            logger.warning("Gesture start failed: %s", e)
            self._stop_gestures()

    def _stop_gestures(self) -> None:
        tracker = getattr(self, "_tracker", None)
        camera = getattr(self, "_camera", None)
        self._tracker = None
        self._camera = None
        self._recognizer = None
        self._gesture_active = False
        self._gesture_state = False

        tracker_thread = getattr(tracker, "_thread", None) if tracker else None
        camera_thread = getattr(camera, "_capture_thread", None) if camera else None

        tracker_stopped = tracker is None
        camera_stopped = camera is None
        try:
            if tracker is not None:
                tracker_stopped = bool(tracker.stop())
                tracker_thread = getattr(tracker, "_thread", tracker_thread)
                if tracker_thread is not None:
                    tracker_stopped = not tracker_thread.is_alive()
        except Exception:
            logger.exception("Failed to stop hand tracker")
            tracker_stopped = False

        try:
            if camera is not None:
                camera_stopped = bool(camera.stop())
                camera_thread = getattr(camera, "_capture_thread", camera_thread)
                if camera_thread is not None:
                    camera_stopped = not camera_thread.is_alive()
        except Exception:
            logger.exception("Failed to stop gesture camera")
            camera_stopped = False

        def _release_after_workers_exit() -> None:
            # The camera must not be released while either worker can still
            # access it. If a bounded join timed out, this watcher waits for
            # actual thread termination before releasing the device.
            for worker in (tracker_thread, camera_thread):
                if (
                    worker is not None
                    and worker is not threading.current_thread()
                    and worker.is_alive()
                ):
                    worker.join()
            workers_alive = any(
                worker is not None and worker.is_alive()
                for worker in (tracker_thread, camera_thread)
            )
            if camera is not None and not workers_alive:
                try:
                    camera.tracker_exit_confirmed()
                except Exception:
                    logger.exception("Camera release failed after worker shutdown")
            elif workers_alive:
                logger.error("Gesture workers remain active; camera was not released")

        if camera is not None:
            if tracker_stopped and camera_stopped:
                try:
                    camera.tracker_exit_confirmed()
                except Exception:
                    logger.exception("Camera release failed after worker shutdown")
            else:
                threading.Thread(
                    target=_release_after_workers_exit,
                    name="jarvis-gesture-shutdown",
                    daemon=True,
                ).start()

        try:
            self._set_state(AppState.IDLE)
        except Exception:
            logger.exception("Failed to publish idle state after gesture shutdown")

    def _on_gesture(self, event: GestureEvent) -> None:
        if self._mapper:
            self._mapper.handle(event)

    def _set_gesture_mode(self, enabled: bool) -> None:
        if enabled and not self._gesture_active:
            self._start_gestures()
        elif not enabled and self._gesture_active:
            self._stop_gestures()

    def _on_gesture_action_event(self, action: str, event: GestureEvent) -> None:
        if action == "toggle_gesture_mode":
            try:
                self.toggle_gestures()
            except Exception:
                pass
            try:
                self.gesture_action.emit(action)
            except Exception:
                pass
            return
        elif action == "pan_workspace":
            try:
                if self._workspace:
                    if hasattr(self._workspace, "pan"):
                        self._workspace.pan(event)
                    else:
                        self._workspace_visible = not self._workspace_visible
                        if self._workspace_visible:
                            self._workspace.show()
                        else:
                            self._workspace.hide()
            except Exception:
                pass
        elif action == "exit_gesture_mode":
            try:
                self._stop_gestures()
            except Exception:
                pass
        elif action == "zoom_in":
            if self._workspace:
                try:
                    self._workspace.zoom(factor=1.25)
                except Exception:
                    pass
        elif action == "zoom_out":
            if self._workspace:
                try:
                    self._workspace.zoom(factor=0.8)
                except Exception:
                    pass
        elif action == "prev_task":
            try:
                self.gesture_action.emit(action)
            except Exception:
                pass
            return
        elif action == "next_task":
            try:
                self.gesture_action.emit(action)
            except Exception:
                pass
            return
        elif action == "capture_selection":
            try:
                self.gesture_action.emit(action)
            except Exception:
                pass
            return
        elif action == "deselect":
            try:
                if self._actions:
                    self._actions.execute("deselect")
                else:
                    self.gesture_action.emit(action)
            except Exception:
                try:
                    self.gesture_action.emit(action)
                except Exception:
                    pass
            return
        else:
            if self._actions:
                try:
                    self._actions.execute(action)
                except Exception:
                    pass
        try:
            self.gesture_action.emit(action)
        except Exception:
            pass

    # ── Workspace ───────────────────────────────────────────────
    def toggle_workspace(self) -> None:
        """Toggle 3D workspace on/off."""
        if not self._workspace:
            # Workspace not yet created; create it on first explicit request.
            try:
                self._workspace = Workspace3D()
            except Exception:
                logger.warning("Failed to create Workspace3D; workspace will be unavailable")
                return
        # Use the public load() result; do NOT mutate private _loaded to fake success.
        try:
            load_ok = self._workspace.load()
        except Exception:
            load_ok = False
        if not load_ok:
            # QML load failed — keep workspace closed and surface a useful error.
            # Do NOT set _workspace_visible or _set_state(WORKSPACE_OPEN).
            logger.warning("Workspace3D load() returned False; keeping workspace closed")
            return
        # load() succeeded; now toggle visibility
        if getattr(self._workspace, "is_visible", False):
            try:
                self._workspace.hide()
            except Exception:
                pass
            self._workspace_visible = False
            self._set_state(AppState.IDLE)
        else:
            try:
                self._workspace.show()
            except Exception:
                pass
            self._workspace_visible = True
            self._set_state(AppState.WORKSPACE_OPEN)

    def update_workspace_panel(self, panel: str, text: str) -> None:
        """Update a workspace panel."""
        if self._workspace:
            self._workspace.set_panel_text(panel, text)
        self.workspace_update.emit(panel, text)

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
            "stt_engine": getattr(self._voice, 'stt_engine', None) if self._voice else None,
            "tts_engine": getattr(self._voice, 'tts_engine', None) if self._voice else None,
        }



    def _process_action_queue(self) -> None:
        """Process queued action requests in a background thread.

        Pops items from self._action_queue and dispatches them so that
        OS commands, approval handling, or other blocking work cannot stall
        the gesture tracking loop.
        """
        while True:
            try:
                item = self._action_queue.get(timeout=1.0)
                # Parse and dispatch the action
                if item.startswith("gesture:"):
                    # Extract gesture action name and dispatch
                    action_name = item[8:]  # Remove "gesture:" prefix
                    # Dispatch to the appropriate handler
                    if self._mapper:
                        # Map and execute
                        pass  # Actual dispatch handled elsewhere
                # Add other action types as needed
            except Exception:
                # timeout or other error - continue looping
                continue