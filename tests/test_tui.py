"""Tests for the Textual dashboard's data layer and headless app run.

Covers ``ui.providers.provider_rows`` (pure mapping of daemon router
status to table rows) and a headless ``App.run_test`` boot of the whole
dashboard against the forced-mock backend. No daemon, no network, no LLM.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── provider_rows mapping ────────────────────────────────────────────────────

def test_provider_rows_marks_available():
    from ui.providers import provider_rows

    status = {"groq": {"available": True, "package_ok": True,
                       "model": "llama-3.1-8b-instant",
                       "health": {"latency_ms": 42.0, "error_rate": 0.0}}}
    rows = provider_rows(status)
    assert rows == [("GROQ", "ONLINE", "42ms", "-", "llama-3.1-8b-instant")]


def test_provider_rows_marks_unavailable_and_formats_rate():
    from ui.providers import provider_rows

    status = {"ollama": {"available": False, "package_ok": True,
                         "model": "qwen2.5:1.5b",
                         "health": {"latency_ms": 0.0, "error_rate": 0.12}}}
    rows = provider_rows(status)
    assert rows == [("OLLAMA", "OFFLINE", "-", "12%", "qwen2.5:1.5b")]


def test_provider_rows_sorts_and_skips_empty():
    from ui.providers import provider_rows

    rows = provider_rows({"z": None, "a": {}, "m": {"available": True}})
    names = [row[0] for row in rows]
    assert names == ["A", "M", "Z"]
    by_name = {row[0]: row[1] for row in rows}
    assert by_name["M"] == "ONLINE"
    assert by_name["A"] == "OFFLINE"
    assert by_name["Z"] == "OFFLINE"


# ── headless app boot ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dashboard_boots_in_mock_mode():
    pytest.importorskip("textual")

    from ui.backend import TuiDataSource
    from ui.tui import JarvisApp

    source = TuiDataSource(mock=True)
    app = JarvisApp(data_source=source)

    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.data_source is source
        assert not app.data_source.connected
        assert app.data_source.using_mock_providers
        assert "mock" in app.data_source.last_error.lower()
        from ui.tui import LogsPanel
        assert app.query_one(LogsPanel) is not None
        assert app.query_one("#providers-table") is not None
        assert app.query_one("#tasks-table") is not None


# ── new feature panels (mock mode) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_plan_and_mcp_panels_render():
    pytest.importorskip("textual")

    from ui.backend import TuiDataSource
    from ui.tui import AgentPlanPanel, JarvisApp, McpPanel

    source = TuiDataSource(mock=True)
    app = JarvisApp(data_source=source)

    async with app.run_test() as pilot:
        await pilot.pause()

        plan = app.query_one(AgentPlanPanel)
        plan_table = app.query_one("#plan-table")
        assert plan_table.row_count == len(source.plan_rows)
        title = str(plan.query_one(".panel-title").render())
        assert "4/6" in title

        app.query_one(McpPanel)
        mcp_table = app.query_one("#mcp-table")
        assert mcp_table.row_count == len(source.mcp_rows)
        assert all(row[2] == "ONLINE" for row in source.mcp_rows)


@pytest.mark.asyncio
async def test_mode_select_present_and_disabled_offline():
    pytest.importorskip("textual")

    from ui.backend import TuiDataSource
    from ui.tui import JarvisApp

    app = JarvisApp(data_source=TuiDataSource(mock=True))

    async with app.run_test() as pilot:
        await pilot.pause()
        select = app.query_one("#mode-select")
        assert select.value == "smart"
        assert select.disabled  # daemon offline at boot


@pytest.mark.asyncio
async def test_write_event_tags():
    pytest.importorskip("textual")

    from ui.backend import TuiDataSource
    from ui.tui import JarvisApp, LogsPanel

    app = JarvisApp(data_source=TuiDataSource(mock=True))
    async with app.run_test() as pilot:
        await pilot.pause()
        logs = app.query_one(LogsPanel)
        logs.clear()
        logs.write_event("tool_execution.started")
        logs.write_event("goal.completed")
        text = " ".join(logs.query_one("#logs-view").lines)
        assert "[TOOL]" in text
        assert "[OK]" in text
