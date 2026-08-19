"""Cockpit — persistent command-center dashboard for the JARVIS MK-X terminal.

Rendered with Rich Layout/Panels between commands and re-rendered after every
task so the user always sees, at a glance:
    - header: workspace, mode, model, tool count
    - center: last task (Task Observer)
    - right:  memory stats + recent decisions (Mem)
    - bottom: Headroom context bars (System / Memory / Files / Conv)

No polling: it is recomputed on demand (startup, after each task, /cockpit).
"""

from __future__ import annotations

import datetime

from rich import box
from rich.console import Group
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

_W = 12


def _bar(ratio: float, width: int = _W) -> Text:
    filled = max(0, min(width, int(round(ratio * width))))
    style = "green" if ratio < 0.8 else ("yellow" if ratio < 1.0 else "red")
    return Text("█" * filled + "░" * (width - filled), style=style)


def _header_panel(loop) -> Panel:
    bits = [
        "JARVIS MK-X",
        f"mode={loop.mode}",
        f"project={loop.project.root_path}",
    ]
    if loop.project.language:
        bits.append(f"lang={loop.project.language}")
    if loop.project.framework:
        bits.append(f"framework={loop.project.framework}")
    if getattr(loop.router, "_last_provider", None):
        bits.append(f"model={loop.router._last_provider}/{loop.router._last_model}")
    bits.append(f"tools={len(loop.registry.list())}")
    return Panel(Text("  ".join(bits)), box=box.ROUNDED, border_style="cyan")


def _memory_panel(loop) -> Panel:
    if loop.mem is None:
        return Panel(Text("memory disabled"), title="MEMORY", border_style="magenta")
    stats = loop.mem.get_stats()
    lines = [
        Text(
            f"memories={stats.get('memories', 0)}  decisions={stats.get('decisions', 0)}"
            f"  knowledge={stats.get('knowledge', 0)}",
            style="dim",
        ),
    ]
    for d in loop.mem.recall_decisions(project=str(loop.project.root_path), query="", limit=4):
        lines.append(Text(f"- {d['goal'][:38]} → {d['decision']}", style="dim"))
    return Panel(Group(*lines), title="MEMORY", border_style="magenta")


def _context_panel(loop) -> Panel:
    report = loop.context_manager.last_report
    if report is None:
        return Panel(Text("no context data yet"), title="CONTEXT", border_style="blue")
    data = report.to_dict()
    lines = [
        Text(
            f"total {data['total_tokens']}/{data['total_budget']} tokens"
            + ("  [compacted]" if data.get("compacted") else ""),
        ),
    ]
    for section in data.get("sections", []):
        ratio = section["ratio"]
        bar = _bar(ratio)
        label = Text(f"{section['section']:<9} ")
        tokens = Text(f" {section['tokens']}/{section['budget']}", style="dim")
        lines.append(Group(label, bar, tokens))
    return Panel(Group(*lines), title="CONTEXT", border_style="blue")


def _task_panel(loop) -> Panel:
    result = getattr(loop, "_last_result", None)
    if result is None:
        return Panel(Text("no task yet — type a goal below", style="dim"),
                     title="TASK OBSERVER", border_style="green")
    obs = result.observation or {}
    steps = obs.get("steps", [])
    lines = [
        Text(f"task {result.trace_id} · {result.state.goal[:56]}", style="bold"),
        Text(
            f"status={obs.get('status')}  iterations={obs.get('iterations')}"
            f"  tokens={obs.get('tokens_used')}",
            style="dim",
        ),
    ]
    for s in steps:
        mark = {"ok": "+", "error": "!", "denied": "x", "running": ">"}.get(s.get("status"), "?")
        lines.append(Text(f"  {mark} {s['tool']} {s.get('duration_ms', 0):.0f}ms", style="dim"))
    return Panel(Group(*lines), title="TASK OBSERVER", border_style="green")


_FOOTER_HINTS = (
    "/help  /mode  /plan  /model  /models  /tokens  /context  /cockpit  "
    "/memory  /history  /tree  /resume  /clear  /exit"
)


def render_cockpit(loop) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(_header_panel(loop), name="header", size=3),
        Layout(name="middle"),
        Layout(Text(_FOOTER_HINTS, style="dim"), name="footer", size=1),
    )
    layout["middle"].split_row(
        Layout(name="left", ratio=3),
        Layout(name="right", size=40),
    )
    layout["left"].split_column(
        Layout(name="task", ratio=2),
        Layout(name="context", size=7),
    )
    layout["left"]["task"].update(_task_panel(loop))
    layout["left"]["context"].update(_context_panel(loop))
    layout["right"].update(_memory_panel(loop))
    return layout


def render_status_bar(loop) -> Text:
    """Compact single-line status shown before the prompt — no panels."""
    bits = ["JARVIS"]
    bits.append(f"mode={loop.mode}")
    if getattr(loop.router, "_last_provider", None):
        bits.append(f"{loop.router._last_model}/{loop.router._last_provider}")
    bits.append(f"tools={len(loop.registry.list())}")
    if loop.mem is not None:
        stats = loop.mem.get_stats()
        bits.append(f"mem={stats.get('decisions', 0)}d/{stats.get('knowledge', 0)}k")
    report = getattr(loop.context_manager, "last_report", None)
    if report is not None:
        data = report.to_dict()
        ratio = data.get("total_tokens", 0) / data.get("total_budget", 1)
        width = 6
        filled = max(0, min(width, int(round(ratio * width))))
        bar = "█" * filled + "░" * (width - filled)
        bits.append(f"ctx {ratio:.0%} {bar}")
        bits.append(f"{data.get('total_tokens', 0):,} tok")
    bits.append(f"time={datetime.datetime.now().strftime('%H:%M:%S')}")
    text = Text("  │  ".join(bits))
    return text


def render_notifications(notifications) -> Group:
    """Rolling event log — last few notifications as a dim list."""
    if not notifications:
        return Group(Text("  no events yet", style="dim"))
    lines = []
    for item in notifications[-8:]:
        kind, msg = item
        mark = {"ok": "✓", "warn": "⚠", "err": "✘", "info": "·"}.get(kind, "·")
        style = {"ok": "green", "warn": "yellow", "err": "red"}.get(kind, "dim")
        lines.append(Text(f"  {mark} {msg}", style=style))
    return Group(*lines)
