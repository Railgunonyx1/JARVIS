"""Routines — just-style declarative task files (casey/just).

A routine is a small recipe of steps the agent runs on request:

    {"name": "standup-digest",
     "steps": [
       {"tool": "web.search", "args": {"query": "AI news today"}},
       {"tool": "doc_report", "args": {...}},
       {"tool": "shell.execute", "args": {"command": "git status"}}
     ]}

Stored under memory/routines.json so they survive restarts and can be
inspected, run and deleted by name. Steps run through the same tool
executor the agent uses — no new privilege path.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from tools.schema import ToolResult, truncate

logger = logging.getLogger("jarvis.tools.routines")

MAX_STEPS = 20
MAX_NAME = 64
STEP_TIMEOUT = 120.0


def _store() -> Path:
    from core.project import ProjectContext
    return ProjectContext.discover().root_path / "memory" / "routines.json"


def _load() -> dict[str, dict[str, Any]]:
    p = _store()
    if not p.exists():
        return {}
    try:
        import json

        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        logger.warning("routines store unreadable, starting fresh", exc_info=True)
        return {}


def _save(data: dict[str, dict[str, Any]]) -> None:
    import json

    p = _store()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ manage

def routine_add(args: dict[str, Any]) -> ToolResult:
    """Create/update a named routine from a step list."""
    name = str(args.get("name", "")).strip()[:MAX_NAME]
    if not name:
        return ToolResult(success=False, error="name is required")
    steps = args.get("steps") or []
    if isinstance(steps, dict):
        steps = [steps]
    steps = [s for s in steps if isinstance(s, dict)][:MAX_STEPS]
    if not steps:
        return ToolResult(
            success=False,
            error="steps is required: a list of {'tool': ..., 'args': {...}} steps",
        )
    cleaned = []
    for i, s in enumerate(steps, 1):
        tool = str(s.get("tool", "")).strip()
        if not tool:
            return ToolResult(success=False, error=f"step {i}: 'tool' is required")
        cleaned.append({"tool": tool, "args": s.get("args") or {}})

    data = _load()
    replaced = name in data
    data[name] = {
        "steps": cleaned,
        "created": data.get(name, {}).get("created") or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "runs": data.get(name, {}).get("runs", 0),
    }
    _save(data)
    return ToolResult(
        success=True,
        output=f"Routine '{name}' {'updated' if replaced else 'created'} with {len(cleaned)} steps.",
        metadata={"name": name, "steps": len(cleaned), "replaced": replaced},
    )


def routine_list(args: dict[str, Any]) -> ToolResult:
    """List stored routines with step counts and run history."""
    data = _load()
    if not data:
        return ToolResult(success=True, output="No routines stored yet.")
    lines = []
    for name, entry in sorted(data.items()):
        tools_used = ", ".join(s.get("tool", "?") for s in entry.get("steps", []))
        lines.append(f"{name}: {len(entry.get('steps', []))} steps [{tools_used}] runs={entry.get('runs', 0)}")
    return ToolResult(success=True, output="\n".join(lines), metadata={"count": len(data)})


def routine_remove(args: dict[str, Any]) -> ToolResult:
    """Delete a routine by name."""
    name = str(args.get("name", "")).strip()
    data = _load()
    if name not in data:
        return ToolResult(success=False, error=f"No routine named '{name}'")
    del data[name]
    _save(data)
    return ToolResult(success=True, output=f"Routine '{name}' removed.")


# -------------------------------------------------------------------- run

def routine_run(args: dict[str, Any]) -> ToolResult:
    """Resolve a routine into an ordered execution plan.

    Steps are deliberately NOT executed inside this handler: nested tool
    execution would bypass the permission/authorization boundary (the same
    policy-bypass class flagged in the Orbit runtime audit). Instead the
    routine is validated against the live tool registry and returned as a
    ready-to-run plan; the agent then performs each step through the normal
    ToolExecutionService path, so every step is audited like any other call.
    """
    from tools import build_default_registry

    name = str(args.get("name", "")).strip()
    data = _load()
    entry = data.get(name)
    if not entry:
        known = ", ".join(sorted(data)) or "(none)"
        return ToolResult(success=False, error=f"No routine named '{name}'. Known: {known}")

    steps = entry.get("steps", [])
    # Validate against the real registry so typos fail before any step runs.
    registry = build_default_registry()
    plan: list[dict[str, Any]] = []
    unknown: list[str] = []
    for i, step in enumerate(steps, 1):
        tool = str(step.get("tool", ""))
        if registry.get(tool) is None:
            unknown.append(f"step {i}: '{tool}'")
            continue
        plan.append({"step": i, "tool": tool, "args": step.get("args") or {}})
    if unknown:
        return ToolResult(
            success=False,
            error="Routine references unknown tools: " + "; ".join(unknown)
            + ". Fix with routine.add.",
        )

    data[name]["runs"] = int(data[name].get("runs", 0)) + 1
    _save(data)

    import json

    body = [
        f"Routine '{name}': {len(plan)} steps, validated against the tool registry.",
        "Execute each step in order with its tool now:",
    ]
    body.extend(json.dumps(p, ensure_ascii=False) for p in plan)
    return ToolResult(
        success=True,
        output=truncate("\n".join(body), 12000),
        metadata={"name": name, "steps": len(plan), "plan": plan},
    )


__all__ = ["routine_add", "routine_list", "routine_remove", "routine_run"]
