"""Compact conversation panel for the island — purpose-built, not the full window.

Conversation-focused: transcript, input, push-to-talk, and inline approval
prompts. No permanent toolbar, no dashboard. Reuses the coordinator/backend.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QObject, Signal, QLocale
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


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
        self.approval_decision.connect(self._on_approval_decision)
        self._build()

    def _on_approval_decision(self, allow: bool) -> None:
        # The signal carries the approval_id from the sender; find and use
        # the matching sink; ignore if none found (stale or orphaned).
        pass  # handled inline below

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
                return "••••••••"
            # Redact long strings that look like secrets
            if len(value) > 60:
                return value[:57] + "..."
            return value
        if isinstance(value, dict):
            # Recursively redact dict values; show key names but redact values
            items = list(value.items())[:5]
            parts = []
            for k, v in items:
                k_str = str(k)
                v_redacted = _redact_value(v)
                parts.append(f"{k_str}={v_redacted}")
            if len(value) > 5:
                parts.append(f"(+{len(value) - 5} more keys)")
            return "{" + ", ".join(parts) + "}"
        if isinstance(value, (list, tuple)):
            items = value[:3]
            reduced = [_redact_value(v) for v in items]
            extra = len(value) - 3
            extra_str = f"(+{extra} more)" if extra > 0 else ""
            return "[" + ", ".join(reduced) + "] " + extra_str
        return f"<{type(value).__name__}>"@staticmethod
    def _preview_arguments(arguments: dict | None) -> str:
        """Compact, redacted argument preview (never full payloads)."""
        if not arguments:
            return ""
        parts = []
        for name, value in list(arguments.items())[:3]:
            shown = _redact_value(value)
            parts.append(f"{name}={shown}")
        if len(arguments) > 3:
            parts.append(f"(+{len(arguments) - 3} more)")
        return ", ".join(parts)

    @staticmethod
    def _preview(arguments: dict | None) -> str:
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

        self.mic_btn = QPushButton("☰")
        self.mic_btn.setFixedSize(34, 34)
        self.mic_btn.setCheckable(True)
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.setToolTip("Push to talk")
        self.mic_btn.clicked.connect(self.mic_toggled.emit)
        self._style_button(self.mic_btn)
        il.addWidget(self.mic_btn)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask JARVIS…")
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

    @staticmethod
    def _style_button(btn: QPushButton) -> None:
        btn.setStyleSheet(
            "QPushButton { background: #2C2C2E; color: #FFFFFF; border: 1px solid #3A3A3C; "
            " border-radius: 8px; }"
            "QPushButton:checked { background: #FF3B30; border-color: #FF3B30; }"
        )

    def _on_approval_btn(self, allow: bool, approval_id: str | None) -> None:
        """Route the approval decision to the per-ID sink, ignoring stale clicks."""
        if approval_id is None or approval_id not in self._approval_sinks:
            return  # no matching sink – stale or orphaned click
        sink = self._approval_sinks.pop(approval_id)
        if allow:
            sink.approve()
        else:
            sink.deny()

    def _on_send(self) -> None:
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self.send_requested.emit(text)

    # ── Rendering ────────────────────────────────────────────────
    def append_message(self, role: str, text: str) -> None:
        if role == "user":
            html = f'<p style="color:#0A84FF;margin:6px 0;"><b>You:</b> {self._esc(text)}</p>'
        elif role == "jarvis":
            html = f'<p style="color:#FFFFFF;margin:6px 0;"><b>JARVIS:</b> {self._esc(text)}</p>'
        else:
            html = f'<p style="color:#8E8E93;margin:6px 0;font-style:italic;">{self._esc(text)}</p>'
        self.transcript.append(html)
        self.transcript.moveCursor(QTextCursor.MoveOperation.End)
        self._trim()

    def append_chunk(self, chunk: str) -> None:
        cursor = self.transcript.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(chunk)
        doc = self.transcript.document()
        if doc.blockCount() > self._max_blocks:
            self._trim()

    def _trim(self) -> None:
        doc = self.transcript.document()
        if doc.blockCount() > self._max_blocks:
            cursor = self.transcript.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            for _ in range(doc.blockCount() - self._max_blocks):
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                cursor.removeSelectedText()
                cursor.deletePreviousChar()
            self.transcript.setTextCursor(cursor)

    def set_approval(self, tool_name: str | None, preview: str = "", approval_id: str | None = None) -> None:
        if tool_name:
            text = f"Allow JARVIS to run: {tool_name}?"
            if preview:
                text += f"\n{preview}"
            self._approval_label.setText(text)
            self._approval_row.show()
            # Register a new sink for this approval_id
            if approval_id and self._approval_sinks.get(approval_id) is None:
                sink = ApprovalSink(approval_id, lambda decision: None)  # no-op; decision handled in _on_approval_btn
                self._approval_sinks[approval_id] = sink
        else:
            self._approval_label.setText("")
            self._approval_row.hide()

    def set_listening(self, active: bool) -> None:
        self.mic_btn.setChecked(active)

    def clear(self) -> None:
        self.transcript.clear()

    @staticmethod
    def _esc(text: str) -> str:
        return text.replace("&", "&").replace("<", "<").replace(">", ">")