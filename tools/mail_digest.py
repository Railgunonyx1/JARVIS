"""Mail digest — the notmuch/neomutt-class "what's in my inbox" slice.

Derived from the mail-in-a-terminal school (notmuch, neomutt, mutt-wizard):
an assistant that knows about your inbox should summarize *headers*, never
harvest bodies, and be off entirely unless the user hands it credentials.
This module reads UNSEEN message headers from IMAP over SSL using only the
stdlib, groups them by sender domain, and lists the newest subjects.
No body fetch, no marking as read (read-only EXAMINE), nothing stored.

Configuration (all via environment; never in files):

* ``JARVIS_IMAP_HOST`` — e.g. imap.gmail.com
* ``JARVIS_IMAP_USER`` — login name
* ``JARVIS_IMAP_PASSWORD`` — an app password (never the account password)
* ``JARVIS_IMAP_FOLDER`` — optional, default INBOX
"""

from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from tools.schema import ToolResult

logger = logging.getLogger(__name__)

_MAX_HEADERS = 60
_MAX_SUBJECT = 110


def _decode_header_value(raw: str | None) -> str:
    if not raw:
        return ""
    parts = []
    for text, charset in email.header.decode_header(raw):
        if isinstance(text, bytes):
            try:
                parts.append(text.decode(charset or "utf-8", errors="replace"))
            except LookupError:
                parts.append(text.decode("utf-8", errors="replace"))
        else:
            parts.append(text)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _imap_class():  # isolated for test patching
    return imaplib.IMAP4_SSL


def mail_digest(args: dict[str, Any]) -> ToolResult:
    """Summarize unread mail headers: count by sender, newest subjects. Read-only."""
    host = os.environ.get("JARVIS_IMAP_HOST", "").strip()
    user = os.environ.get("JARVIS_IMAP_USER", "").strip()
    password = os.environ.get("JARVIS_IMAP_PASSWORD", "")
    folder = os.environ.get("JARVIS_IMAP_FOLDER", "").strip() or "INBOX"
    if not host or not user or not password:
        return ToolResult(
            success=False,
            error="mail digest is not configured — set JARVIS_IMAP_HOST, JARVIS_IMAP_USER, "
            "and JARVIS_IMAP_PASSWORD (an app password) in the environment to enable it",
        )
    try:
        days = min(int(args.get("days") or 2), 14)
    except (TypeError, ValueError):
        return ToolResult(success=False, error="days must be an integer")
    limit = min(int(args.get("limit") or 10), 40)

    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    try:
        conn = _imap_class()(host, 993)
        conn.login(user, password)
        conn.select(folder, readonly=True)  # EXAMINE — nothing gets marked as read
        status, data = conn.search(None, f'(UNSEEN SINCE "{since}")')
        if status != "OK":
            return ToolResult(success=False, error="IMAP search failed")
        ids = (data[0] or b"").split()
        if not ids:
            conn.logout()
            return ToolResult(success=True, output=f"No unseen mail in {folder} in the last {days} day(s).")

        messages = []
        for mid in ids[-_MAX_HEADERS:]:
            status, msg_data = conn.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else b""
            msg = email.message_from_bytes(raw)
            from_line = _decode_header_value(msg.get("From"))
            subject = _decode_header_value(msg.get("Subject")) or "(no subject)"
            name, addr = email.utils.parseaddr(from_line)
            messages.append({"name": name or addr, "addr": addr, "subject": subject[:_MAX_SUBJECT]})
        conn.logout()
    except imaplib.IMAP4.error as exc:
        return ToolResult(success=False, error=f"IMAP error: {exc}")
    except OSError as exc:
        return ToolResult(success=False, error=f"could not reach {host}: {exc}")

    if not messages:
        return ToolResult(success=True, output=f"{len(ids)} unseen message(s), headers unreadable.")

    by_domain = Counter(a.partition("@")[2].lower() for m in messages for a in [m["addr"]] if "@" in a)
    domains = ", ".join(f"{d} ({n})" for d, n in by_domain.most_common(6))
    lines = [
        f"{len(messages)} unseen message(s) in {folder} (last {days} day(s)); senders: {domains}",
        "Newest first:",
    ]
    for m in reversed(messages[-limit:]):
        lines.append(f"  - {m['subject']}  — {m['name']}")
    lines.append("(headers only — message bodies are never fetched)")
    return ToolResult(success=True, output="\n".join(lines))


__all__ = ["mail_digest"]
