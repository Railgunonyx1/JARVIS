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
from enum import Enum
from app.voice.voice_manager import VoiceState

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
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

_TOP_MARGIN = 8
_IDLE_W, _IDLE_H = 180, 36
_COMPACT_W, _COMPACT_H = 320, 44
_EXPANDED_W, _EXPANDED_H = 480, 620
_RADIUS = 20
_EXIT_DELAY_MS = 180
_MARGIN = 10
_SCREEN_SIGNALS = (
    "geometryChanged",
    "availableGeometryChanged",
    "logicalDotsPerInchChanged",
    "physicalDotsPerInchChanged",
)


class IslandState(Enum):
    IDLE = "idle"
    COMPACT = "compact"
    EXPANDED = "expanded"


# Approval lifecycle: request-scoped IDs, event-based resolution, no shared mutable slot
from PySide6.QtCore import QObject, QWaitCondition, QMutex, QLocale
import uuid

_PENDING = "pending"
_APPROVED = "approved_once"
_DENIED = "denied"
_EXPIRED = "expired"
_CANCELLED = "cancelled"
_FAILED = "failed"


class ApprovalRecord(QObject):
    """Request-scoped approval record with a single terminal transition.

    Each approval gets a unique approval_id. The state machine ensures exactly
    one terminal transition: approved_once | denied | expired | cancelled | failed.
    Stale or late clicks are ignored.
    """

    def __init__(self, approval_id: str, tool_name: str, arguments: dict):
        super().__init__()
        self.approval_id = approval_id
        self.tool_name = tool_name
        self.arguments = arguments
        self.state = _PENDING
        self.mutex = QMutex()
        self.wait_condition = QWaitCondition()
        # UI callback reference (weak: set to None on resolve)
        self._decision_sink: Callable[[str], None] | None = None

    def approve(self) -> None:
        """Transition to approved_once — single terminal transition."""
        with QMutexLocker(self.mutex) as locker:
            if self.state != _PENDING:
                return  # stale; already resolved
            self.state = _APPROVED
            self.wait_condition.wakeAll()

    def deny(self) -> None:
        """Transition to denied — single terminal transition."""
        with QMutexLocker(self.mutex) as locker:
            if self.state != _PENDING:
                return  # stale; already resolved
            self.state = _DENIED
            self.wait_condition.wakeAll()

    def expire(self) -> None:
        """Transition to expired — single terminal transition."""
        with QMutexLocker(self.mutex) as locker:
            if self.state != _PENDING:
                return  # stale; already resolved
            self.state = _EXPIRED
            self.wait_condition.wakeAll()

    def is_terminal(self) -> bool:
        """Check if the approval has reached a terminal state."""
        return self.state in (_APPROVED, _DENIED, _EXPIRED, _CANCELLED, _FAILED)

    def wait(self, timeout: float = 10.0) -> str:
        """Block until a terminal state is reached or timeout expires.

        Returns the terminal state string, or _EXPIRED if timeout.
        Uses QWaitCondition for event-based wakeup instead of busy-wait sleep.
        """
        with QMutexLocker(self.mutex) as locker:
            # Wait until terminal or timeout
            result = self.wait_condition.wait(self.mutex, int(timeout * 1000))
            if self.state == _PENDING:
                # Timed out while still pending
                self.state = _EXPIRED
                self.wait_condition.wakeAll()
            return self.state


class IslandWindow(QWidget):
    """Top-center morphing island overlay."""

    _approval_requested = Signal(str, object, str)  # (tool_name, arguments, approval_id)

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

        self._state = IslandState.IDLE
        self._panel = None
        self._controller = controller
        self._quitting = False
        # Registry: approval_id -> ApprovalRecord, protects against stale events
        self._approval_registry: dict[str, ApprovalRecord] = {}
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

        self._approval_requested.connect(self._show_approval)

        self.resize(_IDLE_W, _IDLE_H)
        self._reposition()

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

    def _register_approval(self, record: ApprovalRecord) -> None:
        """Register an approval record in the registry."""
        self._approval_registry[record.approval_id] = record

    def _unregister_approval(self, approval_id: str) -> None:
        """Unregister an approval record."""
        self._approval_registry.pop(approval_id, None)

    def _resolve_approval(self, approval_id: str, state: str) -> None:
        """Resolve an approval to a terminal state and clean up."""
        record = self._approval_registry.pop(approval_id, None)
        if record is None:
            return  # stale; already cleaned up
        record.state = state
        record.wait_condition.wakeAll()

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
            #islandTitle {{ color: #FFFFFF; font-size: 13px; font-weight: 600; }}
            #islandStatus {{ color: #8E8E93; font-size: 11px; }}
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
        bar_layout.addWidget(self._title)

        self._dot = QLabel("\u25cf")
        self._dot.setObjectName("islandStatus")
        bar_layout.addWidget(self._dot)

        self._status = QLabel("Ready")
        self._status.setObjectName("islandStatus")
        bar_layout.addWidget(self._status, 1)

        self._close_btn = QPushButton("\u2715")
        self._close_btn.setFixedSize(22, 22)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #8E8E93; }"
            "QPushButton:hover { color: #FFFFFF; }"
        )
        self._close_btn.setToolTip("Collapse")
        self._close_btn.clicked.connect(self.collapse)
        self._close_btn.hide()
        bar_layout.addWidget(self._close_btn)

        card_layout.addWidget(bar)

        self._host = QVBoxLayout()
        self._host.setContentsMargins(0, 0, 0, 0)
        card_layout.addLayout(self._host)

        root.addWidget(self._card)

    def _ensure_panel(self):
        if self._panel is None:
            from app.ui.conversation_panel import ConversationPanel
            self._panel = ConversationPanel()
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
        except Exception:
            pass
        # If panel already created, bind signals
        try:
            if getattr(self, "_panel", None) is not None and hasattr(coord, "voice_state_changed"):
                try:
                    coord.voice_state_changed.connect(self._on_voice_state_changed)
                except Exception:
                    pass
        except Exception:
            pass

    def _confirm(self, tool_name: str, arguments: dict) -> str:
        """Approval handler — runs on the agent worker thread.

        Generates a unique approval_id, registers the record, and waits
        event-based for a decision via queued signal. Exactly one terminal
        transition is allowed: approved_once | denied | expired | cancelled | failed.
        Stale or late events are ignored.

        The GUI thread delivers the decision via _on_approval_decision,
        which sets the record's terminal state.
        """
        import uuid

        approval_id = self._generate_approval_id(tool_name, arguments)
        record = ApprovalRecord(approval_id, tool_name, arguments)
        self._register_approval(record)
        # Emit to GUI thread with approval_id
        self._approval_requested.emit(tool_name, arguments, approval_id)
        # Wait event-based (no busy-wait sleep)
        terminal = record.wait(timeout=10.0)
        # Clean up registry entry
        self._resolve_approval(approval_id, terminal)
        # Return the terminal state as the decision
        if terminal == _APPROVED:
            return "approved"
        elif terminal == _DENIED:
            return "denied"
        elif terminal == _EXPIRED:
            return "denied"
        else:
            return "denied"

    def _show_approval(self, tool_name: str, arguments: dict, approval_id: str) -> None:
        """GUI thread: surface the approval card, expanding so it is visible."""
        panel = self._ensure_panel()
        # Look up the record; if not found (stale), still show but mark expired
        record = self._approval_registry.get(approval_id)
        if record is None:
            # Stale approval — show but mark expired immediately
            record = ApprovalRecord(approval_id, tool_name, arguments)
            self._register_approval(record)
            record.expire()
            return
        # Update the preview with redacted arguments
        panel.request_approval(tool_name, arguments)
        # Ensure panel's sink routes to this specific record
        if record._decision_sink is None:
            record._decision_sink = lambda decision: self._on_approval_decision(record, decision)
        panel.set_approval(tool_name, self._preview_arguments(arguments))
        if self._state is not IslandState.EXPANDED:
            self.expand()

    def _on_approval_decision(self, record: ApprovalRecord, allow: bool) -> None:
        """Called from the panel: resolve this specific approval record."""
        if allow:
            record.approve()
        else:
            record.deny()
        # Hide the approval card after decision
        if self._panel is not None:
            self._panel.set_approval(None)

    def _deny_pending(self) -> None:
        """Resolve all pending approvals to deny before hiding/quitting."""
        for record in self._approval_registry.values():
            if record.state == _PENDING:
                record.deny()
        # Clear the registry
        self._approval_registry.clear()

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
            self._panel.input_field.setFocus()

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
        self._dot.setStyleSheet(f"color: {color};")
        if detail:
            self._status.setToolTip(detail)

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
