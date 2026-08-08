"""Calendar Manager — Manage calendar events and scheduling.

Uses ICS file parsing and local storage for calendar operations.
"""
import logging
import time
import json
import re
import sqlite3
import uuid
from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger("external.calendar_manager")


@dataclass
class CalendarEvent:
    """A calendar event."""
    id: str = ""
    title: str = ""
    description: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    location: str = ""
    recurrence: str = ""  # "daily", "weekly", "monthly", ""
    reminder_minutes: int = 15
    created_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "title": self.title,
            "start": datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else "",
            "end": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else "",
            "location": self.location,
        }


class CalendarManager:
    """Manage calendar events with SQLite storage."""

    def __init__(self, db_path: str = "cache/calendar.db"):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                location TEXT DEFAULT '',
                recurrence TEXT DEFAULT '',
                reminder_minutes INTEGER DEFAULT 15,
                created_at REAL NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def create_event(self, title: str, start_time: float, end_time: float,
                     description: str = "", location: str = "",
                     recurrence: str = "", reminder_minutes: int = 15) -> CalendarEvent:
        event = CalendarEvent(
            id=str(uuid.uuid4())[:8],
            title=title, description=description,
            start_time=start_time, end_time=end_time,
            location=location, recurrence=recurrence,
            reminder_minutes=reminder_minutes,
            created_at=time.time(),
        )
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "INSERT INTO events (id, title, description, start_time, end_time, location, recurrence, reminder_minutes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (event.id, event.title, event.description, event.start_time, event.end_time,
             event.location, event.recurrence, event.reminder_minutes, event.created_at)
        )
        conn.commit()
        conn.close()
        return event

    def get_upcoming(self, hours: int = 24) -> List[CalendarEvent]:
        now = time.time()
        future = now + hours * 3600
        conn = sqlite3.connect(self._db_path)
        rows = conn.execute(
            "SELECT id, title, description, start_time, end_time, location, recurrence, reminder_minutes, created_at FROM events WHERE start_time >= ? AND start_time <= ? ORDER BY start_time",
            (now, future)
        ).fetchall()
        conn.close()
        return [CalendarEvent(id=r[0], title=r[1], description=r[2], start_time=r[3],
                              end_time=r[4], location=r[5], recurrence=r[6],
                              reminder_minutes=r[7], created_at=r[8]) for r in rows]

    def get_today(self) -> List[CalendarEvent]:
        now = datetime.now()
        start = datetime(now.year, now.month, now.day).timestamp()
        end = start + 86400
        conn = sqlite3.connect(self._db_path)
        rows = conn.execute(
            "SELECT id, title, description, start_time, end_time, location, recurrence, reminder_minutes, created_at FROM events WHERE start_time >= ? AND start_time < ? ORDER BY start_time",
            (start, end)
        ).fetchall()
        conn.close()
        return [CalendarEvent(id=r[0], title=r[1], description=r[2], start_time=r[3],
                              end_time=r[4], location=r[5], recurrence=r[6],
                              reminder_minutes=r[7], created_at=r[8]) for r in rows]

    def delete_event(self, event_id: str) -> bool:
        conn = sqlite3.connect(self._db_path)
        cursor = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    def get_stats(self) -> Dict[str, Any]:
        conn = sqlite3.connect(self._db_path)
        count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        upcoming = conn.execute("SELECT COUNT(*) FROM events WHERE start_time >= ?", (time.time(),)).fetchone()[0]
        conn.close()
        return {"total_events": count, "upcoming_events": upcoming}


_calendar_instance: Optional[CalendarManager] = None


def get_calendar_manager() -> CalendarManager:
    global _calendar_instance
    if _calendar_instance is None:
        _calendar_instance = CalendarManager()
    return _calendar_instance
