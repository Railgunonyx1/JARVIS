"""Dynamic Island for JARVIS Desktop.

A top-center always-on-top pill that morphs between three states:
  idle      — compact pill, quiet, shows live status
  compact   — hover: widens to reveal detail
  expanded  — click: compact conversation panel

The window owns only presentation: chrome, geometry, and the state machine.
Runtime coupling lives in IslandController; conversation lives in
ConversationPanel. No agent/permission/tool logic here.
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from app.voice.voice_manager import VoiceState

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QMutexLocker,
    QEvent,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger("jarvis.desktop.island")

_TOP_MARGIN = 4
_IDLE_W, _IDLE_H = 180, 36
_COMPACT_W, _COMPACT_H = 320, 44
_EXPANDED_W, _EXPANDED_H = 480, 620
_EXPANDED_HEIGHT = _EXPANDED_H
_RADIUS = 20
_EXIT_DELAY_MS = 180
_MARGIN = 10
_SCREEN_SIGNALS = (
    "geometryChanged",
    "availableGeometryChanged",
    "availableGeometryChanged",
    "logicalDotsPerInchChanged",
    "physicalDotsPerInchChanged",
)


# Design tokens — classic dark glass palette from DI-025 (matched to conversation_panel.py)
_PRIMARY = "#141619"
_ACCENT  = "#8C96A3"
_TEXT   = "#EBEEF2"
_MUTED   = "#B0B7C1"
_DIVIDER = "#3A3A3C"
_INPUT_BG = "#2C1C2E"
_INPUT_FG = "#FFFFFF"
_BLUE    = "#0A84FF"
_BLUE_H  = "#0071E3"
_AMBER   = "#FFD60A"
_DARK_BG = "#272B30"
_DARK_DK = "#172431"


class IslandState(Enum):
    IDLE = "idle"
    COMPACT = "compact"
    EXPANDED = "expanded"


# Approval lifecycle: request-scoped IDs, event-based resolution, no shared mutable slot
from PySide6.QtCore import QObject, QWaitCondition, QMutex
import uuid
from collections.abc import Callable

_PENDING = "pending"
_APPROVED = "approved_once"
_DENIED = "denied"
_EXPIRED = "expired"
_CANCELLED = "cancelled"
_FAILED = "failed"
_APPROVAL_TIMEOUT_SECONDS = 10.0


class ApprovalRecord(QObject):
    """Request-scoped approval record with a single terminal transition.

    Adapted concept: an explicit, request-scoped consent gateway with a single
    terminal transition, drawn from the FatihMakes approval/confirmation pattern
    (Mark-LVI-style ``undo.py``/``confirm.py`` shape). Adapted to JARVIS by
    making the record itself the authority, not a shared mutable flag, and by
    rejecting stale/duplicate/late decisions at the record level.

    Each approval gets a unique ``approval_id``. The state machine ensures exactly
    one terminal transition: ``approved_once | denied | expired | cancelled | failed``.
    Stale or late clicks are ignored.
    """

    def __init__(self, approval_id: str, tool_name: str, arguments: dict):
        super().__init__()
        self.approval_id = approval_id
        self.tool_name = tool_name
        self.arguments = arguments
        self.mutex = QMutex()
        self.wait_condition = QWaitCondition()
        self._state = _PENDING
        # UI callback reference (weak: set to None on resolve)
        self._decision_sink: Callable[[str], None] | None = None

    @property
    def state(self) -> str:
        with QMutexLocker(self.mutex):
            return self._state

    def transition(self, state: str) -> bool:
        """Atomically perform the only permitted transition from pending."""
        if state not in (_APPROVED, _DENIED, _EXPIRED, _CANCELLED, _FAILED):
            raise ValueError(f"not an approval terminal state: {state}")
        with QMutexLocker(self.mutex):
            if self._state != _PENDING:
                return False
            self._state = state
            self.wait_condition.wakeAll()
            return True

    def approve(self) -> bool:
        """Transition to approved_once, or reject a duplicate/stale decision."""
        return self.transition(_APPROVED)

    def deny(self) -> bool:
        """Transition to denied, or reject a duplicate/stale decision."""
        return self.transition(_DENIED)

    def expire(self) -> bool:
        """Transition to expired, or reject a duplicate/stale decision."""
        return self.transition(_EXPIRED)

    def cancel(self) -> bool:
        """Transition to cancelled when the originating request is cancelled."""
        return self.transition(_CANCELLED)

    def fail(self) -> bool:
        """Transition to failed when the originating request errors out."""
        return self.transition(_FAILED)

    def is_terminal(self) -> bool:
        """Check if the approval has reached a terminal state."""
        return self.state in (_APPROVED, _DENIED, _EXPIRED, _CANCELLED, _FAILED)

    def wait(self, timeout: float = _APPROVAL_TIMEOUT_SECONDS) -> str:
        """Wait for one terminal transition; timeout races use first-writer-wins."""
        deadline = time.monotonic() + timeout
        while True:
            with QMutexLocker(self.mutex):
                if self._state != _PENDING:
                    return self._state
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.wait_condition.wait(self.mutex, max(1, int(remaining * 1000)))
            if time.monotonic() >= deadline:
                break
        self.transition(_EXPIRED)
        return self.state


class IslandWindow(QWidget):
    """Top-center morphing island overlay."""

    _approval_requested = Signal(str, object, str)
    _approval_finished = Signal(str)

    def __init__(self, controller=None) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._state = IslandState.IDLE
        self._panel = None
        self._controller = controller
        self._quitting = False
        # Registry: approval_id -> ApprovalRecord, protects against stale events
        self._approval_registry: dict[str, ApprovalRecord] = {}
        self._approval_registry_mutex = QMutex()
        self._approval_queue: list[str] = []
        self._approval_ui_lock = threading.RLock()
        self._active_approval_id: str | None = None
        self._last_status_before_approval = ("Ready", "")
        self._watched_screen = None

        self._build()

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._exit_timer = QTimer(self)
        self._exit_timer.setSingleShot(True)
        self._exit_timer.setInterval(_EXIT_DELAY_MS)
        self._exit_timer.timeout.connect(self._maybe_collapse)

        if self._controller is not None:
            self._controller.view_changed.connect(self._on_view_changed)
            self._controller.chat_message.connect(self._on_chat_message)
            self._controller.stream_chunk.connect(self._on_stream_chunk)
            self._controller.transcription.connect(self._on_transcription)

        self.resize(_IDLE_W, _IDLE_H)
        self._reposition()
        self._approval_requested.connect(self._show_approval)
        self._approval_finished.connect(self._on_approval_finished)

        app = QApplication.instance()
        if app is not None:
            app.screenAdded.connect(self._on_screens_changed)
            app.screenRemoved.connect(self._on_screens_changed)
            app.primaryScreenChanged.connect(self._on_screens_changed)
            self._watch_screen()

    # ── Approval lifecycle ─────────────────────────────────────────
    def _generate_approval_id(self, tool_name: str, arguments: dict) -> str:
        """Generate a unique approval_id from request context."""
        # Use request_id (tool call context) + UUID suffix for uniqueness
        ctx = f"{tool_name}@{hash(str(arguments)) % 100000}"
        return f"approval-{uuid.uuid4().hex[:12]}"

    def _register_approval(self, record: ApprovalRecord) -> bool:
        with QMutexLocker(self._approval_registry_mutex):
            if record.approval_id in self._approval_registry:
                return False
            self._approval_registry[record.approval_id] = record
            return True

    def _get_approval(self, approval_id: str) -> ApprovalRecord | None:
        with QMutexLocker(self._approval_registry_mutex):
            return self._approval_registry.get(approval_id)

    def _resolve_approval(self, approval_id: str, state: str) -> None:
        """Resolve and remove one request without overwriting a terminal result."""
        with QMutexLocker(self._approval_registry_mutex):
            record = self._approval_registry.get(approval_id)
            if record is None:
                return
            if state in (_APPROVED, _DENIED, _EXPIRED, _CANCELLED, _FAILED):
                record.transition(state)
            if self._approval_registry.get(approval_id) is record:
                self._approval_registry.pop(approval_id, None)

    # ── UI ───────────────────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        # Margin leaves room for the drop shadow; it is clipped otherwise.
        root.setContentsMargins(_MARGIN, _MARGIN, _MARGIN, _MARGIN)
        root.setSpacing(0)

        self._card = QFrame()
        self._card.setObjectName("islandCard")
        self._card.setStyleSheet(f"""
            #islandCard {{
                background: rgba(20, 20, 22, 235);
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: {_RADIUS}px;
            }}
            #islandTitle {{ color: {_TEXT}; font-size: 13px; font-weight: 600; }}
            #islandStatus {{ color: {_MUTED}; font-size: 11px; }}
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 6)
        self._card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(14, 0, 14, 0)
        card_layout.setSpacing(0)

        bar = QWidget()
        bar.setFixedHeight(_IDLE_H)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(8)

        self._title = QLabel("JARVIS")
        self._title.setObjectName("islandTitle")
        self._title.setToolTip("Right-click for Hide / Quit")
        self._title.setStyleSheet(
            "QLabel { color: #EBEEF2; font-size: 13px; font-weight: 700; letter-spacing: 0.5px; }"
        )
        bar_layout.addWidget(self._title)

        self._dot = QLabel("\u25CF")
        self._dot.setObjectName("islandStatus")
        self._dot.setStyleSheet(f"color: {_ACCENT}; font-size: 8px; font-weight: 700;")
        bar_layout.addWidget(self._dot)

        self._status = QLabel("Ready")
        self._status.setObjectName("islandStatus")
        self._status.setStyleSheet(
            "QLabel { color: #B0B7C1; font-size: 10px; font-weight: 600; "
            "letter-spacing: 0.3px; }"
        )
        self._status.setToolTip("Ready")
        bar_layout.addWidget(self._status, 1)

        self._state_label = QLabel("Idle")
        self._state_label.setStyleSheet(
            "QLabel { color: #8C96A3; font-size: 9px; font-weight: 600; "
            "letter-spacing: 0.5px; text-transform: uppercase; }"
        )
        bar_layout.addWidget(self._state_label)

        self._close_btn = QPushButton("\u2715")
        self._close_btn.setFixedSize(22, 22)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #B0B7C1; border-radius: 11px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.1); color: #EBEEF2; }"
            "QPushButton:focus { outline: 2px solid #FFD60A; outline-offset: 2px; border-radius: 11px; }"
            "QPushButton:pressed { background: rgba(255,255,255,0.2); }"
        )
        self._close_btn.setToolTip("Collapse island")
        self._close_btn.clicked.connect(self.collapse)
        self._close_btn.hide()
        bar_layout.addWidget(self._close_btn)

        self._app_icon = QLabel()
        self._app_icon.setFixedSize(14, 14)
        self._app_icon.setStyleSheet("color: #8C96A3; "
                                     "border-radius: 7px; "
                                     "font-size: 10px; "
                                     "font-weight: 700; "
                                     "text-align: center; "
                                     "padding: 2px; "
                                     )
        bar_layout.addWidget(self._app_icon)

        card_layout.addWidget(bar)

        self._host = QVBoxLayout()
        self._host.setContentsMargins(0, 0, 0, 0)
        card_layout.addLayout(self._host)

        root.addWidget(self._card)

    def _ensure_panel(self):
        if self._panel is None:
            from app.ui.conversation_panel import ConversationPanel
            self._panel = ConversationPanel()
            self._panel.input_field.installEventFilter(self)
            self._panel.send_requested.connect(self._on_send)
            self._panel.mic_toggled.connect(self._on_mic)
            # Bind coordinator signals if available
            try:
                coord = getattr(self._controller, "coordinator", None) if self._controller else None
                if coord is not None and hasattr(coord, "voice_state_changed"):
                    coord.voice_state_changed.connect(self._on_voice_state_changed)
            except Exception:
                pass
            self._host.addWidget(self._panel)
        return self._panel

    def _start_backend(self) -> None:
        if self._controller is None:
            return
        if getattr(self._controller, "coordinator", None) is not None:
            return
        from app.integration.coordinator import AppCoordinator
        from app.settings import load

        settings = load()
        coord = AppCoordinator(mode="agent", confirmation_handler=self._confirm)
        coord.set_voice_enabled(bool(settings.get("voice_enabled", True)))
        if settings.get("model"):
            coord.set_model(settings["model"])
        coord.start()
        try:
            self._controller.attach(coord)
        except Exception as exc:
            logger.error("Backend attachment failed: %s", exc)
            # Surface the backend failure as an island status so the user
            # can see that the UI is not fully connected. Do not swallow
            # the exception — the error is logged and the UI state is
            # updated.
            try:
                from app.ui.island_controller import IslandStatus
            except Exception:
                IslandStatus = None  # type: ignore[assignment]

            if IslandStatus is not None:
                self._controller.set_status(IslandStatus.ERROR, "Backend failed to attach")
            # If a panel was built, surface the error there as well.
            if getattr(self, "_panel", None) is not None:
                try:
                    self._panel.set_approval(
                        None, "Backend connection failed: " + str(exc), None
                    )
                except Exception:
                    pass
        # If panel already created, bind signals
        try:
            if getattr(self, "_panel", None) is not None and hasattr(coord, "voice_state_changed"):
                try:
                    coord.voice_state_changed.connect(self._on_voice_state_changed)
                except Exception as exc:
                    logger.warning("Failed to bind voice_state_changed: %s", exc)
        except Exception as exc:
            logger.warning("Failed to bind voice_state_changed signals: %s", exc)

    def _confirm(self, tool_name: str, arguments: dict, approval_id: str | None = None) -> str:
        """Approval handler — runs on the agent worker thread.

        Accepts a request-scoped approval_id from the caller when available,
        otherwise generates one. Registers the record, emits the decision UI
        to the GUI thread, and waits event-based for a single terminal
        transition: approved_once | denied | expired | cancelled | failed.
        Stale or late events are ignored.

        The GUI thread delivers the decision via _on_approval_decision, which
        sets the record's terminal state.
        """
        import uuid as _uuid

        if approval_id is None:
            approval_id = f"approval-{_uuid.uuid4().hex[:12]}"

        record = ApprovalRecord(approval_id, tool_name, arguments)
        if not self._register_approval(record):
            return "deny"
        # Emit to GUI thread with approval_id. The panel's per-ID sink will
        # route the operator's decision back to this exact record.
        self.set_status("Approval", detail=f"{tool_name}: approval required")
        self._approval_requested.emit(tool_name, arguments, approval_id)
        # Wait event-based (no busy-wait sleep)
        try:
            terminal = record.wait(timeout=_APPROVAL_TIMEOUT_SECONDS)
            return "once" if terminal == _APPROVED else "deny"
        finally:
            self._resolve_approval(approval_id, record.state)
            self._approval_finished.emit(approval_id)

    def _show_approval(self, tool_name: str, arguments: dict, approval_id: str) -> None:
        panel = self._ensure_panel()
        record = self._get_approval(approval_id)
        if record is None:
            return
        if record._decision_sink is None:
            record._decision_sink = lambda decision: self._on_approval_decision(
                record, decision in ("once", "run", True)
            )
        from app.ui.conversation_panel import ApprovalSink
        panel._approval_sinks[approval_id] = ApprovalSink(
            approval_id, record._decision_sink
        )
        with self._approval_ui_lock:
            self._approval_queue.append(approval_id)
            if self._active_approval_id is None:
                self._present_next_approval()

    def _present_next_approval(self) -> None:
        if self._panel is None or not self._approval_queue:
            self._active_approval_id = None
            return
        while self._approval_queue:
            approval_id = self._approval_queue.pop(0)
            record = self._get_approval(approval_id)
            if record is None or record.is_terminal():
                continue
            self._active_approval_id = approval_id
            self._panel.request_approval(record.tool_name, record.arguments, approval_id)
            self._panel.set_approval(
                record.tool_name, self._preview_arguments(record.arguments), approval_id
            )
            if self._state is not IslandState.EXPANDED:
                self.expand()
            return
        self._active_approval_id = None

    def _on_approval_finished(self, approval_id: str) -> None:
        with self._approval_ui_lock:
            if self._panel is not None:
                self._panel._approval_sinks.pop(approval_id, None)
            if self._active_approval_id == approval_id:
                self._active_approval_id = None
                if self._panel is not None:
                    self._panel.set_approval(None, "", None)
                if self._approval_queue:
                    next_record = self._get_approval(self._approval_queue[0])
                    if next_record is not None:
                        self.set_status("Approval", detail=f"{next_record.tool_name}: approval required")
                    self._present_next_approval()
                else:
                    label, detail = self._last_status_before_approval
                    self.set_status(label or "Ready", detail=detail)
            else:
                self._approval_queue = [
                    pending_id for pending_id in self._approval_queue
                    if pending_id != approval_id
                ]

    def _on_approval_decision(self, record: ApprovalRecord, allow: bool) -> None:
        if allow:
            record.approve()
        else:
            record.deny()

    def _deny_pending(self) -> None:
        """Resolve all pending approvals to deny before hiding/quitting."""
        with self._approval_ui_lock:
            self._approval_queue.clear()
            self._active_approval_id = None
            label, detail = self._last_status_before_approval
            self.set_status(label or "Ready", detail=detail)
            if self._panel is not None:
                self._panel.set_approval(None, "", None)
            with QMutexLocker(self._approval_registry_mutex):
                pending = list(self._approval_registry.values())
                self._approval_registry.clear()
            for record in pending:
                record.deny()

    @staticmethod
    def _preview_arguments(arguments: dict) -> str:
        """Compact, redacted argument preview (never full payloads)."""
        if not arguments:
            return ""
        sensitive = ("password", "secret", "token", "api_key", "apikey", "credential")
        parts = []
        for name, value in list(arguments.items())[:3]:
            if any(s in name.lower() for s in sensitive):
                shown = "\u2022\u2022\u2022"
            else:
                shown = str(value)
                if len(shown) > 60:
                    shown = shown[:57] + "\u2026"
            parts.append(f"{name}={shown}")
        text = ", ".join(parts)
        if len(arguments) > 3:
            text += f" (+{len(arguments) - 3} more)"
        return text

    def _on_send(self, text: str) -> None:
        if self._controller and self._controller.coordinator is not None:
            self._controller.coordinator.send_message(text)

    def _on_mic(self) -> None:
        if self._controller and self._controller.coordinator is not None:
            self._controller.coordinator.toggle_voice()

    def _on_voice_state_changed(self, state: object) -> None:
        panel = self._ensure_panel()
        if panel is not None:
            panel.set_listening(state == VoiceState.LISTENING)

    def _on_chat_message(self, role: str, text: str) -> None:
        panel = self._ensure_panel()
        if role == "chunk":
            panel.append_chunk(text)
        else:
            panel.append_message(role, text)

    def _on_stream_chunk(self, text: str) -> None:
        self._ensure_panel().append_chunk(text)

    def _on_transcription(self, text: str) -> None:
        panel = self._ensure_panel()
        panel.append_message("user", text)

    # ── State machine ────────────────────────────────────────────
    def _on_screens_changed(self, *_args) -> None:
        self._watch_screen()
        self._reposition()

    def _watch_screen(self) -> None:
        """Track geometry/DPI changes on the screen the island lives on."""
        screen = self._active_screen()
        if screen is self._watched_screen:
            return
        previous = self._watched_screen
        if previous is not None:
            for name in _SCREEN_SIGNALS:
                try:
                    getattr(previous, name).disconnect(self._on_screens_changed)
                except (RuntimeError, TypeError):
                    pass
        self._watched_screen = screen
        if screen is not None:
            for name in _SCREEN_SIGNALS:
                getattr(screen, name).connect(self._on_screens_changed)

    def _active_screen(self):
        if self._watched_screen is not None and self._watched_screen in QGuiApplication.screens():
            return self._watched_screen
        screen = QGuiApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is not None:
            self._watched_screen = screen
        return screen

    def _target_rect(self, state: IslandState) -> QRect:
        screen = self._active_screen()
        if screen is None or screen not in QGuiApplication.screens():
            screen = QApplication.primaryScreen()
            if screen is not None:
                self._watched_screen = screen
        geo = screen.availableGeometry() if screen else None
        if state is IslandState.IDLE:
            w, h = _IDLE_W, _IDLE_H
        elif state is IslandState.COMPACT:
            w, h = _COMPACT_W, _COMPACT_H
        else:
            w, h = _EXPANDED_W, _EXPANDED_H
        if geo is None:
            return self.geometry()
        w = min(w + 2 * _MARGIN, geo.width())
        h = min(h + 2 * _MARGIN, geo.height() - 2 * _TOP_MARGIN)
        # Fallback geometry for environments where KWin does not reposition the
        # window (non-KDE Wayland, no client-area knowledge). The KWin script
        # packaged with the installer is the authoritative placement on KDE
        # Wayland; it uses workspace.clientArea() which accounts for the panel
        # and panel-taskbar insets. This fallback only applies the top margin
        # and horizontal centre so the island never lands dead-centre.
        x = geo.left() + (geo.width() - w) // 2
        y = geo.top() + _TOP_MARGIN
        return QRect(x, y, w, h)

    def _reposition(self) -> None:
        self._watch_screen()
        self.setGeometry(self._target_rect(self._state))

    def _set_state(self, state: IslandState) -> None:
        if state is self._state:
            return
        self._state = state
        expanded = state is IslandState.EXPANDED
        self._close_btn.setVisible(expanded)
        if expanded:
            self._ensure_panel()
            # Defer backend construction off the animation path: importing the
            # agent stack + constructing the coordinator costs ~190ms and would
            # stagger the morph. Let the animation start first.
            QTimer.singleShot(0, self._start_backend)
        else:
            self._exit_timer.stop()
        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(self._target_rect(state))
        self._anim.start()

    def expand(self) -> None:
        self._set_state(IslandState.EXPANDED)
        if self._panel is not None:
            # This method is reached from an explicit user click or keyboard
            # action, so activating the window here is intentional. Hover
            # expansion remains non-activating.
            self.activateWindow()
            self._panel.input_field.setFocus(Qt.FocusReason.OtherFocusReason)

    def collapse(self) -> None:
        self._set_state(IslandState.IDLE)

    def hide_island(self) -> None:
        """Hide without terminating the runtime (task continuity preserved)."""
        self._exit_timer.stop()
        self._deny_pending()
        self.hide()

    def quit_application(self) -> None:
        """Full shutdown: stop the runtime, then exit the process."""
        self._quitting = True
        self._deny_pending()
        if self._controller and self._controller.coordinator is not None:
            try:
                self._controller.coordinator.shutdown()
            except Exception as e:  # noqa: BLE001
                logger.warning("Coordinator shutdown failed: %s", e)
        QApplication.quit()

    def _on_view_changed(self, view) -> None:
        self.set_status(view.status.label, view.status.color, view.detail)

    def set_status(self, text: str, color: str = "#8E8E93", detail: str = "") -> None:
        self._status.setText(text)
        self._dot.setStyleSheet(f"color: {color}; font-size: 8px; font-weight: 700;")
        # Map backend status labels to compact state labels
        if text == "Ready":
            self._state_label.setText("Idle")
            self._state_label.setStyleSheet(
                "QLabel { color: #8C96A3; font-size: 9px; font-weight: 600; "
                "letter-spacing: 0.5px; text-transform: uppercase; }"
            )
        elif text in ("Listening", "Thinking", "Speaking", "Working", "Starting"):
            self._state_label.setText(text[:10].title())
            self._state_label.setStyleSheet(
                "QLabel { color: #8C96A3; font-size: 9px; font-weight: 600; "
                "letter-spacing: 0.5px; text-transform: uppercase; }"
            )
        elif text == "Error":
            self._state_label.setText("Error")
            self._state_label.setStyleSheet(
                "QLabel { color: #FF6B6B; font-size: 9px; font-weight: 600; "
                "letter-spacing: 0.5px; text-transform: uppercase; }"
            )
        elif text == "Approval":
            self._state_label.setText("Approval")
            self._state_label.setStyleSheet(
                "QLabel { color: #FFD60A; font-size: 9px; font-weight: 600; "
                "letter-spacing: 0.5px; text-transform: uppercase; }"
            )
        self._status.setToolTip(detail)
        if detail:
            self._status.setToolTip(f"{text}: {detail}")

    # ── Interaction ──────────────────────────────────────────────
    def enterEvent(self, event) -> None:
        self._exit_timer.stop()
        if self._state is IslandState.IDLE:
            self._set_state(IslandState.COMPACT)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self._state is IslandState.COMPACT:
            self._exit_timer.start()
        super().leaveEvent(event)

    def _maybe_collapse(self) -> None:
        if self._state is IslandState.COMPACT and not self.underMouse():
            self._set_state(IslandState.IDLE)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._state is not IslandState.EXPANDED:
                self.expand()

    def eventFilter(self, watched, event) -> bool:
        input_field = getattr(self._panel, "input_field", None)
        if (
            watched is input_field
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
            and self._state is IslandState.EXPANDED
        ):
            self.collapse()
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._state is IslandState.EXPANDED:
            self.collapse()
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        hide_action = menu.addAction("Hide island")
        quit_action = menu.addAction("Quit JARVIS Island")
        chosen = menu.exec(event.globalPos())
        if chosen is quit_action:
            self.quit_application()
        elif chosen is hide_action:
            self.hide_island()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reposition()

    def closeEvent(self, event) -> None:
        # Closing the window hides the island; it does not kill the runtime.
        if not self._quitting:
            event.ignore()
            self.hide_island()
            return
        event.accept()
