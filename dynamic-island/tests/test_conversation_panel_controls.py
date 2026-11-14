"""Conversation-panel input and cancellation control tests."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app.ui.conversation_panel import ConversationPanel


def test_enter_sends_typed_message_exactly_once(qtbot):
    panel = ConversationPanel()
    qtbot.addWidget(panel)
    sent = []
    panel.send_requested.connect(sent.append)

    panel.input_field.setText("hello from Enter")
    panel.input_field.setFocus()
    QTest.keyClick(panel.input_field, Qt.Key.Key_Return)

    qtbot.waitUntil(lambda: len(sent) == 1, timeout=1000)
    assert sent == ["hello from Enter"]
    assert panel.input_field.text() == ""


def test_send_button_reads_input_field(qtbot):
    panel = ConversationPanel()
    qtbot.addWidget(panel)
    sent = []
    panel.send_requested.connect(sent.append)

    panel.input_field.setText("hello from button")
    QTest.mouseClick(panel.send_btn, Qt.MouseButton.LeftButton)

    assert sent == ["hello from button"]
    assert panel.input_field.text() == ""


def test_running_request_turns_send_button_into_cancel(qtbot):
    panel = ConversationPanel()
    qtbot.addWidget(panel)
    cancelled = []
    panel.cancel_requested.connect(lambda: cancelled.append(True))

    panel.set_request_running(True)

    assert panel._request_running is True
    assert panel.input_field.isEnabled() is False
    assert panel.mic_btn.isEnabled() is False
    assert panel.send_btn.toolTip() == "Stop response"

    QTest.mouseClick(panel.send_btn, Qt.MouseButton.LeftButton)
    assert cancelled == [True]

    panel.set_request_cancelling()
    assert panel.send_btn.isEnabled() is False

    panel.set_request_running(False)
    assert panel._request_running is False
    assert panel.input_field.isEnabled() is True
    assert panel.mic_btn.isEnabled() is True
    assert panel.send_btn.isEnabled() is True
    assert panel.send_btn.toolTip() == "Send message (Enter)"
