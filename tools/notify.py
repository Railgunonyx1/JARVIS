"""Push notifications for long-running tasks — ntfy.sh and Gotify.

Derived from binwiederhier/ntfy + gotify/server: when the agent finishes a
long task (or hits an error worth waking the user for) it can push a
notification to the user's phone/desktop without any account setup (ntfy
public topics) or with a self-hosted Gotify server.

Config via env:
    JARVIS_NTFY_URL     e.g. https://ntfy.sh/my-secret-topic   (or self-hosted)
    JARVIS_GOTIFY_URL   e.g. https://push.example.com
    JARVIS_GOTIFY_TOKEN app token (Gotify requires one)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from tools.schema import ToolResult

logger = logging.getLogger("jarvis.tools.notify")

MAX_TITLE = 120
MAX_MESSAGE = 2000
PRIORITIES = {"min", "low", "default", "high", "urgent", "1", "2", "3", "4", "5"}


def send_notification(args: dict[str, Any]) -> ToolResult:
    """Send a push notification via ntfy (topic URL) or Gotify (server+token)."""
    message = str(args.get("message", "")).strip()
    if not message:
        return ToolResult(success=False, error="message is required")
    message = message[:MAX_MESSAGE]
    title = str(args.get("title", "JARVIS")).strip()[:MAX_TITLE]
    priority = str(args.get("priority", "default")).lower()
    if priority not in PRIORITIES:
        priority = "default"
    tags = args.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    tags = [str(t)[:32] for t in tags][:5]

    ntfy_url = str(args.get("ntfy_url") or os.environ.get("JARVIS_NTFY_URL", "")).strip()
    gotify_url = str(args.get("gotify_url") or os.environ.get("JARVIS_GOTIFY_URL", "")).strip()
    gotify_token = str(args.get("gotify_token") or os.environ.get("JARVIS_GOTIFY_TOKEN", "")).strip()

    if not ntfy_url and not (gotify_url and gotify_token):
        return ToolResult(
            success=False,
            error=(
                "No notification target configured. Set JARVIS_NTFY_URL "
                "(https://ntfy.sh/<your-topic>) or JARVIS_GOTIFY_URL + "
                "JARVIS_GOTIFY_TOKEN in the environment."
            ),
        )

    results: list[str] = []
    ok = False

    if ntfy_url:
        try:
            ok |= _send_ntfy(ntfy_url, title, message, priority, tags)
            results.append("ntfy: sent")
        except Exception as e:  # noqa: BLE001
            logger.debug("ntfy send failed: %s", e)
            results.append(f"ntfy: failed ({e})")

    if gotify_url and gotify_token:
        try:
            ok |= _send_gotify(gotify_url, gotify_token, title, message, priority)
            results.append("gotify: sent")
        except Exception as e:  # noqa: BLE001
            logger.debug("gotify send failed: %s", e)
            results.append(f"gotify: failed ({e})")

    if ok:
        return ToolResult(success=True, output="; ".join(results), metadata={"targets": results})
    return ToolResult(success=False, error="; ".join(results) or "No notification target succeeded.")


def _send_ntfy(url: str, title: str, message: str, priority: str, tags: list[str]) -> bool:
    """POST to ntfy's simple HTTP API (https://docs.ntfy.sh/publish/)."""
    from core.http_pool import get_client

    client = get_client()
    headers = {
        "Title": title,
        "Priority": priority if not priority.isdigit() else priority,
        "Tags": ",".join(tags),
    }
    resp = client.post(url, content=message.encode("utf-8"), headers=headers, timeout=10.0)
    if resp.status_code in (200, 202):
        return True
    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:120]}")


def _send_gotify(url: str, token: str, title: str, message: str, priority: str) -> bool:
    """POST to Gotify's /message endpoint (priority 0-10)."""
    from core.http_pool import get_client

    prio = {"min": 1, "low": 3, "default": 5, "high": 8, "urgent": 10}.get(priority, 5)
    if priority.isdigit():
        prio = min(max(int(priority), 0), 10)
    base = url.rstrip("/")
    client = get_client()
    resp = client.post(
        f"{base}/message?token={token}",
        json={"title": title, "message": message, "priority": prio},
        headers={"X-Gotify-Key": token},
        timeout=10.0,
    )
    if resp.status_code in (200, 201):
        return True
    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:120]}")


__all__ = ["send_notification"]
