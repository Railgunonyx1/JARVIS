"""User Model — SQLite-backed preference learning and activity tracking."""

import json
import time
import math
import sqlite3
import logging
import threading
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger("jarvis.personal_intelligence.user_model")

_CONFIDENCE_DECAY_HALF_LIFE = 86400.0 * 7.0
_ROLLING_WINDOW = 86400.0 * 30.0
_DEFAULT_STYLE = "neutral"


@dataclass
class Preference:
    key: str
    value: str
    confidence: float = 0.5
    source: str = "interaction"
    last_updated: float = field(default_factory=time.time)

    def decayed_confidence(self, now: Optional[float] = None) -> float:
        now = now or time.time()
        elapsed = now - self.last_updated
        return self.confidence * math.exp(-0.693 * elapsed / _CONFIDENCE_DECAY_HALF_LIFE)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Preference":
        return cls(
            key=data["key"],
            value=data["value"],
            confidence=data.get("confidence", 0.5),
            source=data.get("source", "interaction"),
            last_updated=data.get("last_updated", 0.0),
        )


@dataclass
class ActivityPattern:
    action: str
    frequency: float = 0.0
    time_of_day: int = -1
    day_of_week: int = -1
    count: int = 0
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "frequency": self.frequency,
            "time_of_day": self.time_of_day,
            "day_of_week": self.day_of_week,
            "count": self.count,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ActivityPattern":
        return cls(
            action=data["action"],
            frequency=data.get("frequency", 0.0),
            time_of_day=data.get("time_of_day", -1),
            day_of_week=data.get("day_of_week", -1),
            count=data.get("count", 0),
            last_seen=data.get("last_seen", 0.0),
        )


@dataclass
class UserProfile:
    name: str = "User"
    timezone: str = "Asia/Kolkata"
    preferences: dict = field(default_factory=dict)
    habits: list = field(default_factory=list)
    communication_style: str = _DEFAULT_STYLE
    activity_patterns: dict = field(default_factory=dict)
    facts: list = field(default_factory=list)


class UserModel:
    def __init__(self, data_dir: Optional[Path] = None):
        self._data_dir = data_dir or Path.home() / ".jarvis" / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "user_model.db"
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._flush_timer: Optional[threading.Timer] = None
        self._dirty = False
        self._profile = UserProfile()
        self._interaction_buffer: list[tuple] = []
        self._init_db()
        self._load_profile()

    def _init_db(self):
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            timeout=10,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA journal_mode = WAL")

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                source TEXT DEFAULT 'interaction',
                last_updated REAL NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS activity_patterns (
                action TEXT PRIMARY KEY,
                frequency REAL DEFAULT 0.0,
                time_of_day INTEGER DEFAULT -1,
                day_of_week INTEGER DEFAULT -1,
                count INTEGER DEFAULT 0,
                last_seen REAL NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                intent TEXT DEFAULT '',
                response TEXT DEFAULT '',
                timestamp REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact TEXT UNIQUE NOT NULL,
                source TEXT DEFAULT 'interaction',
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_interactions_ts ON interactions(timestamp);
        """)
        self._conn.commit()

    def update_from_interaction(self, text: str, intent: str, response: str) -> None:
        now = time.time()
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO interactions (text, intent, response, timestamp) VALUES (?, ?, ?, ?)",
                    (text, intent, response, now),
                )
                self._conn.commit()
        except Exception as e:
            logger.error("Failed to log interaction: %s", e)

        self._extract_preferences_from_text(text, intent)
        self._update_activity_pattern(intent, now)
        self._detect_communication_style(text)

    def _extract_preferences_from_text(self, text: str, intent: str) -> None:
        lower = text.lower()
        preference_signals = [
            ("language", ["prefer", "i like", "i want", "use"], None),
            ("verbosity", ["keep it short", "be brief", "terse", "concise"], "terse"),
            ("verbosity", ["explain in detail", "be thorough", "verbose", "elaborate"], "verbose"),
            ("tone", ["be formal", "formal"], "formal"),
            ("tone", ["be casual", "casual", "relaxed"], "casual"),
            ("tone", ["be professional", "professional"], "professional"),
        ]

        for key, triggers, override_value in preference_signals:
            if any(t in lower for t in triggers):
                value = override_value or text[:120]
                self.set_preference(key, value, confidence=0.6, source="explicit")

        if intent and intent not in ("general.chat", "meta.greet", "meta.howareyou", "meta.thanks", "meta.help"):
            self.set_preference(f"last_intent:{intent}", "used", confidence=0.3, source="implicit")

    def _update_activity_pattern(self, intent: str, now: float) -> None:
        if not intent or intent in ("general.chat", "meta.greet", "meta.howareyou", "meta.thanks", "meta.help"):
            return

        dt = datetime.fromtimestamp(now)
        hour = dt.hour
        dow = dt.weekday()

        with self._lock:
            row = self._conn.execute(
                "SELECT action, frequency, count, last_seen, time_of_day, day_of_week FROM activity_patterns WHERE action = ?",
                (intent,),
            ).fetchone()

            if row:
                new_count = row["count"] + 1
                elapsed = now - row["last_seen"]
                old_freq = row["frequency"]
                new_freq = old_freq * 0.95 + 1.0 / max(elapsed, 1.0) * 0.05 if elapsed > 0 else old_freq + 0.1
                self._conn.execute(
                    "UPDATE activity_patterns SET count = ?, frequency = ?, last_seen = ?, time_of_day = ?, day_of_week = ? WHERE action = ?",
                    (new_count, new_freq, now, hour, dow, intent),
                )
            else:
                self._conn.execute(
                    "INSERT INTO activity_patterns (action, frequency, time_of_day, day_of_week, count, last_seen, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (intent, 0.1, hour, dow, 1, now, now),
                )
            self._conn.commit()

    def _detect_communication_style(self, text: str) -> None:
        words = text.split()
        word_count = len(words)
        has_question = "?" in text
        has_please = "please" in text.lower()

        if word_count <= 4:
            style = "terse"
        elif word_count >= 20 and has_question:
            style = "detailed"
        elif has_please or word_count >= 10:
            style = "polite"
        else:
            style = "neutral"

        if self._profile.communication_style != style:
            self._profile.communication_style = style
            self._mark_dirty()

    def set_preference(self, key: str, value: str, confidence: float = 0.5, source: str = "interaction") -> None:
        now = time.time()
        with self._lock:
            existing = self._conn.execute(
                "SELECT confidence, last_updated FROM preferences WHERE key = ?", (key,)
            ).fetchone()

            if existing:
                old_conf = existing["confidence"]
                new_conf = max(confidence, old_conf * 0.9 + confidence * 0.1)
                self._conn.execute(
                    "UPDATE preferences SET value = ?, confidence = ?, source = ?, last_updated = ? WHERE key = ?",
                    (value, min(new_conf, 1.0), source, now, key),
                )
            else:
                self._conn.execute(
                    "INSERT INTO preferences (key, value, confidence, source, last_updated, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (key, value, confidence, source, now, now),
                )
            self._conn.commit()

        pref = Preference(key=key, value=value, confidence=confidence, source=source, last_updated=now)
        self._profile.preferences[key] = pref.to_dict()

    def get_preference(self, key: str) -> Optional[Preference]:
        with self._lock:
            row = self._conn.execute(
                "SELECT key, value, confidence, source, last_updated FROM preferences WHERE key = ?", (key,)
            ).fetchone()
        if row:
            pref = Preference(
                key=row["key"],
                value=row["value"],
                confidence=row["confidence"],
                source=row["source"],
                last_updated=row["last_updated"],
            )
            if pref.decayed_confidence() < 0.05:
                return None
            return pref
        return None

    def get_style_for_context(self, context: str = "") -> str:
        hour = datetime.now().hour

        tone_pref = self.get_preference("tone")
        if tone_pref and tone_pref.decayed_confidence() > 0.2:
            return tone_pref.value

        if 0 <= hour < 7:
            return "quiet"
        elif 7 <= hour < 12:
            return "energetic"
        elif 12 <= hour < 17:
            return "focused"
        elif 17 <= hour < 21:
            return "relaxed"
        else:
            return "quiet"

    def get_active_hours(self) -> list[int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT time_of_day, COUNT(*) as cnt FROM activity_patterns "
                "WHERE time_of_day >= 0 GROUP BY time_of_day ORDER BY cnt DESC"
            ).fetchall()
        return [row["time_of_day"] for row in rows]

    def get_frequent_actions(self, limit: int = 10) -> list[tuple[str, int]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT action, count FROM activity_patterns ORDER BY count DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [(row["action"], row["count"]) for row in rows]

    def get_all_preferences(self) -> dict[str, Preference]:
        now = time.time()
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, value, confidence, source, last_updated FROM preferences"
            ).fetchall()
        result = {}
        for row in rows:
            pref = Preference(
                key=row["key"],
                value=row["value"],
                confidence=row["confidence"],
                source=row["source"],
                last_updated=row["last_updated"],
            )
            if pref.decayed_confidence(now) >= 0.05:
                result[row["key"]] = pref
        return result

    def get_interaction_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) as cnt FROM interactions").fetchone()
        return row["cnt"] if row else 0

    def add_fact(self, fact: str, source: str = "interaction") -> None:
        now = time.time()
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT OR IGNORE INTO facts (fact, source, created_at) VALUES (?, ?, ?)",
                    (fact, source, now),
                )
                self._conn.commit()
        except Exception as e:
            logger.error("Failed to add fact: %s", e)
        if fact not in self._profile.facts:
            self._profile.facts.append(fact)

    def get_facts(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT fact FROM facts ORDER BY created_at DESC").fetchall()
        return [row["fact"] for row in rows]

    def export_profile(self) -> dict:
        prefs = {}
        for k, v in self.get_all_preferences().items():
            prefs[k] = v.to_dict()

        patterns = {}
        with self._lock:
            rows = self._conn.execute(
                "SELECT action, frequency, time_of_day, day_of_week, count, last_seen FROM activity_patterns"
            ).fetchall()
        for row in rows:
            ap = ActivityPattern(
                action=row["action"],
                frequency=row["frequency"],
                time_of_day=row["time_of_day"],
                day_of_week=row["day_of_week"],
                count=row["count"],
                last_seen=row["last_seen"],
            )
            patterns[row["action"]] = ap.to_dict()

        return {
            "name": self._profile.name,
            "timezone": self._profile.timezone,
            "preferences": prefs,
            "habits": self._profile.habits,
            "communication_style": self._profile.communication_style,
            "activity_patterns": patterns,
            "facts": self.get_facts(),
            "exported_at": time.time(),
        }

    def import_profile(self, data: dict) -> None:
        if not isinstance(data, dict):
            return

        self._profile.name = data.get("name", self._profile.name)
        self._profile.timezone = data.get("timezone", self._profile.timezone)
        self._profile.habits = data.get("habits", self._profile.habits)
        self._profile.communication_style = data.get("communication_style", self._profile.communication_style)

        for key, pref_data in data.get("preferences", {}).items():
            if isinstance(pref_data, dict):
                self.set_preference(
                    key=key,
                    value=pref_data.get("value", ""),
                    confidence=pref_data.get("confidence", 0.5),
                    source=pref_data.get("source", "import"),
                )

        now = time.time()
        for action, pattern_data in data.get("activity_patterns", {}).items():
            if isinstance(pattern_data, dict):
                with self._lock:
                    self._conn.execute(
                        "INSERT OR REPLACE INTO activity_patterns (action, frequency, time_of_day, day_of_week, count, last_seen, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            action,
                            pattern_data.get("frequency", 0.0),
                            pattern_data.get("time_of_day", -1),
                            pattern_data.get("day_of_week", -1),
                            pattern_data.get("count", 0),
                            pattern_data.get("last_seen", now),
                            now,
                        ),
                    )
                    self._conn.commit()

        for fact in data.get("facts", []):
            if isinstance(fact, str) and fact:
                self.add_fact(fact, source="import")

        logger.info("Profile imported: %s", self._profile.name)

    def decay_all_preferences(self) -> int:
        now = time.time()
        decayed = 0
        with self._lock:
            rows = self._conn.execute("SELECT key, confidence, last_updated FROM preferences").fetchall()
            for row in rows:
                elapsed = now - row["last_updated"]
                decayed_conf = row["confidence"] * math.exp(-0.693 * elapsed / _CONFIDENCE_DECAY_HALF_LIFE)
                if decayed_conf < 0.05:
                    self._conn.execute("DELETE FROM preferences WHERE key = ?", (row["key"],))
                    decayed += 1
                elif decayed_conf < row["confidence"] * 0.5:
                    self._conn.execute(
                        "UPDATE preferences SET confidence = ? WHERE key = ?",
                        (decayed_conf, row["key"]),
                    )
            self._conn.commit()
        if decayed:
            logger.info("Decayed %d low-confidence preferences", decayed)
        return decayed

    def prune_old_interactions(self, max_age_days: int = 90) -> int:
        cutoff = time.time() - (max_age_days * 86400)
        with self._lock:
            cursor = self._conn.execute("DELETE FROM interactions WHERE timestamp < ?", (cutoff,))
            deleted = cursor.rowcount
            self._conn.commit()
        return deleted

    def _mark_dirty(self) -> None:
        self._dirty = True
        with self._flush_lock:
            if self._flush_timer and self._flush_timer.is_alive():
                return
            self._flush_timer = threading.Timer(30.0, self._flush_to_disk)
            self._flush_timer.daemon = True
            self._flush_timer.start()

    def _flush_to_disk(self) -> None:
        if not self._dirty:
            return
        with self._flush_lock:
            try:
                profile_path = self._data_dir / "user_model_profile.json"
                profile_path.write_text(json.dumps({
                    "name": self._profile.name,
                    "timezone": self._profile.timezone,
                    "habits": self._profile.habits,
                    "communication_style": self._profile.communication_style,
                    "facts": self._profile.facts,
                }, indent=2, ensure_ascii=False), encoding="utf-8")
                self._dirty = False
            except Exception as e:
                logger.error("Profile flush failed: %s", e)

    def _load_profile(self) -> None:
        profile_path = self._data_dir / "user_model_profile.json"
        if profile_path.exists():
            try:
                data = json.loads(profile_path.read_text(encoding="utf-8"))
                self._profile.name = data.get("name", self._profile.name)
                self._profile.timezone = data.get("timezone", self._profile.timezone)
                self._profile.habits = data.get("habits", [])
                self._profile.communication_style = data.get("communication_style", _DEFAULT_STYLE)
                self._profile.facts = data.get("facts", [])
            except Exception as e:
                logger.error("Profile load failed: %s", e)

    def flush(self) -> None:
        self._flush_to_disk()

    def close(self) -> None:
        self.flush()
        if self._flush_timer and self._flush_timer.is_alive():
            self._flush_timer.cancel()
        if self._conn:
            self._conn.close()
