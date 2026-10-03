"""Dead-man's switch for scheduled/recurring tasks — healthchecks.io semantics.

Derived from healthchecks/healthchecks: a long-running or cron-driven task
pings `task.ping` on every successful run. If the ping stops (the job died,
the machine rebooted, the scheduler broke), `task.alert` detects the silence
and — when a ntfy/Gotify target is configured — pushes a notification so the
user learns about the failure before they discover it themselves.

State is persisted under memory/ so check-ins survive restarts.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from tools.schema import ToolResult, truncate

logger = logging.getLogger("jarvis.tools.task_pulse")

MAX_TASKS = 200
MAX_OUTPUT = 3000


def _state_path() -> Path:
    from core.project import ProjectContext

    return ProjectContext.discover().root_path / "memory" / "task_pulse_state.json"


def _load() -> dict[str, dict[str, Any]]:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save(state: dict[str, dict[str, Any]]) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=1), encoding="utf-8")


def _slug(name: str) -> str:
    """Stable key: lowercase, alnum + dashes only."""
    out = []
    for ch in name.strip().lower():
        out.append(ch if (ch.isalnum() or ch in "-_") else "-")
    slug = "".join(out).strip("-")
    return slug or "task"


def _push(subject: str, body: str, priority: str) -> str | None:
    """Best-effort push via notify.send; returns error string or None."""
    try:
        from tools.notify import send_notification

        res = send_notification({
            "title": subject[:120],
            "message": body[:2000],
            "priority": priority,
        })
        return None if res.success else (res.error or "notify failed")
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def task_ping(args: dict[str, Any]) -> ToolResult:
    """Record a successful check-in for a named task (healthchecks-style ping).

    Called by the agent at the END of a recurring task. First ping registers
    the task; `expect_minutes` sets the silence threshold for task.alert.
    """
    name = str(args.get("name", "")).strip()
    if not name:
        return ToolResult(success=False, error="name is required")
    try:
        expect_minutes = max(1.0, float(args.get("expect_minutes", 60.0)))
    except (TypeError, ValueError):
        expect_minutes = 60.0

    state = _load()
    if len(state) >= MAX_TASKS and _slug(name) not in state:
        return ToolResult(success=False, error=f"Task limit reached ({MAX_TASKS}).")
    now = time.time()
    prev = state.get(_slug(name))
    entry = {
        "name": name,
        "slug": _slug(name),
        "last_ping": now,
        "pings": int(prev.get("pings", 0)) + 1 if prev else 1,
        "expect_minutes": expect_minutes,
        "first_ping": (prev or {}).get("first_ping", now),
        "last_alert": (prev or {}).get("last_alert", 0),
        "grace_alerted": False,  # a fresh ping clears any open alert
    }
    state[_slug(name)] = entry
    _save(state)
    return ToolResult(
        success=True,
        output=(
            f"Ping recorded: {name} (#{entry['pings']}). "
            f"Alert if silent > {expect_minutes:.0f}m."
        ),
        metadata={
            "slug": entry["slug"],
            "pings": entry["pings"],
            "expect_minutes": expect_minutes,
        },
    )


def task_alert(args: dict[str, Any]) -> ToolResult:
    """Sweep all tasks; report (and optionally push) any that went silent.

    A task is OVERDUE when now - last_ping > expect_minutes. With
    `notify=true`, a ntfy/Gotify push is sent once per silence episode
    (re-armed by the next successful ping) so the user is not spammed.
    """
    notify = bool(args.get("notify", True))
    state = _load()
    if not state:
        return ToolResult(success=True, output="No tasks are pinging. Nothing to check.")

    now = time.time()
    overdue: list[tuple[str, dict[str, Any], float]] = []
    healthy = 0
    for slug, entry in state.items():
        expect = float(entry.get("expect_minutes", 60.0))
        silent_for_min = (now - float(entry.get("last_ping", 0))) / 60.0
        if silent_for_min > expect:
            overdue.append((slug, entry, silent_for_min))
        else:
            healthy += 1
    overdue.sort(key=lambda t: -t[2])

    errors: list[str] = []
    for slug, entry, silent_min in overdue:
        if notify and not entry.get("grace_alerted"):
            err = _push(
                "JARVIS task silent",
                f"Task '{entry.get('name', slug)}' has not checked in for "
                f"{silent_min:.0f}m (expected every {float(entry.get('expect_minutes', 60)):.0f}m).",
                "high",
            )
            if err:
                errors.append(f"{slug}: {err}")
        entry["grace_alerted"] = True

    if notify and (overdue or errors):
        _save(state)

    if not overdue:
        return ToolResult(
            success=True,
            output=f"All {healthy} task(s) are checking in on schedule.",
            metadata={"healthy": healthy, "overdue": 0},
        )

    lines = [
        f"OVERDUE: {entry.get('name', slug)} — silent {(now - float(entry.get('last_ping', 0))) / 60:.0f}m "
        f"(expect every {float(entry.get('expect_minutes', 60)):.0f}m, "
        f"{entry.get('pings', 0)} pings total)"
        for slug, entry, _ in overdue
    ]
    body = truncate("\n".join(lines), MAX_OUTPUT)
    note = ""
    if errors:
        note = f" (push failed: {'; '.join(errors)})"
    pushed = "pushed" if notify else "local only"
    return ToolResult(
        success=True,
        output=f"{len(overdue)} task(s) overdue [{pushed}]{note}:\n{body}",
        metadata={
            "healthy": healthy,
            "overdue": len(overdue),
            "slugs": [s for s, _, _ in overdue],
            "notified": notify and not errors,
        },
    )


__all__ = ["task_ping", "task_alert"]
