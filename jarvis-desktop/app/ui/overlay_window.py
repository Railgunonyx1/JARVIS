"""Dynamic Island for JARVIS Desktop.

A top-center always-on-top pill that morphs between three states:
  idle      — compact pill, near-invisible, shows status
  compact   — hover: widens to show live detail
  expanded  — click: full chat card with spring animation

Reuses ChatWindow/AppCoordinator for the agent stack; this module owns only
the island chrome, state machine, and geometry.
"""

from __future__ import annotations

import logging
from enum import Enum

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    Qt,
)
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger("jarvis.desktop.island")

_TOP_MARGIN = 8
_IDLE_W, _IDLE_H = 180, 36
_COMPACT_W, _COMPACT_H = 320, 44
_EXPANDED_W, _EXPANDED_H = 460, 600
_RADIUS = 20


class IslandState(Enum):
    IDLE = "idle"
    COMPACT = "compact"
    EXPANDED = "expanded"


class IslandWindow(QWidget):
    """Top-center morphing island overlay."""

    def __init__(self) -> None:
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

        self._build()

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(260)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)

        self.resize(_IDLE_W, _IDLE_H)
        self._reposition()

    def _reposition(self) -> None:
        self.setGeometry(self._target_rect(self._state))

    # ── UI ───────────────────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
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

        bar = QWidget()
        bar.setFixedHeight(_IDLE_H)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(8)

        self._title = QLabel("JARVIS")
        self._title.setObjectName("islandTitle")
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
            from app.ui.chat_window import ChatWindow
            self._panel = ChatWindow()
            self._panel.settings_btn.hide()
            self._panel.status_label.hide()
            self._host.addWidget(self._panel)
            self._panel.start_backend()
        return self._panel

    # ── State machine ────────────────────────────────────────────
    def _target_rect(self, state: IslandState):
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else None
        if state is IslandState.IDLE:
            w, h = _IDLE_W, _IDLE_H
        elif state is IslandState.COMPACT:
            w, h = _COMPACT_W, _COMPACT_H
        else:
            w, h = _EXPANDED_W, _EXPANDED_H
        if geo is None:
            return self.geometry()
        x = geo.left() + (geo.width() - w) // 2
        y = geo.top() + _TOP_MARGIN
        return QRect(x, y, w, h)

    def _set_state(self, state: IslandState) -> None:
        if state is self._state:
            return
        self._state = state
        expanded = state is IslandState.EXPANDED
        self._close_btn.setVisible(expanded)
        if expanded:
            self._ensure_panel()
            self._dot.setStyleSheet("color: #30D158;")
        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(self._target_rect(state))
        self._anim.start()

    def expand(self) -> None:
        self._set_state(IslandState.EXPANDED)

    def collapse(self) -> None:
        self._set_state(IslandState.IDLE)

    def set_status(self, text: str, color: str = "#8E8E93") -> None:
        self._status.setText(text)
        self._dot.setStyleSheet(f"color: {color};")

    # ── Interaction ──────────────────────────────────────────────
    def enterEvent(self, event) -> None:
        if self._state is IslandState.IDLE:
            self._set_state(IslandState.COMPACT)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self._state is IslandState.COMPACT:
            self._set_state(IslandState.IDLE)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._state is not IslandState.EXPANDED:
                self.expand()

    def closeEvent(self, event) -> None:
        if self._panel is not None:
            self._panel.close()
        event.accept()
