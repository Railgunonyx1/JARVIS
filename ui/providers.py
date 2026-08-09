"""Pure data-shape helpers for the TUI (no Textual / daemon imports).

Kept import-light so the provider mapping can be unit-tested without
dragging in the UI stack. The daemon already exposes per-provider health
via its ``models`` status action (router.status); these helpers translate
that into the rows the dashboard tables render.
"""

from __future__ import annotations

# Honest fallback rows: this repo's actual providers, clearly marked mock.
MOCK_PROVIDERS: list[tuple[str, str, str, str, str]] = [
    ("GROQ", "ONLINE", "-", "-", "llama-3.1-8b-instant"),
    ("GEMINI", "ONLINE", "-", "-", "gemini-2.0-flash"),
    ("OPENROUTER", "OFFLINE", "-", "-", "-"),
    ("OPENCODE_ZEN", "OFFLINE", "-", "-", "-"),
    ("OLLAMA", "OFFLINE", "-", "-", "qwen2.5:1.5b"),
]  # MOCK — real rows come from the daemon's router status

# Placeholder rows; the daemon does not expose a task list yet.
MOCK_TASKS: list[tuple[str, str, str, int, str]] = [
    ("-", "Provider health check", "IDLE", 0, "-"),
    ("-", "Memory consolidation", "IDLE", 0, "-"),
    ("-", "Document index", "IDLE", 0, "-"),
]  # MOCK — no task endpoint on the daemon yet (roadmap follow-up)


def provider_rows(router_status: dict) -> list[tuple[str, str, str, str, str]]:
    """Map the daemon's router status dict to provider-table rows.

    ``router_status`` is what the daemon returns for the ``models`` action:
    ``{name: {available, model, package_ok, health: {latency_ms, error_rate,
    consecutive_failures, cooldown_until}}}``. Returns
    ``(name, STATUS, latency, rate, model)`` rows.
    """
    rows: list[tuple[str, str, str, str, str]] = []
    for name in sorted(router_status):
        info = router_status[name] or {}
        health = info.get("health") or {}
        latency_ms = float(health.get("latency_ms", 0.0) or 0.0)
        latency = f"{int(latency_ms)}ms" if latency_ms > 0 else "-"
        error_rate = float(health.get("error_rate", 0.0) or 0.0)
        rate = f"{error_rate * 100:.0f}%" if error_rate > 0 else "-"
        online = bool(info.get("available")) and bool(info.get("package_ok", True))
        rows.append((name.upper(), "ONLINE" if online else "OFFLINE",
                     latency, rate, str(info.get("model", "unknown"))))
    return rows
