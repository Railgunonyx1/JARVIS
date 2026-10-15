"""Watch rules — chain page.watch diffs into notifications (huginn-style).

Derived from huginn/huginn agents + dgtlmoon/changedetection.io notification
agents: a rule binds a watched URL to an action so "the page changed" becomes
"the user hears about it" without the agent having to remember the chain.
The condition stays simple and inspectable: changed / unchanged / any.

Rules are persisted under memory/ alongside page-watch state so they survive
restarts. Running `watch.run` evaluates every rule: it re-checks the URL via
page_watch, compares against the rule's trigger, and fires the bound action
(currently: push notification via notify.send; 'agent_note' records the event
into the rule's history for the next agent turn).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from tools.schema import ToolResult, truncate

logger = logging.getLogger("jarvis.tools.watch_rules")

MAX_RULES = 100
MAX_HISTORY = 20
MAX_OUTPUT = 4000

_VALID_TRIGGERS = {"changed", "unchanged", "any"}
_VALID_ACTIONS = {"notify", "agent_note"}


def _rules_path() -> Path:
    from core.project import ProjectContext

    return ProjectContext.discover().root_path / "memory" / "watch_rules.json"


def _load() -> dict[str, dict[str, Any]]:
    try:
        return json.loads(_rules_path().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save(rules: dict[str, dict[str, Any]]) -> None:
    p = _rules_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rules, indent=1), encoding="utf-8")


def _slug(url: str) -> str:
    import hashlib

    return hashlib.sha256(url.encode()).hexdigest()[:16]


def watch_rule(args: dict[str, Any]) -> ToolResult:
    """Create (action='add'), list, or remove (action='remove') watch rules."""
    action = str(args.get("action", "add")).lower()

    if action == "list":
        rules = _load()
        if not rules:
            return ToolResult(success=True, output="No watch rules defined.", metadata={"count": 0})
        lines = []
        for rid, r in rules.items():
            fired = r.get("fired_count", 0)
            last = r.get("last_fired", 0)
            ago = f"{(time.time() - last) / 60:.0f}m ago" if last else "never"
            lines.append(
                f"- [{rid[:8]}] {r['trigger']} on {r['url']} -> {r['action']}"
                f"  (fired {fired}x, last {ago})"
            )
        return ToolResult(
            success=True,
            output=truncate("\n".join(lines), MAX_OUTPUT),
            metadata={"count": len(rules)},
        )

    if action == "remove":
        rid = str(args.get("rule_id", "")).strip()
        rules = _load()
        matches = [k for k in rules if k.startswith(rid)] if rid else []
        if not matches:
            return ToolResult(success=False, error=f"No rule matching '{rid}'. Use watch.rule action='list'.")
        for k in matches:
            del rules[k]
        _save(rules)
        return ToolResult(success=True, output=f"Removed {len(matches)} rule(s).")

    # default: add
    url = str(args.get("url", "")).strip()
    if not url or not url.lower().startswith(("http://", "https://")):
        return ToolResult(success=False, error="url (http/https) is required")
    trigger = str(args.get("trigger", "changed")).lower()
    if trigger not in _VALID_TRIGGERS:
        return ToolResult(success=False, error=f"trigger must be one of {sorted(_VALID_TRIGGERS)}")
    rule_action = str(args.get("then", "notify")).lower()
    if rule_action not in _VALID_ACTIONS:
        return ToolResult(success=False, error=f"then must be one of {sorted(_VALID_ACTIONS)}")
    message = str(args.get("message", "")).strip()[:300]

    rid = _slug(url + "|" + trigger + "|" + rule_action)
    rules = _load()
    if len(rules) >= MAX_RULES and rid not in rules:
        return ToolResult(success=False, error=f"Rule limit reached ({MAX_RULES}).")
    rules[rid] = {
        "url": url,
        "trigger": trigger,
        "action": rule_action,
        "message": message or f"Watch rule fired: {trigger} on {url}",
        "created_at": time.time(),
        "last_fired": 0,
        "fired_count": 0,
        "history": [],
    }
    _save(rules)
    # Also make sure a page watch exists (page_watch auto-arms on first check).
    try:
        from tools.page_watch import page_watch

        page_watch({"url": url, "action": "arm"})
    except Exception as exc:  # noqa: BLE001
        logger.debug("auto-arm failed for %s: %s", url, exc)
    return ToolResult(
        success=True,
        output=(
            f"Rule [{rid[:8]}] armed: when {url} is {trigger}, "
            f"then {rule_action}. Evaluate with watch.run."
        ),
        metadata={"rule_id": rid},
    )


def watch_run(args: dict[str, Any], *, page_watch_fn=None, send_notification_fn=None) -> ToolResult:
    """Evaluate every rule: re-check its URL, fire the action when triggered.

    ``page_watch_fn`` / ``send_notification_fn`` let callers inject alternate
    implementations (tests use this; embedders could route pushes elsewhere).
    """
    rules = _load()
    if not rules:
        return ToolResult(
            success=True, output="No watch rules to evaluate.",
            metadata={"fired": 0, "errors": 0, "quiet": 0},
        )

    fired: list[str] = []
    quiet: list[str] = []
    errors: list[str] = []

    # Resolve through this module so tests (and embedders) can patch either
    # the module attribute or the concrete implementations.
    page_watch = page_watch_fn if page_watch_fn else _page_watch
    send = send_notification_fn or _send_notification

    for rid, rule in rules.items():
        url = rule["url"]
        trigger = rule["trigger"]
        try:
            res = page_watch({"url": url, "action": "check"})
        except Exception as exc:  # noqa: BLE001
            errors.append(f"[{rid[:8]}] check failed: {exc}")
            continue
        changed = bool(res.metadata.get("changed"))
        triggered = (
            (trigger == "changed" and changed)
            or (trigger == "unchanged" and not changed and not res.metadata.get("first"))
            or (trigger == "any")
        )
        if not triggered:
            quiet.append(rid)
            continue

        note = str(rule.get("message", "")).strip()
        if rule["action"] == "notify":
            push = send({
                "title": "JARVIS watch rule",
                "message": note or f"{trigger} on {url}",
                "priority": "default",
            })
            if not push.success:
                errors.append(f"[{rid[:8]}] notify failed: {push.error}")
                continue
        fired.append(f"[{rid[:8]}] {trigger} on {url} -> {rule['action']}")

        rule["fired_count"] = int(rule.get("fired_count", 0)) + 1
        rule["last_fired"] = time.time()
        hist = rule.setdefault("history", [])
        hist.append({"at": time.time(), "trigger": trigger, "note": note})
        rules[rid] = rule

    _prune_history(rules)
    _save(rules)
    parts = []
    if fired:
        parts.append("FIRED:\n" + "\n".join(fired))
    if errors:
        parts.append("ERRORS:\n" + "\n".join(errors))
    if not parts:
        parts.append(f"{len(quiet)} rule(s) checked — no triggers.")
    return ToolResult(
        success=True,
        output=truncate("\n".join(parts), MAX_OUTPUT),
        metadata={"fired": len(fired), "errors": len(errors), "quiet": len(quiet)},
    )


def _prune_history(rules: dict[str, dict[str, Any]]) -> None:
    """Cap per-rule history in place so the state file stays small."""
    for rule in rules.values():
        hist = rule.get("history")
        if isinstance(hist, list) and len(hist) > MAX_HISTORY:
            rule["history"] = hist[-MAX_HISTORY:]


__all__ = ["watch_rule", "watch_run"]


def _page_watch(args: dict[str, Any]) -> ToolResult:
    from tools.page_watch import page_watch

    return page_watch(args)


def _send_notification(args: dict[str, Any]) -> ToolResult:
    from tools.notify import send_notification

    return send_notification(args)
