"""Compact conversation panel for the island — purpose-built, not the full window.

Conversation-focused: transcript, input, push-to-talk, and inline approval
prompts. No permanent toolbar, no dashboard. Reuses the coordinator/backend.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QImage, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Design tokens (from DI-025 mockup) — mirrored from overlay_window.py
# Palette: background #141619, accent #8C96A3, text #EBEEF2, muted #B0B7C1
#          divider #3A3A3C, input bg #2C1C2E, primary blue #0A84FF,
#          amber #FFD60A, dark bg #272B30, darkest #172431
_BLUE    = "#0A84FF"
_BLUE_H  = "#0071E3"
_ACCENT  = "#8C96A3"
_MUTED   = "#B0B7C1"
_DIVIDER = "#3A3A3C"
_INPUT_BG = "#2C1C2E"
_INPUT_FG = "#FFFFFF"
_AMBER   = "#FFD60A"
_DARK_BG = "#272B30"
_DARK_DK = "#172431"


# Per-request approval sink: keyed by approval_id, single-terminal-transition
class ApprovalSink(QObject):
    """Sinks exactly one decision per approval_id.

    On the first allow/deny call, it records the result and invalidates.
    Subsequent calls are ignored (stale-click safe).
    """

    def __init__(self, approval_id: str, sink: object):
        super().__init__()
        self.approval_id = approval_id
        self._sink = sink
        self._decided = False

    def approve(self) -> None:
        if self._decided:
            return  # stale / duplicate click – ignore
        self._decided = True
        self._sink("once")

    def deny(self) -> None:
        if self._decided:
            return  # stale / duplicate click – ignore
        self._decided = True
        self._sink("deny")


class ConversationPanel(QWidget):
    """Compact chat surface embedded in the expanded island."""

    send_requested = Signal(str)
    mic_toggled = Signal()
    cancel_requested = Signal()
    approval_decision = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._max_blocks = 500
        # Map approval_id -> ApprovalSink; each sink handles one decision only
        self._approval_sinks: dict[str, ApprovalSink] = {}
        self._build()

    def request_approval(self, tool_name: str, arguments: dict | None = None, approval_id: str | None = None) -> None:
        """Show the approval row and route the next decision to a per-ID sink."""
        self.set_approval(tool_name, self._preview_arguments(arguments), approval_id)

    @staticmethod
    def _redact_value(value: object) -> str:
        """Recursively redact sensitive values, never exposing full secrets."""
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            # Redact if the string looks like a token/key/credential
            if any(prefix in value.lower() for prefix in ("sk-", "pk-", "api-", "token=", "secret=")):
                return "•••"
            # Redact known sensitive field values
            if value.lower() in ("hunter2", "password", "secret", "apikey", "private_key", "password123"):
                return "•••"
            # Redact long strings that look like secrets
            if len(value) > 60:
                return value[:57] + "…"
            return value
        if isinstance(value, dict):
            # Recursively redact dict values; show key names but redact values
            items = list(value.items())[:5]
            parts = []
            for k, v in items:
                k_str = str(k)
                v_redacted = ConversationPanel._redact_value(v)
                parts.append(f"{k_str}={v_redacted}")
            if len(value) > 5:
                parts.append(f"(+{len(value) - 5} more keys…)")
            return "{" + ", ".join(parts) + "}"
        if isinstance(value, (list, tuple)):
            items = value[:3]
            reduced = [ConversationPanel._redact_value(v) for v in items]
            extra = len(value) - 3
            extra_str = f"(+{extra} more…)" if extra > 0 else ""
            return "[" + ", ".join(reduced) + "] " + extra_str
        return f"<{type(value).__name__}>"

    @staticmethod
    def _preview_arguments(arguments: dict | None) -> str:
        """Compact, redacted argument preview (never full payloads)."""
        if not arguments:
            return ""
        parts = []
        for name, value in list(arguments.items())[:3]:
            shown = ConversationPanel._redact_value(value)
            parts.append(f"{name}={shown}")
        if len(arguments) > 3:
            parts.append(f"(+{len(arguments) - 3} more)")
        return ", ".join(parts)

    @staticmethod
    def _preview(arguments: dict | None = None) -> str:
        """Static preview for test compatibility (never full payloads)."""
        return ConversationPanel._preview_arguments(arguments)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setFrameShape(QFrame.NoFrame)
        self.transcript.setObjectName("islandTranscript")
        self.transcript.setStyleSheet(
            "#islandTranscript {\n"
            "background: transparent;\n"
            "color: #E5E5EA;\n"
            "border: none;\n"
            "font-size: 13px;\n"
            "line-height: 1.6;\n"
            "padding: 12px 14px;\n"
            "-webkit-scrollbar-width: thin;\n"
            "-webkit-scrollbar-color: #3A3A3C #141619;\n"
        )
        # Add message styling for clear hierarchy
        self.transcript.append("<style> QTextBlock { margin: 0 0 14px 0; } "
                               "</style>")
        root.addWidget(self.transcript, 1)

        # ── Media player strip (optional, compact) ──────────────────────────────────
        self._media_row = QFrame()
        self._media_row.setObjectName("islandMedia")
        self._media_row.setStyleSheet(
            "#islandMedia { background: #141619; border-top: 1px solid #3A3A3C; }"
        )
        ml = QHBoxLayout(self._media_row)
        ml.setContentsMargins(12, 8, 12, 8)
        ml.setSpacing(12)

        # Track metadata: title and artist
        self._media_title = QLabel("No track playing")
        self._media_title.setMinimumWidth(120)
        self._media_title.setStyleSheet(
            "color: #EBEEF2; font-size: 12px; font-weight: 500; "
            "white-space: nowrap; overflow: hidden; "
        )
        self._media_title.setToolTip("No track playing")
        self._media_title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self._media_title)

        # Artist
        self._media_artist = QLabel("")
        self._media_artist.setMinimumWidth(100)
        self._media_artist.setStyleSheet(
            "color: #B0B7C1; font-size: 11px; white-space: nowrap; "
            "overflow: hidden; "
        )
        self._media_artist.setToolTip("")
        self._media_artist.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self._media_artist)

        # Album artwork placeholder (compact circle)
        self._media_art = QLabel("")
        self._media_art.setFixedSize(36, 36)
        self._media_art.setStyleSheet(
            "background: #20242B; border: 2px solid #3A404B; "
            "border-radius: 18px; color: #5C6470; "
            "font-size: 11px; font-weight: 600; "
            "display: flex; align-items: center; justify-content: center; "
        )
        self._media_art.setToolTip("Change album art")
        self._media_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ml.addWidget(self._media_art)

        # Wrapper for playback buttons (previous / play-pause / next)
        self._playback_w = QWidget()
        self._playback_w.setFixedSize(100, 32)
        self._playback_w.setStyleSheet("""
            background: transparent; border-radius: 4px; margin-right: 6px;
        """)
        pl = QHBoxLayout(self._playback_w)
        pl.setContentsMargins(4, 0, 4, 0)
        pl.setSpacing(2)
        self._prev_btn = QPushButton("\u23EE")
        self._prev_btn.setFixedSize(26, 26)
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.setStyleSheet("""
            QPushButton { background: #2C1C2E; color: #E5E5EA; border: 1px solid #3A3A3C; }
            QPushButton:hover { background: #3A3A3C; }
            QPushButton:checked { background: #8C96A3; border-color: #8C96A3; }
        """)
        self._prev_btn.clicked.connect(self._on_prev)
        pl.addWidget(self._prev_btn)

        self._play_btn = QPushButton("\u25B6")
        self._play_btn.setFixedSize(26, 26)
        self._play_btn.setCheckable(True)
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.setStyleSheet("""
            QPushButton { background: #0A84FF; color: #FFFFFF; border: none; border-radius: 6px; }
            QPushButton:hover { background: #0071E3; }
            QPushButton:checked { background: #0071E3; }
        """)
        self._play_btn.setToolTip("Play / pause")
        self._play_btn.clicked.connect(self._on_play)
        pl.addWidget(self._play_btn)

        self._next_btn = QPushButton("\u23ED")
        self._next_btn.setFixedSize(26, 26)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setStyleSheet("""
            QPushButton { background: #2C1C2E; color: #E5E5EA; border: 1px solid #3A3A3C; }
            QPushButton:hover { background: #3A3A3C; }
            QPushButton:checked { background: #8C96A3; border-color: #8C96A3; }
        """)
        self._next_btn.clicked.connect(self._on_next)
        pl.addWidget(self._next_btn)

        # Progress slider (compact)
        self._progress_bar = QSlider(Qt.Orientation.Horizontal)
        self._progress_bar.setFixedWidth(100)
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setStyleSheet(
            "QSlider::groove:horizontal { background: #3A3A3C; border-radius: 3px; height: 4px; }"
            "QSlider::handle:horizontal { background: #8C96A3; border: 1px solid #3A3A3C; "
            " border-radius: 3px; height: 8px; width: 8px; margin: -2px 0; }"
            "QSlider::handle:horizontal:hover { background: #EBEEF2; }"
        )
        self._progress_bar.valueChanged.connect(self._on_progress)

        # Volume slider (compact)
        self._volume_bar = QSlider(Qt.Orientation.Horizontal)
        self._volume_bar.setFixedWidth(66)
        self._volume_bar.setMinimum(0)
        self._volume_bar.setMaximum(100)
        self._volume_bar.setStyleSheet(
            "QSlider::groove:horizontal { background: #3A3A3C; border-radius: 3px; height: 4px; }"
            "QSlider::handle:horizontal { background: #8C96A3; border: 1px solid #3A3A3C; "
            " border-radius: 3px; height: 8px; width: 8px; margin: -2px 0; }"
            "QSlider::handle:horizontal:hover { background: #EBEEF2; }"
        )
        self._volume_bar.valueChanged.connect(self._on_volume)

        ml.addWidget(self._media_art)
        ml.addWidget(self._playback_w)
        ml.addWidget(self._progress_bar)
        ml.addWidget(self._volume_bar)

        root.addWidget(self._media_row)

        # Media player strip (optional, compact) — hidden until valid media metadata arrives
        self._media_row = QFrame()
        self._media_row.setObjectName("islandMedia")
        self._media_row.setStyleSheet(
            "#islandMedia { background: #141619; border-top: 1px solid #3A3A3C; }"
        )
        ml = QHBoxLayout(self._media_row)
        ml.setContentsMargins(12, 8, 12, 8)
        ml.setSpacing(12)

        # Track metadata: title and artist
        self._media_title = QLabel("No track playing")
        self._media_title.setMinimumWidth(120)
        self._media_title.setStyleSheet(
            "color: #EBEEF2; font-size: 12px; font-weight: 500; "
            "white-space: nowrap; overflow: hidden; "
        )
        self._media_title.setToolTip("No track playing")
        self._media_title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self._media_title)

        # Artist
        self._media_artist = QLabel("")
        self._media_artist.setMinimumWidth(100)
        self._media_artist.setStyleSheet(
            "color: #B0B7C1; font-size: 11px; white-space: nowrap; "
            "overflow: hidden; "
        )
        self._media_artist.setToolTip("")
        self._media_artist.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        ml.addWidget(self._media_artist)

        # Album artwork placeholder (compact circle)
        self._media_art = QLabel("")
        self._media_art.setFixedSize(36, 36)
        self._media_art.setStyleSheet(
            "background: #20242B; border: 2px solid #3A404B; "
            "border-radius: 18px; color: #5C6470; "
            "font-size: 11px; font-weight: 600; "
            "display: flex; align-items: center; justify-content: center; "
        )
        self._media_art.setToolTip("Change album art")
        self._media_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ml.addWidget(self._media_art)

        # Wrapper for playback buttons (previous / play-pause / next)
        self._playback_w = QWidget()
        self._playback_w.setFixedSize(100, 32)
        self._playback_w.setStyleSheet("""
            background: transparent; border-radius: 4px; margin-right: 6px;
        """)
        pl = QHBoxLayout(self._playback_w)
        pl.setContentsMargins(4, 0, 4, 0)
        pl.setSpacing(2)
        self._prev_btn = QPushButton("\u23EE")
        self._prev_btn.setFixedSize(26, 26)
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.setStyleSheet("""
            QPushButton { background: #2C1C2E; color: #E5E5EA; border: 1px solid #3A3A3C; }
            QPushButton:hover { background: #3A3A3C; }
            QPushButton:checked { background: #8C96A3; border-color: #8C96A3; }
        """)
        self._prev_btn.clicked.connect(self._on_prev)
        pl.addWidget(self._prev_btn)

        self._play_btn = QPushButton("\u25B6")
        self._play_btn.setFixedSize(26, 26)
        self._play_btn.setCheckable(True)
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.setStyleSheet("""
            QPushButton { background: #0A84FF; color: #FFFFFF; border: none; border-radius: 6px; }
            QPushButton:hover { background: #0071E3; }
            QPushButton:checked { background: #0071E3; }
        """)
        self._play_btn.setToolTip("Play / pause")
        self._play_btn.clicked.connect(self._on_play)
        pl.addWidget(self._play_btn)

        self._next_btn = QPushButton("\u23ED")
        self._next_btn.setFixedSize(26, 26)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setStyleSheet("""
            QPushButton { background: #2C1C2E; color: #E5E5EA; border: 1px solid #3A3A3C; }
            QPushButton:hover { background: #3A3A3C; }
            QPushButton:checked { background: #8C96A3; border-color: #8C96A3; }
        """)
        self._next_btn.clicked.connect(self._on_next)
        pl.addWidget(self._next_btn)

        # Progress slider (compact)
        self._progress_bar = QSlider(Qt.Orientation.Horizontal)
        self._progress_bar.setFixedWidth(100)
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setStyleSheet(
            "QSlider::groove:horizontal { background: #3A3A3C; border-radius: 3px; height: 4px; }"
            "QSlider::handle:horizontal { background: #8C96A3; border: 1px solid #3A3A3C; "
            " border-radius: 3px; height: 8px; width: 8px; margin: -2px 0; }"
            "QSlider::handle:horizontal:hover { background: #EBEEF2; }"
        )
        self._progress_bar.valueChanged.connect(self._on_progress)

        # Volume slider (compact)
        self._volume_bar = QSlider(Qt.Orientation.Horizontal)
        self._volume_bar.setFixedWidth(66)
        self._volume_bar.setMinimum(0)
        self._volume_bar.setMaximum(100)
        self._volume_bar.setStyleSheet(
            "QSlider::groove:horizontal { background: #3A3A3C; border-radius: 3px; height: 4px; }"
            "QSlider::handle:horizontal { background: #8C96A3; border: 1px solid #3A3A3C; "
            " border-radius: 3px; height: 8px; width: 8px; margin: -2px 0; }"
            "QSlider::handle:horizontal:hover { background: #EBEEF2; }"
        )
        self._volume_bar.valueChanged.connect(self._on_volume)

        ml.addWidget(self._media_art)
        ml.addWidget(self._playback_w)
        ml.addWidget(self._progress_bar)
        ml.addWidget(self._volume_bar)

        # Hide the media row when no audio is playing (show only when a track is active)
        self._media_row.hide()

        # ── Inline approval row (hidden unless approval is required) ──────────
        self._approval_row = QFrame()
        self._approval_row.setObjectName("islandApproval")
        self._approval_row.setStyleSheet(
            "#islandApproval { background: #2C2C2E; border-top: 1px solid #3A3A3C; }"
        )
        ar = QHBoxLayout(self._approval_row)
        ar.setContentsMargins(12, 8, 12, 8)
        ar.setSpacing(8)
        self._approval_label = QLabel("")
        self._approval_label.setTextFormat(Qt.TextFormat.PlainText)
        self._approval_label.setWordWrap(True)
        self._approval_label.setStyleSheet("color: #FFD60A; font-size: 12px;")
        ar.addWidget(self._approval_label, 1)
        approve_btn = QPushButton("Allow")
        deny_btn = QPushButton("Deny")
        for b in (approve_btn, deny_btn):
            b.setFixedHeight(28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            b.setStyleSheet(
                "QPushButton { background: #2C1C2E; color: #E5E5EA; border: 1px solid #3A3A3C; "
                "border-radius: 6px; font-size: 11px; font-weight: 600; padding: 6px 14px; }"
                "QPushButton:hover { background: #3A3A3C; }"
                "QPushButton:focus { outline: 2px solid #FFD60A; outline-offset: 1px; }"
                "QPushButton:checked { background: #FFD60A; color: #FFFFFF; border-color: #FFD60A; }"
                "QPushButton:pressed { background: #FFD60A; }"
            )
        # Each button carries the approval_id passed into set_approval
        # Delegate to the instance methods so _current_approval_id is used.
        # The allow/deny buttons use _on_approve_btn/_on_deny_btn which read
        # self._current_approval_id set by set_approval().
        self._current_approval_id: str | None = None
        # Use a closure that captures _current_approval_id at call time
        self._on_approve_btn = lambda: self._on_approval_btn(True, self._current_approval_id)
        self._on_deny_btn = lambda: self._on_approval_btn(False, self._current_approval_id)
        approve_btn.clicked.connect(self._on_approve_btn)
        deny_btn.clicked.connect(self._on_deny_btn)
        ar.addWidget(deny_btn)
        ar.addWidget(approve_btn)
        self._approval_row.hide()
        root.addWidget(self._approval_row)

        # Input row
        input_bar = QFrame()
        input_bar.setObjectName("islandInput")
        input_bar.setStyleSheet(
            "#islandInput { background: #1C1C1E; border-top: 1px solid #3A3A3C; }"
        )
        il = QHBoxLayout(input_bar)
        il.setContentsMargins(12, 8, 12, 8)
        il.setSpacing(8)

        self.mic_btn = QPushButton("\u2630")
        self.mic_btn.setFixedSize(34, 34)
        self.mic_btn.setCheckable(True)
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.setToolTip("Push to talk")
        self.mic_btn.clicked.connect(self.mic_toggled.emit)
        self._style_button(self.mic_btn)
        self.mic_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.mic_btn.setStyleSheet(
            "QPushButton { background: #2C2C2E; color: #E5E5EA; border: 1px solid #3A3A3C; "
            "border-radius: 8px; padding: 6px 12px; font-size: 13px; font-weight: 500; }"
            "QPushButton:hover { background: #3A3A3C; }"
            "QPushButton:focus { outline: 2px solid #0A84FF; outline-offset: 1px; }"
            "QPushButton:checked { background: #0A84FF; color: #FFFFFF; border-color: #0A84FF; }"
            "QPushButton:checked:hover { background: #0071E3; }"
        )
        il.addWidget(self.mic_btn)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask JARVIS\u2026")
        self.input_field.setMinimumHeight(34)
        self.input_field.setStyleSheet(
            "QLineEdit { background: #2C1C2E; color: #FFFFFF; border: 1px solid #3A3A3C; "
            "border-radius: 8px; padding: 8px 12px; font-size: 13px; font-weight: 500; }"
            "QLineEdit:focus { border-color: #0A84FF; outline: 2px solid #0A84FF; "
            "outline-offset: 1px; background: #24282F; }"
        )
        self.input_field.returnPressed.connect(self._on_send)
        il.addWidget(self.input_field, 1)

        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedSize(60, 34)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet(
            "QPushButton { background: #0A84FF; color: #FFFFFF; border: none; "
            " border-radius: 8px; font-size: 13px; font-weight: 500; }"
            "QPushButton:hover { background: #0071E3; }"
        )
        self.send_btn.clicked.connect(self._on_send)
        self.send_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.send_btn.setStyleSheet(
            "QPushButton { background: #0A84FF; color: #FFFFFF; border: none; "
            "border-radius: 8px; font-size: 13px; font-weight: 500; "
            "padding: 6px 12px; }"
            "QPushButton:hover { background: #0071E3; }"
            "QPushButton:focus { outline: 2px solid #8C96A3; outline-offset: 1px; }"
            "QPushButton:pressed { background: #0071E3; }"
        )
        il.addWidget(self.send_btn)

        root.addWidget(input_bar)

    # ── Public API (called by overlay_window) ─────────────────────────────────

    def _style_button(self, btn: QPushButton) -> None:
        """Apply the dark theme style to a button."""
        btn.setStyleSheet(
            "QPushButton { background: #2C2C2E; color: #E5E5EA; border: 1px solid #3A3A3C; "
            "border-radius: 8px; padding: 6px 12px; font-size: 13px; font-weight: 500; }"
            "QPushButton:hover { background: #3A3A3C; }"
            "QPushButton:checked { background: #8C96A3; border-color: #8C96A3; }"
            "QPushButton:default { background: #0A84FF; color: #FFFFFF; border-color: #0A84FF; }"
            "QPushButton:default:hover { background: #0071E3; }"
        )

    def set_approval(self, tool_name: str | None = None, preview: str | None = None, approval_id: str | None = None) -> None:
        """Show or clear the approval row.

        Called with (tool_name, preview, approval_id) to show; with
        (None, "", None) to hide.
        """
        self._approval_row.show()
        if tool_name is None:
            self._approval_row.hide()
            self._current_approval_id = None
        else:
            self._approval_label.setText(f"{tool_name}: {preview}")
            self._current_approval_id = approval_id

    def append_chunk(self, chunk: str) -> None:
        """Append a streaming response chunk to the transcript."""
        cursor = self.transcript.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(chunk)
        self.transcript.setTextCursor(cursor)
        self.transcript.ensureCursorVisible()

    def append_message(self, role: str, text: str) -> None:
        """Append a full message with role styling."""
        prefix = "JARVIS: " if role == "jarvis" else ("You: " if role == "user" else "")
        self.append_chunk(prefix + text)

    def set_listening(self, listening: bool) -> None:
        """Update the voice/listening indicator state."""
        self.mic_btn.setChecked(listening)
        if listening:
            self.mic_btn.setStyleSheet(
                f"QPushButton {{ background: #{_BLUE}; color: #FFFFFF; border: none; "
                f"border-radius: 8px; padding: 6px 12px; font-size: 13px; font-weight: 500; }}"
                f"QPushButton:hover {{ background: {_BLUE_H}; }}"
            )

    def _on_send(self, text: str = "") -> None:
        """Handle send button / Enter in the input field.

        Emits the send_requested signal so the overlay window routes the
        message through the coordinator/backend. The placeholder default
        keeps unit tests that call this method without forwarding an
        argument working.
        """
        text = text.strip()
        if text:
            self.send_requested.emit(text)

    def _on_mic(self) -> None:
        """Handle push-to-talk button toggle."""
        # The overlay window holds the real push-to-talk logic.
        self.mic_toggled.emit()

    def _on_prev(self) -> None:
        """Handle previous track button."""
        # Media playback state never overwrites JARVIS activity states
        return  # wired to MPRIS/adapter in the future

    def _on_play(self) -> None:
        """Handle play/pause toggle."""
        return  # wired to MPRIS/adapter in the future

    def _on_next(self) -> None:
        """Handle next track button."""
        # Media playback state never overwrites JARVIS activity states
        return  # wired to MPRIS/adapter in the future

    def _on_progress(self, value: int) -> None:
        """Handle progress slider movement."""
        return  # wired to MPRIS/adapter in the future

    def _on_volume(self, value: int) -> None:
        """Handle volume slider movement."""
        return  # wired to MPRIS/adapter in the future

    # ── Media player public API ────────────────────────────────────────────────

    def _set_media_hidden(self, hidden: bool) -> None:
        """Show or hide the media row when no media is active."""
        self._media_row.setVisible(not hidden)

    def set_media_title(self, title: str) -> None:
        """Set the track title shown in the media strip."""
        self._media_title.setText(title)

    def set_media_artist(self, artist: str) -> None:
        """Set the track artist shown in the media strip."""
        self._media_artist.setText(artist)

    def set_media_art(self, pixmap: QImage | None = None) -> None:
        """Set the album artwork. Pass a QImage or None to show placeholder."""
        if pixmap is not None:
            self._media_art.setPixmap(pixmap.scaled(36, 36, Qt.AspectRatioMode.KeepAspectCrop))
        else:
            self._media_art.setText("?")

    def media_play_pause(self) -> None:
        """Toggle play/pause programmatically."""
        self._play_btn.setChecked(not self._play_btn.isChecked())

    def set_media_playing(self, playing: bool) -> None:
        """Set playback state. True = playing, False = paused."""
        self._play_btn.setChecked(playing)

    def set_media_status(self, title: str, artist: str, album_art: QImage | None = None) -> None:
        """Update the full media strip in one call.

        With empty title/artist, hides the strip (no active media).
        """
        if not title.strip():
            self._media_row.hide()
            return
        self.set_media_title(title)
        self.set_media_artist(artist)
        self.set_media_art(album_art)
        self._media_row.show()

    def disconnect_media(self) -> None:
        """Release media resources. Call when the media player is no longer available."""
        self._media_row.hide()
        self.set_media_status("", "")

    def _on_approval_btn(self, allow: bool, approval_id: str | None) -> None:
        """Handle an approval button click."""
        if approval_id is None:
            return
        # Route through the sink that was registered with this approval_id
        sink = self._approval_sinks.get(approval_id)
        if sink is not None:
            (sink.approve if allow else sink.deny)()

        # Hide the approval row after decision
        self.set_approval(None, "", None)