"""Secret references — Infisical-style indirection for agent credentials.

Derived from Infisical/infisical: skills and routines should be able to say
"call the API with the key stored under PROVIDER/GROQ" without the raw secret
ever entering the model's context. `secret.ref` resolves a reference to a
process-environment variable (or a `memory/secrets.json` entry), returns the
value ONLY as a scoped handle that tool handlers accept, and `secret.status`
shows what is configured with values masked to a fingerprint.

Security posture:
- Values are NEVER echoed by secret.ref / secret.status (masked fingerprints).
- Only exact, uppercase, [A-Z0-9_] names are accepted (no traversal, no
  arbitrary expression evaluation).
- The agent cannot enumerate the environment: status lists only names that
  are explicitly registered in the local index (memory/secrets_index.json).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from tools.schema import ToolResult

logger = logging.getLogger("jarvis.tools.secret_ref")

_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_MAX_REFS = 500


def _index_path() -> Path:
    from core.project import ProjectContext

    return ProjectContext.discover().root_path / "memory" / "secrets_index.json"


def _load_index() -> dict[str, dict[str, Any]]:
    try:
        return json.loads(_index_path().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_index(idx: dict[str, dict[str, Any]]) -> None:
    p = _index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(idx, indent=1), encoding="utf-8")


def _mask(value: str) -> str:
    """Short, non-reversible fingerprint for humans: first2…last2 + len."""
    if not value:
        return "(empty)"
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:2]}…{value[-2:]} (len={len(value)})"


def secret_ref(args: dict[str, Any]) -> ToolResult:
    """Resolve NAME to a masked handle; register it in the local index.

    `secret.ref` is the agent-facing way to use credentials WITHOUT seeing
    them: the model passes `ref` = the returned handle into tools that
    support it (HTTP tools may accept {"secret_ref": ...}). The raw value
    stays in the process environment.
    """
    action = str(args.get("action", "resolve")).lower()
    name = str(args.get("name", "")).strip()

    if action == "register":
        if not _NAME_RE.match(name):
            return ToolResult(
                success=False,
                error="name must be UPPER_SNAKE_CASE (the env var to register).",
            )
        value = os.environ.get(name)
        idx = _load_index()
        if value is None:
            return ToolResult(
                success=False,
                error=f"{name} is not set in the environment; nothing to register.",
            )
        if len(idx) >= _MAX_REFS and name not in idx:
            return ToolResult(success=False, error=f"Reference limit reached ({_MAX_REFS}).")
        idx[name] = {
            "registered_at": __import__("time").time(),
            "fingerprint": _mask(value),
            "source": "env",
        }
        _save_index(idx)
        return ToolResult(
            success=True,
            output=f"Registered {name} ({idx[name]['fingerprint']}).",
            metadata={"name": name, "source": "env"},
        )

    if action == "forget":
        idx = _load_index()
        if name in idx:
            del idx[name]
            _save_index(idx)
            return ToolResult(success=True, output=f"Removed {name} from the index.")
        return ToolResult(success=False, error=f"{name} is not registered.")

    # default: resolve
    if not _NAME_RE.match(name):
        return ToolResult(
            success=False,
            error="name must be UPPER_SNAKE_CASE (e.g. GROQ_API_KEY).",
        )
    idx = _load_index()
    if name not in idx:
        return ToolResult(
            success=False,
            error=(
                f"{name} is not in the local reference index. Ask the user to "
                f"register it first (secret.ref action='register'). The agent "
                f"cannot enumerate the environment."
            ),
        )
    value = os.environ.get(name)
    if value is None:
        return ToolResult(
            success=False,
            error=f"{name} was registered but is no longer set in the environment.",
        )
    # Never return the value into model context — return a scoped handle.
    handle = f"secret:{name}#{hashlib.sha256(value.encode()).hexdigest()[:8]}"
    return ToolResult(
        success=True,
        output=(
            f"Resolved {name} -> handle {handle} "
            f"(value stays in the process environment; {idx[name].get('fingerprint', 'masked')})."
        ),
        metadata={
            "name": name,
            "handle": handle,
            "fingerprint": idx[name].get("fingerprint"),
            "source": "env",
        },
    )


def secret_status(args: dict[str, Any]) -> ToolResult:
    """List registered references with masked fingerprints (never values)."""
    idx = _load_index()
    if not idx:
        return ToolResult(
            success=True,
            output="No secret references registered. Use secret.ref action='register'.",
        )
    lines = []
    for name, meta in sorted(idx.items()):
        still_set = "set" if os.environ.get(name) is not None else "MISSING"
        lines.append(f"- {name}: {meta.get('fingerprint', 'masked')} [{still_set}]")
    return ToolResult(
        success=True,
        output="\n".join(lines),
        metadata={"count": len(idx)},
    )


__all__ = ["secret_ref", "secret_status"]
