"""Project knowledge — per-project facts injected into the context (Claude Mem).

The agent-level analogue of CLAUDE.md: a per-project key/value store plus an
auto-importer that ingests existing project docs (CLAUDE.md, AGENTS.md,
JARVIS.md, docs/AGENTS.md). The context builder injects the formatted
knowledge into the system prompt within the Headroom memory budget.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path

from core.context.selector import score as _lexical_score

logger = logging.getLogger("jarvis.memory.knowledge")

_instance: ProjectKnowledge | None = None
_instance_lock = threading.Lock()

_DOC_CANDIDATES = [
    "CLAUDE.md",
    "AGENTS.md",
    "JARVIS.md",
    "docs/CLAUDE.md",
    "docs/AGENTS.md",
    "docs/JARVIS.md",
]
_MAX_DOC_CHARS = 8000


class ProjectKnowledge:
    """SQLite-backed per-project knowledge store."""

    def __init__(self, data_dir: Path | None = None):
        self._data_dir = data_dir or (Path.home() / ".jarvis" / "data")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "project_knowledge.db"
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS project_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project TEXT NOT NULL,
                key TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'note',
                updated_at REAL NOT NULL,
                UNIQUE(project, key)
            );
            CREATE INDEX IF NOT EXISTS idx_knowledge_project ON project_knowledge(project);
        """)
        self._conn.commit()

    def set(self, project: str, key: str, content: str, category: str = "note") -> None:
        """Upsert a knowledge entry for a project."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO project_knowledge (project, key, content, category, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(project, key) DO UPDATE SET
                       content = excluded.content,
                       category = excluded.category,
                       updated_at = excluded.updated_at""",
                (project, key, content[:4000], category, time.time()),
            )
            self._conn.commit()

    def get(self, project: str, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT content FROM project_knowledge WHERE project = ? AND key = ?",
                (project, key),
            ).fetchone()
        return row["content"] if row else None

    def forget(self, project: str, key: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM project_knowledge WHERE project = ? AND key = ?",
                (project, key),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def all(self, project: str) -> list[dict]:
        with self._lock:
            rows = [dict(r) for r in self._conn.execute(
                "SELECT key, content, category, updated_at FROM project_knowledge "
                "WHERE project = ? ORDER BY updated_at ASC", (project,),
            ).fetchall()]
        return rows

    def search(self, project: str, query: str = "", limit: int = 5) -> list[dict]:
        rows = self.all(project)
        if not rows:
            return []
        if not query:
            return rows[:limit]
        scored = [
            (_lexical_score(f"{r['key']} {r['content']}", query), r) for r in rows
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [r for s, r in scored if s > 0.0][:limit]

    def import_docs(self, project: str, root_path: Path) -> int:
        """Ingest standard project docs under their filename as keys."""
        imported = 0
        root = Path(root_path)
        for rel in _DOC_CANDIDATES:
            candidate = root / rel
            if not candidate.is_file():
                continue
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            text = text.strip()[: _MAX_DOC_CHARS]
            if not text:
                continue
            self.set(project, f"doc:{rel}", text, category="project_doc")
            imported += 1
        return imported

    def format_for_prompt(self, project: str, max_tokens: int = 15_000) -> str:
        """Render knowledge for prompt injection, bounded by the token budget."""
        rows = self.all(project)
        if not rows:
            return ""
        lines = []
        for row in rows:
            prefix = row["key"]
            content = row["content"].strip()
            if len(content) > 500:
                content = content[:500] + "..."
            lines.append(f"- {prefix}: {content}")
        text = "[PROJECT KNOWLEDGE]\n" + "\n".join(lines)
        budget_chars = max(80, max_tokens * 4)
        if len(text) > budget_chars:
            text = text[: budget_chars] + "\n"
        return text

    def get_stats(self) -> dict[str, int]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) AS c FROM project_knowledge").fetchone()["c"]
        return {"knowledge": total}

    def close(self) -> None:
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
        global _instance
        if _instance is self:
            _instance = None


def get_project_knowledge() -> ProjectKnowledge:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ProjectKnowledge()
    return _instance
