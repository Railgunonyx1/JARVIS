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


class IslandWindow(QWidget):
    """Top-center morphing island overlay."""

    _approval_requested = Signal(str, object)

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
        self._approval_result: list[str] | None = None
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
            self._host.addWidget(self._panel)
        return self._panel

    def _start_backend(self) -> None:
        if self._controller is None or self._controller.coordinator is not None:
            return
        from app.integration.coordinator import AppCoordinator
        from app.settings import load

        settings = load()
        coord = AppCoordinator(mode="agent", confirmation_handler=self._confirm)
        if settings.get("voice_enabled", True):
            coord.set_voice_enabled(True)
        if settings.get("model"):
            coord.set_model(settings["model"])
        coord.start()
        self._controller.attach(coord)

    def _confirm(self, tool_name: str, arguments: dict) -> str:
        """Approval handler — runs on the agent worker thread.

        The request is marshalled to the GUI thread with a queued signal: a
        Python callable is not a valid QMetaObject slot. There is no silent
        timeout — the call blocks until the operator decides, or until the
        island is hidden/quit (which denies).
        """
        import time

        result: list[str] = []
        self._approval_result = result
        self._approval_requested.emit(tool_name, arguments)
        while not result:
            if self._quitting:
                return "deny"
            time.sleep(0.02)
        return result[0]

    def _show_approval(self, tool_name: str, arguments: dict) -> None:
        """GUI thread: surface the approval card, expanding so it is visible."""
        if self._approval_result is None:
            return
        panel = self._ensure_panel()
        panel._decision_sink = self._approval_result
        panel.request_approval(tool_name, arguments)
        if self._state is not IslandState.EXPANDED:
            self.expand()

    def _deny_pending(self) -> None:
        """Resolve an unanswered approval to deny before hiding/quitting."""
        result, self._approval_result = self._approval_result, None
        if result is not None and not result:
            result.append("deny")
        if self._panel is not None:
            self._panel.set_approval(None)

    def _on_send(self, text: str) -> None:
        if self._controller and self._controller.coordinator is not None:
            self._controller.coordinator.send_message(text)

    def _on_mic(self) -> None:
        if self._controller and self._controller.coordinator is not None:
            self._controller.coordinator.toggle_voice()

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
