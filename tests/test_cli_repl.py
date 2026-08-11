"""Tests for the Rich REPL gap-close: command history (persistent + sensitive
filter), the msvcrt InputReader (editing, recall, Ctrl+C/Z), Markdown
rendering, the status-clock, and the /audit read-out.

Headless: InputReader is driven with injected key sequences; history/audit use
tmp_path; no LLM, no daemon.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from cli.history import MAX_ENTRIES, HistoryStore
from cli.input import Buffer, InputReader
from cli.renderer import render_markdown

# ── HistoryStore ────────────────────────────────────────────────────────────


def test_history_add_skips_empty_and_dedups(tmp_path):
    store = HistoryStore(path=tmp_path / "history")
    store.add("")
    store.add("   ")
    store.add("hello")
    store.add("hello")
    store.add("world")
    assert store.to_list() == ["hello", "world"]


def test_history_sensitive_filter(tmp_path):
    store = HistoryStore(path=tmp_path / "history")
    store.add("set api_key=sk-abc123")
    store.add("export GITHUB_TOKEN=ghp_xxx")
    store.add("password = hunter2")
    store.add("normal command")
    assert store.to_list() == ["normal command"]


def test_history_caps_at_limit(tmp_path):
    store = HistoryStore(path=tmp_path / "history")
    for i in range(MAX_ENTRIES + 50):
        store.add(f"cmd {i}")
    assert len(store) == MAX_ENTRIES
    assert store[0] == "cmd 50"
    assert store[-1] == f"cmd {MAX_ENTRIES + 49}"


def test_history_persists_roundtrip(tmp_path):
    path = tmp_path / "history"
    store = HistoryStore(path=path)
    store.add("first")
    store.add("second")
    store.save()
    reloaded = HistoryStore(path=path)
    assert reloaded.to_list() == ["first", "second"]


def test_history_corrupt_file_degrades_cleanly(tmp_path):
    path = tmp_path / "history"
    path.write_bytes(b"\xff\xfe corrupted \x00\x01")
    store = HistoryStore(path=path)
    assert store.to_list() == []


# ── InputReader / Buffer ────────────────────────────────────────────────────


def test_buffer_editing():
    b = Buffer("hello")
    b.cursor_home()
    b.insert("x")
    assert b.text == "xhello" and b.cursor == 1
    b.delete_right()
    assert b.text == "hello" and b.cursor == 1
    b.cursor_end()
    b.insert("!")
    assert b.text == "hello!" and b.cursor == 6
    b.cursor_left()
    b.delete_left()
    assert b.text == "hello" and b.cursor == 5


def _reader_with(keys, write=None):
    it = iter(keys)
    reader = InputReader(
        write=write or (lambda s: None),
        key_source=lambda: next(it),
    )
    return reader


def test_read_line_typing():
    reader = _reader_with(list("hi") + ["\r"])
    assert reader.read_line() == "hi"


def test_read_line_backspace_and_delete():
    reader = _reader_with(list("abcd") + ["\xe0K", "\xe0K", "\x00S", "\x08", "\r"])
    # type abcd → left,left → Delete removes 'c' → left, Backspace removes 'b' → "ad"
    assert reader.read_line() == "ad"


def test_read_line_cursor_movement():
    keys = list("abcd")
    keys += ["\xe0K", "\xe0K", "\x00G"]  # left, left, Home
    keys += ["\x00O"]  # End
    keys += ["\r"]
    reader = _reader_with(keys)
    assert reader.read_line() == "abcd"


def test_read_line_history_recall():
    reader = _reader_with(
        ["\xe0H", "\r", "\xe0H", "\xe0H", "\r"],  # up, enter, up, up, enter
    )
    reader.set_history(["first", "second"])
    assert reader.read_line() == "second"
    assert reader.read_line() == "first"


def test_read_line_history_edits_are_new_draft():
    reader = _reader_with(["\xe0H", "\x00G", "x", "\r"])
    reader.set_history(["alpha"])
    # up → "alpha", Home, insert "x" → "xalpha"
    assert reader.read_line() == "xalpha"


def test_read_line_ctrl_c_raises_keyboardinterrupt():
    reader = _reader_with(["\x03"])
    with pytest.raises(KeyboardInterrupt):
        reader.read_line()


def test_read_line_ctrl_z_raises_eof():
    reader = _reader_with(["\x1a"])
    with pytest.raises(EOFError):
        reader.read_line()


# ── renderer ────────────────────────────────────────────────────────────────


def test_render_markdown_returns_markdown_renderable():
    from rich.markdown import Markdown

    item = render_markdown("```python\nx = 1\n```")
    assert isinstance(item, Markdown)


def test_render_markdown_plain_stays_plain():
    from rich.text import Text

    item = render_markdown("just a plain sentence")
    assert isinstance(item, Text)


def test_render_markdown_garbage_does_not_crash():
    from rich.markdown import Markdown
    from rich.text import Text

    assert isinstance(render_markdown(""), Text)
    assert isinstance(render_markdown("# " * 50 + "x" * 200), (Markdown, Text))


# ── status clock ────────────────────────────────────────────────────────────


def test_status_bar_has_clock():
    from cli.cockpit import render_status_bar

    loop = types.SimpleNamespace(
        permissions=types.SimpleNamespace(mode="agent"),
        router=types.SimpleNamespace(_last_provider="ollama", _last_model="qwen3"),
        registry=types.SimpleNamespace(list=lambda: [1, 2, 3]),
        mem=types.SimpleNamespace(get_stats=lambda: {"decisions": 1, "knowledge": 0}),
        context_manager=types.SimpleNamespace(last_report=None),
    )
    bar = str(render_status_bar(loop))
    assert "time=" in bar


def test_status_bar_dict_has_clock(capsys):
    from rich.text import Text

    from cli.main import _render_status_bar_dict

    bar = _render_status_bar_dict({"mode": "agent", "tools": 4})
    assert isinstance(bar, Text)
    assert "time=" in str(bar)


# ── /audit read-out ─────────────────────────────────────────────────────────


def test_cmd_audit_stats_and_recent(monkeypatch, tmp_path, capsys):
    import security.audit as audit_mod

    log = audit_mod.AuditLog(db_path=tmp_path / "audit.db")
    log.log_immediate(
        audit_mod.AuditEntry(
            action="tool_call",
            tool="filesystem.write",
            trace_id="trace_abc",
            allowed=True,
            success=True,
        )
    )
    log.log_immediate(
        audit_mod.AuditEntry(
            action="tool_call",
            tool="bash.exec",
            trace_id="trace_abc",
            allowed=False,
            success=False,
        )
    )
    monkeypatch.setattr(audit_mod, "_audit_log", log)

    from cli.main import _cmd_audit

    _cmd_audit("/audit")
    out = capsys.readouterr().out
    assert "2 actions" in out
    assert "1 denied" in out
    assert "1 failed" in out
    assert "filesystem.write" in out

    _cmd_audit("/audit trace trace_abc")
    out = capsys.readouterr().out
    assert "filesystem.write" in out
    assert "DENIED" in out

    log.close()
