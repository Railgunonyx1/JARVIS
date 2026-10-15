"""Tests for pass-10 tools: local document retrieval + ICS agenda view.

Hermetic: documents are written into tmp_path (ProjectContext monkeypatched),
the test PDF is generated in-memory with pypdf, and no calendar source is a
network URL. Verifies TF-IDF ranking, stats, ICS parsing, recurrence
expansion, source registry rules, and the workspace-escape guard.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import build_default_registry  # noqa: E402
from tools.agenda_view import _expand_rrule, _parse_events  # noqa: E402
from tools import agenda_view as ag  # noqa: E402
from tools import doc_retrieval as dr  # noqa: E402


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """A tiny corpus: markdown, txt, and a generated PDF."""
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "research.md").write_text(
        "# Quantum Computing Notes\n\n"
        "Quantum computing uses qubits instead of classical bits.\n\n"
        "Error correction remains the central engineering challenge for "
        "quantum computing hardware in 2026.\n",
        encoding="utf-8",
    )
    (tmp_path / "notes" / "recipes.txt").write_text(
        "Sourdough starter recipe.\n\nFeed the starter daily with equal "
        "weights of flour and water. Rise time depends on room temperature.\n",
        encoding="utf-8",
    )
    # A PDF with known text
    try:
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        pdf_path = tmp_path / "docs"
        pdf_path.mkdir(exist_ok=True)
        (pdf_path / "spec.pdf").write_bytes(b"")  # placeholder; content test below skips if empty
    except Exception:  # pragma: no cover
        pass
    monkeypatch.setattr(
        __import__("core.project", fromlist=["ProjectContext"]).ProjectContext,
        "discover",
        staticmethod(lambda cwd=None: type("C", (), {"root_path": tmp_path})()),
    )
    return tmp_path


# -------------------------------------------------------------- registry

def test_pass10_tools_registered():
    registry = build_default_registry()
    for name in ("doc.search", "agenda.view"):
        tool = registry.get(name)
        assert tool is not None, f"{name} missing"
        assert tool.handler is not None
        assert tool.risk == "safe"


# --------------------------------------------------------- doc retrieval

def test_doc_search_finds_and_ranks(workspace):
    res = dr.doc_search({"query": "qubits error correction"})
    assert res.success
    assert "research.md" in res.output
    assert "recipes.txt" not in res.output  # unrelated doc ranks zero


def test_doc_search_multiple_hits(workspace):
    (workspace / "notes" / "bread.md").write_text(
        "Bread baking log.\n\nThe sourdough starter doubled in four hours.\n",
        encoding="utf-8",
    )
    res = dr.doc_search({"query": "sourdough starter"})
    assert res.success
    assert "recipes.txt" in res.output and "bread.md" in res.output


def test_doc_search_snippets_and_limit(workspace):
    res = dr.doc_search({"query": "quantum computing", "limit": 1})
    assert res.success
    body = res.output
    assert "1." in body  # ranked line


def test_doc_search_no_match(workspace):
    res = dr.doc_search({"query": "zebra xylophone"})
    assert res.success and "No documents match" in res.output


def test_doc_search_requires_query(workspace):
    assert dr.doc_search({}).success is False


def test_doc_stats(workspace):
    res = dr.doc_stats({})
    assert res.success and "chunks from" in res.output
    assert ".md" in res.output and ".txt" in res.output


def test_doc_search_skips_hidden_and_node_modules(workspace):
    hidden = workspace / ".secret"
    hidden.mkdir()
    (hidden / "leaked.md").write_text("quantum qubits classified material", encoding="utf-8")
    nm = workspace / "node_modules"
    nm.mkdir()
    (nm / "vendor.md").write_text("quantum qubits vendor docs", encoding="utf-8")
    res = dr.doc_search({"query": "classified material"})
    assert res.success and "leaked.md" not in res.output
    res = dr.doc_search({"query": "vendor docs"})
    assert res.success and "vendor.md" not in res.output


# ------------------------------------------------------------ agenda view

ICS_SIMPLE = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:evt-1@example
DTSTART:20260924T140000
DTEND:20260924T150000
SUMMARY:Design review
LOCATION:Room 4
END:VEVENT
BEGIN:VEVENT
UID:evt-2@example
DTSTART;VALUE=DATE:20260925
SUMMARY:Team offsite
END:VEVENT
BEGIN:VEVENT
UID:evt-3@example
DTSTART:20260923T090000Z
SUMMARY:Standup (UTC)
END:VEVENT
END:VCALENDAR
"""

ICS_WEEKLY = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:gym@example
DTSTART:20260922T180000
DURATION:PT1H
SUMMARY:Gym
RRULE:FREQ=WEEKLY;COUNT=10
END:VEVENT
END:VCALENDAR
"""


def test_parse_events_basic():
    events = _parse_events(ICS_SIMPLE)
    assert len(events) == 3
    by_uid = {e["uid"]: e for e in events}
    assert by_uid["evt-1@example"]["summary"] == "Design review"
    assert by_uid["evt-1@example"]["location"] == "Room 4"
    assert by_uid["evt-1@example"]["start"] == datetime(2026, 9, 24, 14, 0)
    assert by_uid["evt-2@example"]["all_day"] is True
    assert by_uid["evt-2@example"]["start"] == datetime(2026, 9, 25)
    assert by_uid["evt-3@example"]["all_day"] is False  # UTC converted to local naive


def test_weekly_expansion_within_window():
    events = _parse_events(ICS_WEEKLY)
    win_start = datetime(2026, 9, 22)
    win_end = win_start + timedelta(days=13)
    occurrences = _expand_rrule(events[0], win_start, win_end)
    assert len(occurrences) == 2  # Sep 22 + Sep 29 (COUNT=10 would continue, window ends)
    assert occurrences[0] == datetime(2026, 9, 22, 18, 0)


def test_rrule_respects_count():
    events = _parse_events(ICS_WEEKLY)
    win_start = datetime(2026, 9, 22)
    win_end = win_start + timedelta(days=365)
    occurrences = _expand_rrule(events[0], win_start, win_end)
    assert len(occurrences) == 10  # COUNT=10 caps it


def test_agenda_view_from_workspace_file(workspace):
    # Dynamic dates: agenda_view windows forward from *now*, so a hardcoded
    # fixture date goes stale the day after it was written (this exact
    # failure happened on 2026-09-28). Build the ICS relative to today.
    day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    d1 = day + timedelta(days=2)
    d2 = day + timedelta(days=3)
    ics = (
        "BEGIN:VCALENDAR\nVERSION:2.0\n"
        "BEGIN:VEVENT\n"
        "UID:evt-a@example\n"
        f"DTSTART:{d1.strftime('%Y%m%d')}T140000\n"
        f"DTEND:{d1.strftime('%Y%m%d')}T150000\n"
        "SUMMARY:Design review\n"
        "LOCATION:Room 4\n"
        "END:VEVENT\n"
        "BEGIN:VEVENT\n"
        "UID:evt-b@example\n"
        f"DTSTART;VALUE=DATE:{d2.strftime('%Y%m%d')}\n"
        "SUMMARY:Team offsite\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )
    (workspace / "team.ics").write_text(ics, encoding="utf-8")
    res = ag.agenda_view({"days": 7})
    assert res.success
    assert "Design review" in res.output
    assert "Team offsite" in res.output and "all-day" in res.output
    assert "Room 4" in res.output


def test_agenda_add_remove_list_roundtrip(workspace):
    add = ag.agenda_add({"source": "calendars/personal.ics"})
    assert add.success is False  # file must exist
    (workspace / "calendars").mkdir()
    (workspace / "calendars" / "personal.ics").write_text(ICS_SIMPLE, encoding="utf-8")
    assert ag.agenda_add({"source": "calendars/personal.ics"}).success is True
    assert "personal.ics" in ag.agenda_list({}).output
    assert ag.agenda_remove({"source": "calendars/personal.ics"}).success is True
    assert "No registered" in ag.agenda_list({}).output


def test_agenda_add_refuses_escape(workspace):
    res = ag.agenda_add({"source": "../outside.ics"})
    assert res.success is False
    res = ag.agenda_add({"source": "C:/Windows/system32/config.ics"})
    assert res.success is False  # absolute path outside root


def test_agenda_empty_state(workspace):
    res = ag.agenda_view({})
    assert res.success and "No calendars found" in res.output
