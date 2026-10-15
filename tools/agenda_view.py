"""Agenda view — calendar awareness from iCalendar (.ics) sources.

Derived from the Leon/sukeesh scheduling gap: an assistant that answers
"what's on my plate this week" without a cloud calendar dependency. Reads
standard ICS files — local files inside the workspace or subscribed URLs via
the shared pooled HTTP client (Google Calendar / Outlook / ICS exporters all
publish this format).

Scope is deliberately minimal and honest:

* Parses VEVENT blocks: DTSTART/DTEND (or DURATION), SUMMARY, LOCATION,
  DESCRIPTION, UID. DATE values are all-day events.
* Recurrence: expands FREQ=DAILY/WEEKLY/MONTHLY with INTERVAL/COUNT/UNTIL
  within the view window. Complex rules (BYDAY, BYMONTHDAY, …) fall back to
  the base occurrence — nothing is invented.
* Root-safe: local paths must resolve inside the project root; URLs go through
  the pooled client; every fetch/parse failure degrades to a skipped source.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from tools.schema import ToolResult

logger = logging.getLogger(__name__)

_MAX_SOURCES = 12
_MAX_ICS_BYTES = 2 * 1024 * 1024
_MAX_EVENTS = 500
_MAX_RRULE_OCCURRENCES = 366
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}

_RECUR_SIMPLE = re.compile(
    r"FREQ=(DAILY|WEEKLY|MONTHLY)", re.IGNORECASE
)


# ── Source registry (same pattern as topic_watch) ────────────────────────────

def _state_path() -> Path:
    from core.project import ProjectContext

    return ProjectContext.discover().root_path / "memory" / "calendar_sources.json"


def _load_sources() -> dict[str, str]:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_sources(sources: dict[str, str]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sources, indent=2, ensure_ascii=False), encoding="utf-8")


# ── ICS parsing ──────────────────────────────────────────────────────────────

def _unfold(raw: str) -> list[str]:
    """RFC 5545 line unfolding: a line starting with space/tab continues the previous one."""
    lines: list[str] = []
    for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def _unescape(value: str) -> str:
    return (
        value.replace("\\n", "\n").replace("\\N", "\n")
        .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
    )


def _parse_ics_dt(value: str, params: dict[str, str]) -> tuple[datetime, bool] | None:
    """Parse an iCalendar date-time. Returns (local_naive_datetime, is_all_day)."""
    value = value.strip()
    if params.get("VALUE", "").upper() == "DATE" or (len(value) == 8 and value.isdigit()):
        try:
            return datetime.strptime(value, "%Y%m%d"), True
        except ValueError:
            return None
    tz = params.get("TZID")
    if value.endswith("Z"):
        value = value[:-1]
        tz = "UTC"
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            dt = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if tz == "UTC":
            dt = dt.replace(tzinfo=__import__("datetime").timezone.utc).astimezone()
        # TZID or naive → treat as local wall time (documented limitation)
        return dt.replace(tzinfo=None, microsecond=0) if dt.tzinfo is None else dt.replace(tzinfo=None), False
    return None


def _parse_events(ics_text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in _unfold(ics_text):
        line = line.strip()
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current and current.get("start"):
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        head, _, value = line.partition(":")
        parts = head.split(";")
        name = parts[0].upper()
        params: dict[str, str] = {}
        for p in parts[1:]:
            k, _, v = p.partition("=")
            params[k.upper()] = v
        if name == "DTSTART":
            parsed = _parse_ics_dt(value, params)
            if parsed:
                current["start"], current["all_day"] = parsed
        elif name in ("DTEND", "DURATION") and current.get("start"):
            if name == "DTEND":
                parsed = _parse_ics_dt(value, params)
                if parsed:
                    current["end"] = parsed[0]
            else:
                current["duration"] = value
        elif name == "SUMMARY":
            current["summary"] = _unescape(value)
        elif name == "LOCATION":
            current["location"] = _unescape(value)
        elif name == "DESCRIPTION":
            current["description"] = _unescape(value)[:200]
        elif name == "UID":
            current["uid"] = value
        elif name == "RRULE":
            current["rrule"] = value
    return events


def _expand_rrule(event: dict[str, Any], win_start: datetime, win_end: datetime) -> list[datetime]:
    """Expand simple recurrence within the window; complex rules → base only."""
    rule = event.get("rrule", "")
    base: datetime = event["start"]
    if not rule or not _RECUR_SIMPLE.search(rule):
        return [base] if win_start <= base <= win_end else []
    freq = _RECUR_SIMPLE.search(rule).group(1).upper()  # type: ignore[union-attr]
    step = 1
    m = re.search(r"INTERVAL=(\d+)", rule, re.IGNORECASE)
    if m:
        step = max(1, int(m.group(1)))
    count = None
    m = re.search(r"COUNT=(\d+)", rule, re.IGNORECASE)
    if m:
        count = int(m.group(1))
    until: datetime | None = None
    m = re.search(r"UNTIL=([0-9TZ]+)", rule, re.IGNORECASE)
    if m:
        parsed = _parse_ics_dt(m.group(1).rstrip("Zz"), {})
        until = parsed[0] if parsed else None
    delta = {"DAILY": timedelta(days=step), "WEEKLY": timedelta(weeks=step),
             "MONTHLY": None}[freq]
    out: list[datetime] = []
    occurrence = base
    for i in range(_MAX_RRULE_OCCURRENCES):
        if freq == "MONTHLY":
            month = base.month + i * step
            occurrence = base.replace(year=base.year + (month - 1) // 12, month=(month - 1) % 12 + 1)
        else:
            occurrence = base + delta * i  # type: ignore[operator]
        if until and occurrence > until:
            break
        if count is not None and i >= count:
            break
        if occurrence > win_end:
            break
        if occurrence >= win_start:
            out.append(occurrence)
        if len(out) >= 60:
            break
    return out


# ── Source resolution ────────────────────────────────────────────────────────

def _workspace_root() -> Path:
    from core.project import ProjectContext

    return ProjectContext.discover().root_path


def _read_local_ics(root: Path, raw: str) -> str | None:
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None  # escapes the workspace — refuse
    try:
        text = candidate.read_text(encoding="utf-8", errors="ignore")
        return text[:_MAX_ICS_BYTES] if text else None
    except OSError:
        return None


def _read_url_ics(url: str) -> str | None:
    try:
        from core.http_pool import fetch
    except Exception:
        return None
    try:
        text = fetch(url, timeout=10)
        return str(text)[:_MAX_ICS_BYTES] if text else None
    except Exception as exc:
        logger.debug("agenda: fetch failed for %s: %s", url, exc)
        return None


def _collect_ics_texts(root: Path) -> list[tuple[str, str]]:
    """Registered sources first, then any *.ics found in the workspace."""
    out: list[tuple[str, str]] = []
    for name, source in list(_load_sources().items()):
        if re.match(r"^https?://", source):
            text = _read_url_ics(source)
        else:
            text = _read_local_ics(root, source)
        if text and "BEGIN:VCALENDAR" in text:
            out.append((name, text))
    seen: set[str] = set()
    for path in sorted(root.rglob("*.ics")):
        if len(out) >= _MAX_SOURCES:
            break
        rel = path.relative_to(root)
        if any(part in _SKIP_DIRS for part in rel.parts[:-1]):
            continue
        try:
            if path.stat().st_size > _MAX_ICS_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")[:_MAX_ICS_BYTES]
        except OSError:
            continue
        key = str(rel)
        if key not in seen and "BEGIN:VCALENDAR" in text:
            seen.add(key)
            out.append((key, text))
    return out[:_MAX_SOURCES]


# ── Tool actions ─────────────────────────────────────────────────────────────

def agenda_view(args: dict[str, Any]) -> ToolResult:
    """What's coming up: events from workspace .ics files and subscribed URLs."""
    try:
        days = min(int(args.get("days") or 7), 60)
    except (TypeError, ValueError):
        return ToolResult(success=False, error="days must be an integer")
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    win_start, win_end = today, today + timedelta(days=days)

    root = _workspace_root()
    sources = _collect_ics_texts(root)
    if not sources:
        return ToolResult(
            success=True,
            output="No calendars found. Add one with agenda.view action='add' "
            "(an .ics URL or a workspace file), or drop an .ics file in the workspace.",
        )

    events: list[tuple[datetime, dict[str, Any]]] = []
    errors: list[str] = []
    for _name, text in sources:
        try:
            parsed = _parse_events(text)
        except Exception as exc:  # one bad calendar never blocks the view
            errors.append(str(exc))
            continue
        for ev in parsed[:_MAX_EVENTS]:
            for when in _expand_rrule(ev, win_start, win_end):
                events.append((when, ev))

    events.sort(key=lambda pair: pair[0])
    shown = 0
    lines: list[str] = []
    current_day: str | None = None
    for when, ev in events:
        if shown >= 40:
            break
        if not (win_start <= when <= win_end + timedelta(days=1)):
            continue
        day = when.strftime("%a %b %d")
        if day != current_day:
            lines.append(f"\n{day}")
            current_day = day
        time_part = "all-day" if ev.get("all_day") else when.strftime("%H:%M")
        summary = ev.get("summary") or "(untitled)"
        extra = f" — {ev['location']}" if ev.get("location") else ""
        lines.append(f"  {time_part}  {summary}{extra}")
        shown += 1
    header = f"Agenda for the next {days} day(s):"
    if errors:
        header += f" ({len(errors)} source(s) could not be parsed)"
    if not lines:
        return ToolResult(success=True, output=header + "\n  Nothing scheduled.")
    return ToolResult(success=True, output=header + "\n" + "\n".join(lines).strip())


def agenda_add(args: dict[str, Any]) -> ToolResult:
    source = str(args.get("source") or "").strip()
    if not source:
        return ToolResult(success=False, error="source is required — an .ics URL or a workspace-relative path")
    if not re.match(r"^https?://", source):
        root = _workspace_root()
        resolved = (root / source).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            return ToolResult(success=False, error="path escapes the workspace")
        if not resolved.exists():
            return ToolResult(success=False, error=f"file not found: {source}")
    sources = _load_sources()
    if len(sources) >= _MAX_SOURCES:
        return ToolResult(success=False, error=f"source list is full ({_MAX_SOURCES})")
    sources[source] = source
    _save_sources(sources)
    return ToolResult(success=True, output=f"Calendar source added: {source}")


def agenda_remove(args: dict[str, Any]) -> ToolResult:
    source = str(args.get("source") or "").strip()
    sources = _load_sources()
    if source in sources:
        sources.pop(source)
        _save_sources(sources)
        return ToolResult(success=True, output=f"Removed: {source}")
    return ToolResult(success=False, error=f"not a registered source: {source}")


def agenda_list(args: dict[str, Any]) -> ToolResult:
    sources = _load_sources()
    if not sources:
        return ToolResult(success=True, output="No registered calendar sources (workspace .ics files are still picked up automatically).")
    lines = [f"- {s}" for s in sources]
    return ToolResult(success=True, output="Calendar sources:\n" + "\n".join(lines))
