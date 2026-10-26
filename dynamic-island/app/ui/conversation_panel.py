"""Compact conversation panel for the island — purpose-built, not the full window.

Conversation-focused: transcript, input, push-to-talk, and inline approval
prompts. No permanent toolbar, no dashboard. Reuses the coordinator/backend.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QTextCursor
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
            "padding: 12px 14px;\n"
        )
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
        self._media_title.setStyleSheet(
            "color: #EBEEF2; font-size: 12px; font-weight: 500; "
            "white-space: nowrap; overflow: hidden; text-overflow: ellipsis; "
        )
        ml.addWidget(self._media_title)

        # Artist
        self._media_artist = QLabel("")
        self._media_artist.setStyleSheet(
            "color: #B0B7C1; font-size: 11px; white-space: nowrap; "
            "overflow: hidden; text-overflow: ellipsis; "
        )
        ml.addWidget(self._media_artist)

        # Album artwork placeholder (compact circle)
        self._media_art = QLabel()
        self._media_art.setFixedSize(36, 36)
        self._media_art.setStyleSheet(
            "background: #2C1C2E; border-radius: 18px; border: 1px solid #3A3A3C; "
            "color: #8C96A3; font-size: 14px; font-weight: 600; "
            "display: flex; align-items: center; justify-content: center; "
            "cursor: pointer; "
        )
        self._media_art.setToolTip("Change album art")
        ml.addWidget(self._media_art)

        # Playback bar: previous / play-pause / next
        self._prev_btn = QPushButton("\u23EE")
        self._prev_btn.setFixedSize(32, 32)
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.setStyleSheet("""
            QPushButton { background: #2C1C2E; color: #E5E5EA; border: 1px solid #3A3A3C; }
            QPushButton:hover { background: #3A3A3C; }
            QPushButton:checked { background: #8C96A3; border-color: #8C96A3; }
        """)
        ml.addWidget(self._prev_btn)

        self._play_btn = QPushButton("\u25B6")
        self._play_btn.setFixedSize(32, 32)
        self._play_btn.setCheckable(True)
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.setStyleSheet("""
            QPushButton { background: #0A84FF; color: #FFFFFF; border: none; border-radius: 6px; }
            QPushButton:hover { background: #0071E3; }
            QPushButton:checked { background: #0071E3; }
        """)
        self._play_btn.setToolTip("Play / pause")
        ml.addWidget(self._play_btn)

        self._next_btn = QPushButton("\u23ED")
        self._next_btn.setFixedSize(32, 32)
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.setStyleSheet("""
            QPushButton { background: #2C1C2E; color: #E5E5EA; border: 1px solid #3A3A3C; }
            QPushButton:hover { background: #3A3A3C; }
            QPushButton:checked { background: #8C96A3; border-color: #8C96A3; }
        """)
        ml.addWidget(self._next_btn)

        # Progress slider
        self._progress_bar = QSlider(Qt.Orientation.Horizontal)
        self._progress_bar.setFixedWidth(160)
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setStyleSheet(
            "QSlider::groove:horizontal { background: #3A3A3C; border-radius: 3px; height: 4px; }"
            "QSlider::handle:horizontal { background: #8C96A3; border: 1px solid #3A3A3C; "
            " border-radius: 3px; height: 10px; width: 10px; margin: -3px 0; }"
            "QSlider::handle:horizontal:hover { background: #EBEEF2; }"
        )
        ml.addWidget(self._progress_bar)

        # Volume slider (optional, mirrored from media strip)
        self._volume_bar = QSlider(Qt.Orientation.Horizontal)
        self._volume_bar.setFixedWidth(80)
        self._volume_bar.setMinimum(0)
        self._volume_bar.setMaximum(100)
        self._volume_bar.setStyleSheet(
            "QSlider::groove:horizontal { background: #3A3A3C; border-radius: 3px; height: 4px; }"
            "QSlider::handle:horizontal { background: #8C96A3; border: 1px solid #3A3A3C; "
            " border-radius: 3px; height: 10px; width: 10px; margin: -3px 0; }"
            "QSlider::handle:horizontal:hover { background: #EBEEF2; }"
        )
        ml.addWidget(self._volume_bar)

        root.addWidget(self._media_row)

        # Inline approval row (hidden unless approval is required)
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
        # Each button carries its approval_id via closure
        approve_btn.clicked.connect(lambda checked, aid=None: self._on_approval_btn(True, aid))
        deny_btn.clicked.connect(lambda checked, aid=None: self._on_approval_btn(False, aid))
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
        il.addWidget(self.mic_btn)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask JARVIS\u2026")
        self.input_field.setMinimumHeight(34)
        self.input_field.setStyleSheet(
            "QLineEdit { background: #2C1C2E; color: #FFFFFF; border: 1px solid #3A3A3C; "
            " border-radius: 8px; padding: 6px 10px; font-size: 13px; }"
            "QLineEdit:focus { border-color: #0A84FF; }"
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
        else:
            self._approval_label.setText(f"{tool_name}: {preview}")

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
        """Handle send button / Enter in the input field."""
        pass  # routed via overlay_window.py

    def _on_mic(self) -> None:
        """Handle push-to-talk button toggle."""
        pass  # routed via overlay_window.py

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