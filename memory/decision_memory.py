"""Decision memory — records what JARVIS decided and why (Claude Mem).

Every finished task stores the goal, the decision taken (completed/failed),
the rationale, and the outcome so future runs can avoid re-trying known
dead-ends or re-discovering established facts. Recall is scoped per project
and ranked by lexical relevance to the current goal via the Headroom
selector so the injected context earns its tokens.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from core.context.selector import score as _lexical_score

logger = logging.getLogger("jarvis.memory.decisions")

_instance: DecisionMemory | None = None
_instance_lock = threading.Lock()


class DecisionMemory:
    """SQLite-backed store of agent decisions with project scoping."""

    def __init__(self, data_dir: Path | None = None):
        self._data_dir = data_dir or (Path.home() / ".jarvis" / "data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "decisions.db"
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL DEFAULT '',
                goal TEXT NOT NULL,
                decision TEXT NOT NULL,
                rationale TEXT DEFAULT '',
                outcome TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_dec_project ON decisions(project);
            CREATE INDEX IF NOT EXISTS idx_dec_created ON decisions(created_at);
        """)
        self._conn.commit()

    def record(
        self,
        goal: str,
        decision: str,
        rationale: str = "",
        outcome: str = "",
        project: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Persist a decision; returns the row id."""
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO decisions (project, goal, decision, rationale, outcome, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (project or "", (goal or "")[:500], (decision or "")[:200],
                 (rationale or "")[:1000], (outcome or "")[:1000],
                 json.dumps(metadata or {}, default=str), time.time()),
            )
            self._conn.commit()
        logger.info("Decision recorded: %s — %s", decision[:40], (goal or "")[:60])
        return cur.lastrowid

    def recall(
        self,
        project: str = "",
        query: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Most relevant decisions for a project, optionally ranked by query."""
        sql = "SELECT * FROM decisions"
        params: list = []
        if project:
            sql += " WHERE project = ?"
            params.append(project)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(limit * 4, 50))
        with self._lock:
            rows = [dict(r) for r in self._conn.execute(sql, params).fetchall()]

        if not query:
            return rows[:limit]
        scored = [
            (_lexical_score(f"{r['goal']} {r['decision']} {r['rationale']}", query), r)
            for r in rows
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [r for s, r in scored if s > 0.0][:limit]

    def recent(self, project: str = "", limit: int = 5) -> list[dict[str, Any]]:
        return self.recall(project=project, query="", limit=limit)

    def get_stats(self) -> dict[str, int]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) AS c FROM decisions").fetchone()["c"]
        return {"decisions": total}

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None


def get_decision_memory() -> DecisionMemory:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DecisionMemory()
    return _instance
