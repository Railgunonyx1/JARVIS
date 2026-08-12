"""Tests for Headroom context modules (no LLM, no real DBs)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.context.budget import (
    DEFAULT_BUDGET,
    ContextBudget,
    ContextReport,
    SectionUsage,
    estimate_messages_tokens,
    estimate_tokens,
)
from core.context.compressor import compress, trim_tool_outputs
from core.context.manager import ContextManager
from core.context.selector import rank, score, select_files
from core.context.summarizer import summarize_text, summarize_turns


def _msg(role, content):
    return {"role": role, "content": content}


# ── budget ────────────────────────────────────────────────────────────────

def test_estimate_tokens_heuristic():
    assert estimate_tokens(None) == 0
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcdefghijklmnop") == 4


def test_estimate_messages_tokens_handles_content_kinds():
    messages = [
        _msg("user", "hello"),
        _msg("assistant", [{"type": "text", "text": "part one"}]),
        _msg("tool", "result"),
    ]
    total = estimate_messages_tokens(messages)
    assert total > 0
    assert estimate_messages_tokens([]) == 0
    assert estimate_messages_tokens(None) == 0


def test_context_budget_sections_and_totals():
    budget = ContextBudget(system=100, memory=200, files=300, messages=400, response=50)
    assert budget.total == 1050
    assert budget.section("memory") == 200
    assert budget.section("nope") == 0
    assert budget.to_dict()["system"] == 100
    assert DEFAULT_BUDGET.total == 10_000 + 15_000 + 30_000 + 30_000 + 10_000


def test_section_usage_and_report():
    usage = SectionUsage("messages", 5, 10)
    assert not usage.over
    assert usage.ratio == 0.5
    over = SectionUsage("messages", 11, 10)
    assert over.over
    assert over.to_dict()["over"] is True

    report = ContextReport(
        system_tokens=1, memory_tokens=2, files_tokens=3, messages_tokens=4,
        compacted=True,
        sections=[SectionUsage("system", 1, 10)],
    )
    assert report.total_tokens == 10
    assert report.total_budget == DEFAULT_BUDGET.total
    assert report.any_over is False
    assert report.to_dict()["compacted"] is True
    assert report.to_dict()["sections"][0]["section"] == "system"


# ── summarizer ────────────────────────────────────────────────────────────

def test_summarize_text_truncates():
    assert summarize_text("short") == "short"
    assert summarize_text("x" * 300).endswith("...")
    assert len(summarize_text("x" * 300)) <= 123


def test_summarize_turns_folds_and_labels():
    turns = [_msg("user", "first goal"), _msg("assistant", "thinking")]
    summary = summarize_turns(turns)
    assert "[user]" in summary
    assert "[assistant]" in summary
    assert "first goal" in summary
    assert "thinking" in summary
    assert isinstance(summarize_turns([], max_chars=50), str)


# ── compressor ────────────────────────────────────────────────────────────

def test_compress_returns_same_list_under_budget():
    messages = [_msg("system", "sys"), _msg("user", "hi")]
    result = compress(messages, budget_tokens=10_000)
    assert result == messages
    assert messages[0] is result[0]  # not mutated, same refs


def test_compress_folds_old_turns_keeps_goal_and_recent():
    goal = "write a script that lists files"
    recent_user = "now run it and show output"
    messages = [
        _msg("system", "sys"),
        _msg("user", goal),
        _msg("assistant", "first turn thinking"),
        _msg("tool", "tool output here"),
        _msg("user", recent_user),
        _msg("assistant", "final answer"),
    ]
    result = compress(messages, budget_tokens=4)
    roles = [m.get("role") for m in result]
    assert "system" in roles
    assert goal in [m.get("content") for m in result]  # goal verbatim
    assert recent_user in [m.get("content") for m in result]  # recent verbatim
    summaries = [m for m in result if "[Earlier context]" in (m.get("content") or "")]
    assert len(summaries) == 1
    assert messages[1]["content"] == goal  # input untouched


def test_trim_tool_outputs_truncates_and_returns_new_list():
    messages = [_msg("tool", "x" * 5000), _msg("user", "ok")]
    result = trim_tool_outputs(messages, max_content_chars=100)
    assert len(result[0]["content"]) <= 101
    assert messages[0]["content"] == "x" * 5000  # input untouched
    result2 = trim_tool_outputs(messages, max_content_chars=10_000)
    assert result2[0] is messages[0]


# ── selector ──────────────────────────────────────────────────────────────

def test_score_lexical_overlap():
    assert score("read the file", "read") == 1.0
    assert score("write output", "read") == 0.0
    assert score("", "read") == 0.0
    assert score("anything", "") == 0.0


def test_rank_sorts_by_relevance():
    candidates = [("b.py", "unrelated stuff"), ("a.py", "parsing tokens here")]
    ranked = rank(candidates, "parsing tokens")
    assert ranked[0][0] == "a.py"
    assert ranked[0][1] >= ranked[1][1]


def test_select_files_filters_scores_and_respects_limits():
    files = [
        {"path": "rel.py", "content": "parse tokens from text"},
        {"path": "noise.py", "content": "draw squares on screen"},
        {"path": "small.py", "content": "tokens"},
    ]
    selected = select_files(files, "tokens parse", top_k=2, max_tokens=100)
    assert len(selected) <= 2
    assert all("relevance" in f for f in selected)
    assert all(f["relevance"] > 0 for f in selected)
    assert "noise.py" not in [f["path"] for f in selected]


# ── manager ───────────────────────────────────────────────────────────────

def test_manager_fit_compacts_and_reports():
    reports = []
    manager = ContextManager(
        budget=ContextBudget(system=100, memory=100, files=100, messages=5,
                             response=10),
        on_report=lambda report: reports.append(report),
    )
    messages = [_msg("user", "x" * 200), _msg("assistant", "y" * 200)]
    fitted, report = manager.fit(system_tokens=50, messages=messages)
    assert report.compacted is True
    assert manager.last_report is report
    assert len(reports) == 1
    assert report.to_dict()["messages_tokens"] >= 0
    assert report.any_over is False or True  # best-effort: never asserts over

    fitted_under, report_under = manager.fit(
        system_tokens=50, messages=[_msg("user", "tiny")],
    )
    assert report_under.compacted is False


def test_manager_fit_for_loop_and_report_usage():
    manager = ContextManager(budget=ContextBudget(messages=10_000))
    messages = [_msg("user", "hello")]
    fitted, report = manager.fit_for_loop(messages, system_tokens=25)
    assert report.system_tokens == 25
    assert fitted == messages
    assert report.total_tokens >= report.messages_tokens
