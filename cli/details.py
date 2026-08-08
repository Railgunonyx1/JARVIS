"""Expanded task details for the JARVIS MK-X terminal.

Conversation stays dominant: after each task the CLI prints a one-line
collapsed summary, and pressing Enter expands it into the full report:

    Summary / Reasoning / Files Read / Commands / Memory / Tokens / Execution

Built entirely from AgentResult + AgentState — no extra instrumentation.
ANSI palette is restrained: green success, blue info, purple reasoning,
red errors, gray inactive.
"""

from __future__ import annotations

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.agent.observer import TaskStatus


def _section(title: str, body, border: str = "blue") -> Panel:
    return Panel(body, title=title, border_style=border)


def render_summary(result) -> str:
    """One-line collapsed result — the default after a task."""
    obs = result.observation or {}
    steps = obs.get("steps", [])
    chain = " → ".join(f"{s['tool']}" for s in steps[:8])
    if len(steps) > 8:
        chain += f" +{len(steps) - 8} more"
    status = obs.get("status", TaskStatus.COMPLETED.value)
    if status in ("completed", "ok"):
        head = f"✔ {result.state.goal[:64]}"
    elif status == "error":
        head = f"✘ {result.state.goal[:64]}"
    else:
        head = f"· {result.state.goal[:64]}"
    bits = [head]
    if chain:
        bits.append(chain)
    bits.append(f"{obs.get('duration_ms', 0):.0f}ms")
    bits.append(f"{obs.get('tokens_used', result.state.tokens_used)} tok")
    return "  │  ".join(bits)


def _files_read(result) -> list:
    names = []
    for call in result.state.tool_calls:
        name = call.get("name", "")
        args = call.get("args") or {}
        if name in ("filesystem_write", "filesystem_read", "filesystem_edit"):
            target = args.get("path") or args.get("file")
        elif name in ("project_find", "grep"):
            target = args.get("pattern")
        else:
            target = None
        if target:
            names.append(str(target))
        elif call.get("output"):
            names.append(str(call["output"])[:60])
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _execution_table(result) -> Table:
    obs = result.observation or {}
    steps = obs.get("steps", [])
    total = obs.get("duration_ms") or 0
    tools_ms = sum(s.get("duration_ms", 0) for s in steps)
    rows = [
        ("Tools", tools_ms),
        ("LLM", max(0, total - tools_ms)),
        ("Total", total),
    ]
    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column("stage", style="dim")
    table.add_column("ms", justify="right")
    for label, val in rows:
        table.add_row(label, f"{val:.0f}")
    return table


def render_expanded(result) -> Group:
    """Full drill-down report for a finished task."""
    state = result.state
    obs = result.observation or {}
    sections: list = []

    status = obs.get("status", "")
    status_style = "green" if status in ("completed", "ok") else "red"
    head = Text(
        f"{'✔' if status in ('completed', 'ok') else '✘'} {state.goal}",
        style=f"bold {status_style}",
    )
    sections.append(_section("Repository Audit", head, border=status_style))

    summary_lines = [Text(f"{state.goal}")]
    if obs.get("steps"):
        marks = {"ok": "✔", "error": "✘", "denied": "!", "running": "●"}
        for s in obs["steps"]:
            mark = marks.get(s.get("status"), "·")
            line = Text(f"  {mark} {s['tool']}  {s.get('duration_ms', 0):.0f}ms", style="dim")
            summary_lines.append(line)
    sections.append(_section("Steps", Group(*summary_lines), border="green"))

    files = _files_read(result)
    if files:
        body = Group(*[Text(f"  {f}", style="blue") for f in files])
        sections.append(_section("Files Read", body))

    calls = [c for c in state.tool_calls if c.get("name")]
    if calls:
        rows = [Text(f"  {c['name']}  {c.get('duration_ms', 0):.0f}ms  {c.get('output', '')[:80]}", style="dim")
                for c in calls]
        sections.append(_section("Commands", Group(*rows)))

    tokens = Table(box=None, show_header=False, pad_edge=False)
    tokens.add_column("flow", style="dim")
    tokens.add_column("count", justify="right")
    tokens.add_row("Total", str(state.tokens_used))
    usage = obs.get("context_usage") or state.context_usage or {}
    if usage:
        for key, label in (
            ("system_tokens", "System"),
            ("memory_tokens", "Memory"),
            ("files_tokens", "Files"),
            ("messages_tokens", "Conversation"),
            ("total_tokens", "Context"),
        ):
            val = usage.get(key)
            if val is not None:
                tokens.add_row(label, str(val))
        if usage.get("total_budget"):
            tokens.add_row("Budget", str(usage["total_budget"]))
        if usage.get("compacted"):
            tokens.add_row("Compressed", "yes")
    sections.append(_section("Tokens", tokens))

    exec_table = _execution_table(result)
    sections.append(_section("Execution", exec_table, border="purple"))

    model_line = Text(
        f"  provider={state.provider}  model={state.model}"
        + (f"  mode={obs.get('mode', '')}" if obs.get("mode") else ""),
        style="dim",
    )
    sections.append(_section("Models", model_line, border="cyan"))

    if state.errors:
        errs = Group(*[Text(f"  ! {e}", style="red") for e in state.errors[:6]])
        sections.append(_section("Errors", errs, border="red"))

    return Group(*sections)
