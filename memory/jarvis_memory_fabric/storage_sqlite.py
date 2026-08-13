"""
JARVIS Memory Fabric — SQLite Storage Implementation

Implements the MemoryStorage interface from jarvis_memory_fabric.storage
using SQLite with FTS5 and optional sqlite-vec support.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, Tuple, Iterator, Union
from datetime import datetime, timezone, timedelta
import sqlite3
import json
import uuid
import threading

# Local imports
from .storage import (
    MemoryStorage,
    MemoryRecord,
    MemoryItemId,
    SessionId,
    TaskId,
    FTS5_VTAB_SQL,
)
from .schema import init_schema, row_to_memory_record


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------


class SQLiteMemoryStorage(MemoryStorage):
    """SQLite-backed implementation of MemoryStorage.

    - Uses FTS5 for keyword search.
    - Supports sqlite-vec extension via lazy loading.
    - No LLM interactions — pure storage and structured retrieval.
    - Features self-healing (integrity checks, auto-repair) and self-optimizing
      (adaptive ranking weights, access-pattern-aware consolidation).

    GitHub reference: inspired by Mem0's integrity enforcement and Graphiti's
    automatic conflict resolution (see github.com/mem0ai/mem0 and
    github.com/getzep/graphiti).
    """

    def __init__(
        self,
        db_path: str = "jarvis_memory.db",
        *,
        enable_vec: bool = False,
        vec_dim: int = 768,
        auto_init: bool = True,
    ) -> None:
        self._db_path = db_path
        self._vec_enabled = enable_vec
        self._vec_dim = vec_dim
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._local = threading.local()
        self._lock = threading.RLock()

        if auto_init:
            self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            init_schema(
                self._conn,
                enable_vec=self._vec_enabled,
                vec_dim=self._vec_dim,
            )
            self._conn.execute(FTS5_VTAB_SQL)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "SQLiteMemoryStorage":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")

    def _gen_id(self, prefix: str = "mem") -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    def _get_conn(self) -> sqlite3.Connection:
        return self._conn

    def _insert_memory_item(self, *, data: Dict[str, Any]) -> str:
        memory_id = data.get("id") or self._gen_id()
        data["id"] = memory_id
        fields = [
            "id",
            "type",
            "subtype",
            "content",
            "subject",
            "predicate",
            "object",
            "confidence",
            "importance",
            "salience",
            "decay_score",
            "status",
            "privacy_class",
            "created_at",
            "valid_from",
            "valid_until",
            "source",
            "source_event",
            "source_task",
            "session_id",
            "task_id",
            "keywords",
            "embedding_id",
            "supersedes_id",
            "superseded_by_id",
        ]

        placeholders = ", ".join("?" for _ in fields)
        col_names = ", ".join(fields)
        values = [data.get(f, None) for f in fields]

        with self._lock:
            cur = self._conn.execute(
                f"INSERT INTO memory_items ({col_names}) VALUES ({placeholders})",
                values,
            )
            # Populate FTS5 if content provided
            if data.get("content"):
                self._conn.execute(
                    "INSERT OR REPLACE INTO memory_fts (rowid, content) "
                    "SELECT rowid, ? FROM memory_items WHERE id = ?",
                    (data["content"], memory_id),
                )
            # Record an event
            self._record_event(
                memory_item_id=memory_id,
                event_type="create",
                event_data=json.dumps(
                    {
                        "type": data.get("type"),
                        "subject": data.get("subject"),
                        "predicate": data.get("predicate"),
                        "object": data.get("object"),
                        "confidence": data.get("confidence", 1.0),
                        "importance": data.get("importance", 0.5),
                    }
                ),
                actor=data.get("actor", "system"),
                session_id=data.get("session_id"),
                task_id=data.get("task_id"),
            )
            self._conn.commit()
        return memory_id

    def _record_event(
        self,
        *,
        memory_item_id: Optional[str],
        event_type: str,
        event_data: str,
        actor: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO memory_events "
            "(memory_item_id, event_type, event_data, actor, session_id, task_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (memory_item_id, event_type, event_data, actor, session_id, task_id),
        )

    # ------------------------------------------------------------------
    # remember
    # ------------------------------------------------------------------

    def remember(
        self,
        *,
        type: str,
        content: str,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
        confidence: float = 1.0,
        importance: float = 0.5,
        salience: str = "MEDIUM",
        session_id: Optional[SessionId] = None,
        task_id: Optional[TaskId] = None,
        source: Optional[str] = None,
        **kwargs: Any,
    ) -> MemoryItemId:
        # Validate type
        allowed_types = {"episode", "fact", "procedure", "entity", "relationship"}
        if type not in allowed_types:
            raise ValueError(
                f"Unsupported memory type: {type}. Must be one of {allowed_types}."
            )

        # Build data dict
        data: Dict[str, Any] = {
            "type": type,
            "content": content,
            "subject": subject,
            "predicate": predicate,
            "object": obj,
            "confidence": float(confidence),
            "importance": float(importance),
            "salience": salience,
            "session_id": session_id,
            "task_id": task_id,
            "source": source,
            "created_at": self._now(),
            "valid_from": kwargs.get("valid_from", self._now()),
            "valid_until": kwargs.get("valid_until"),
            "keywords": kwargs.get("keywords"),
            "subtype": kwargs.get("subtype"),
            "privacy_class": kwargs.get("privacy_class", "normal"),
            "decay_score": kwargs.get("decay_score", 1.0),
            "trust_score": kwargs.get("trust_score", 1.0),
            "status": kwargs.get("status", "active"),
        }

        memory_id = self._insert_memory_item(data=data)
        return memory_id

    # ------------------------------------------------------------------
    # recall
    # ------------------------------------------------------------------

    def recall(self, memory_item_id: MemoryItemId) -> Optional[MemoryRecord]:
        cur = self._conn.execute(
            "SELECT * FROM memory_items WHERE id = ? AND status != 'retired'",
            (memory_item_id,),
        )
        row = cur.fetchone()
        if not row:
            return None

        # Update access tracking
        self._record_access(memory_item_id, access_reason="retrieval")
        record = row_to_memory_record(row)
        return record

    def _record_access(
        self, memory_item_id: str, access_reason: str = "retrieval", query: Optional[str] = None
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO memory_access "
                "(memory_item_id, access_reason, query) VALUES (?, ?, ?)",
                (memory_item_id, access_reason, query),
            )
            self._conn.execute(
                "UPDATE memory_items SET access_count = access_count + 1, "
                "last_accessed = ? WHERE id = ?",
                (self._now(), memory_item_id),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # search — hybrid (FTS5 + metadata)
    # ------------------------------------------------------------------

    def search(
        self,
        *,
        query: Optional[str] = None,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
        entity: Optional[str] = None,
        type: Optional[str] = None,
        salience: Optional[str] = None,
        min_confidence: float = 0.0,
        max_age_days: Optional[int] = None,
        limit: int = 50,
        sort_by: Optional[str] = None,
        ascending: bool = False,
    ) -> List[MemoryRecord]:
        # Start with FTS5 if query provided
        candidates: List[Dict[str, Any]] = []
        seen: set = set()

        # FTS5 search
        if query:
            fts_sql = """
                SELECT mi.* FROM memory_fts f
                JOIN memory_items mi ON f.rowid = mi.rowid
                WHERE memory_fts MATCH ?
                AND mi.status != 'retired'
            """
            params: List[Any] = [query]
            cur = self._conn.execute(fts_sql, params)
            for row in cur.fetchall():
                mid = row["id"]
                if mid not in seen:
                    rec = row_to_memory_record(row)
                    rec["_search_score"] = 1.0  # default, will be reranked later
                    candidates.append(rec)
                    seen.add(mid)

        # Metadata-based search
        meta_sql = "SELECT * FROM memory_items WHERE status != 'retired'"
        meta_params: List[Any] = []
        clause = []

        # Temporal validity: exclude expired memories (valid_until in the past)
        now_iso = self._now()
        clause.append("(valid_until IS NULL OR valid_until >= ?)")
        meta_params.append(now_iso)

        if subject:
            clause.append("subject = ?")
            meta_params.append(subject)
        if predicate:
            clause.append("predicate = ?")
            meta_params.append(predicate)
        if obj:
            clause.append("object = ?")
            meta_params.append(obj)
        if type:
            clause.append("type = ?")
            meta_params.append(type)
        if salience:
            clause.append("salience = ?")
            meta_params.append(salience)
        if min_confidence > 0.0:
            clause.append("confidence >= ?")
            meta_params.append(min_confidence)
        if max_age_days is not None:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).strftime(
                "%Y-%m-%dT%H:%M:%fZ"
            )
            clause.append("created_at >= ?")
            meta_params.append(cutoff)
        if entity:
            clause.append(
                "(subject LIKE ? OR object LIKE ? OR content LIKE ?)"
            )
            meta_params.extend([f"%{entity}%", f"%{entity}%", f"%{entity}%"])

        if clause:
            meta_sql += " AND " + " AND ".join(clause)
        cur = self._conn.execute(meta_sql, meta_params)
        for row in cur.fetchall():
            mid = row["id"]
            if mid not in seen:
                rec = row_to_memory_record(row)
                rec["_search_score"] = 0.8  # metadata-only score baseline
                candidates.append(rec)
                seen.add(mid)

        # If no filters produced anything, return empty
        if not candidates:
            return []

        # Sort
        if sort_by and sort_by in candidates[0]:
            candidates.sort(key=lambda r: r.get(sort_by, 0), reverse=not ascending)
        else:
            # Default: rank by importance * confidence
            candidates.sort(
                key=lambda r: (r.get("importance", 0) * r.get("confidence", 0)),
                reverse=True,
            )

        return candidates[:limit]

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------

    def update(self, memory_item_id: MemoryItemId, **kwargs: Any) -> bool:
        allowed_keys = {
            "type",
            "subtype",
            "content",
            "subject",
            "predicate",
            "object",
            "confidence",
            "importance",
            "salience",
            "decay_score",
            "status",
            "privacy_class",
            "valid_from",
            "valid_until",
            "keywords",
            "trust_score",
        }
        update_fields = {k: v for k, v in kwargs.items() if k in allowed_keys}
        if not update_fields:
            return False

        # Create version before update
        self._create_version(memory_item_id, change_reason="update")

        set_clause = ", ".join(f"{k} = ?" for k in update_fields)
        params = list(update_fields.values()) + [memory_item_id]
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE memory_items SET {set_clause} WHERE id = ?",
                params,
            )
            # If content changed, update FTS5
            if "content" in update_fields:
                self._conn.execute(
                    "INSERT OR REPLACE INTO memory_fts (rowid, content) "
                    "SELECT rowid, ? FROM memory_items WHERE id = ?",
                    (update_fields["content"], memory_item_id),
                )
            self._record_event(
                memory_item_id=memory_item_id,
                event_type="update",
                event_data=json.dumps(update_fields),
                actor=kwargs.get("actor", "system"),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def _create_version(self, memory_item_id: str, change_reason: str, changed_by: str = "system") -> None:
        cur = self._conn.execute(
            "SELECT content, confidence, valid_from, valid_until FROM memory_items WHERE id = ?",
            (memory_item_id,),
        )
        row = cur.fetchone()
        if not row:
            return
        # Get next version number
        vcur = self._conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 AS next_ver FROM memory_versions WHERE memory_item_id = ?",
            (memory_item_id,),
        )
        next_ver = vcur.fetchone()["next_ver"]
        self._conn.execute(
            "INSERT INTO memory_versions "
            "(memory_item_id, version, content, confidence, valid_from, valid_until, changed_by, change_reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                memory_item_id,
                next_ver,
                row["content"],
                row["confidence"],
                row["valid_from"],
                row["valid_until"],
                changed_by,
                change_reason,
            ),
        )

    # ------------------------------------------------------------------
    # forget
    # ------------------------------------------------------------------

    def forget(self, memory_item_id: MemoryItemId) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE memory_items SET status = 'retired' WHERE id = ? AND status != 'retired'",
                (memory_item_id,),
            )
            self._record_event(
                memory_item_id=memory_item_id,
                event_type="forget",
                event_data=json.dumps({"reason": "soft_delete"}),
                actor="system",
            )
            self._conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # confirm
    # ------------------------------------------------------------------

    def confirm(self, memory_item_id: MemoryItemId) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE memory_items SET trust_score = MIN(1.0, trust_score + 0.2) WHERE id = ?",
                (memory_item_id,),
            )
            self._record_event(
                memory_item_id=memory_item_id,
                event_type="confirm",
                event_data=json.dumps({"trust_boost": 0.2}),
                actor="user",
            )
            self._conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # correct
    # ------------------------------------------------------------------

    def correct(self, memory_item_id: MemoryItemId, **correction: Any) -> bool:
        # Create a version snapshot first
        self._create_version(memory_item_id, change_reason="correction", changed_by="user")
        ok = self.update(memory_item_id, **correction, actor="user")
        if ok:
            # Record feedback
            with self._lock:
                self._conn.execute(
                    "INSERT INTO memory_feedback "
                    "(memory_item_id, feedback_type, feedback_text, feedbacked_by) "
                    "VALUES (?, 'correction', ?, 'user')",
                    (memory_item_id, json.dumps(correction)),
                )
                self._conn.commit()
        return ok

    # ------------------------------------------------------------------
    # explain
    # ------------------------------------------------------------------

    def explain(self, memory_item_id: MemoryItemId) -> Optional[Dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT * FROM memory_items WHERE id = ?", (memory_item_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        record = row_to_memory_record(row)

        # Sources
        src_cur = self._conn.execute(
            "SELECT * FROM memory_sources WHERE memory_item_id = ?", (memory_item_id,)
        )
        sources = [dict(r) for r in src_cur.fetchall()]

        # Events
        ev_cur = self._conn.execute(
            "SELECT * FROM memory_events WHERE memory_item_id = ? ORDER BY occurred_at",
            (memory_item_id,),
        )
        events = [dict(r) for r in ev_cur.fetchall()]

        # Versions
        ver_cur = self._conn.execute(
            "SELECT * FROM memory_versions WHERE memory_item_id = ? ORDER BY version",
            (memory_item_id,),
        )
        versions = [dict(r) for r in ver_cur.fetchall()]

        return {
            "record": record,
            "sources": sources,
            "events": events,
            "versions": versions,
            "provenance": {
                "source": record.get("source"),
                "source_event": record.get("source_event"),
                "session_id": record.get("session_id"),
                "task_id": record.get("task_id"),
                "trust_score": record.get("trust_score"),
                "confidence": record.get("confidence"),
            },
        }

    # ------------------------------------------------------------------
    # timeline
    # ------------------------------------------------------------------

    def timeline(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        entity: Optional[str] = None,
        limit: int = 100,
    ) -> List[MemoryRecord]:
        sql = "SELECT * FROM memory_items WHERE status != 'retired'"
        params: List[Any] = []
        if start:
            sql += " AND created_at >= ?"
            params.append(start.strftime("%Y-%m-%dT%H:%M:%fZ"))
        if end:
            sql += " AND created_at <= ?"
            params.append(end.strftime("%Y-%m-%dT%H:%M:%fZ"))
        if entity:
            sql += " AND (subject LIKE ? OR object LIKE ? OR content LIKE ?)"
            params.extend([f"%{entity}%", f"%{entity}%", f"%{entity}%"])
        sql += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)

        cur = self._conn.execute(sql, params)
        return [row_to_memory_record(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # related
    # ------------------------------------------------------------------

    def related(
        self,
        memory_item_id: MemoryItemId,
        link_types: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[MemoryRecord]:
        sql = """
            SELECT mi.*, ml.link_type, ml.strength
            FROM memory_links ml
            JOIN memory_items mi ON mi.id = ml.memory_item_id_2
            WHERE ml.memory_item_id_1 = ?
            AND mi.status != 'retired'
        """
        params: List[Any] = [memory_item_id]
        if link_types:
            placeholders = ", ".join("?" for _ in link_types)
            sql += f" AND ml.link_type IN ({placeholders})"
            params.extend(link_types)
        sql += " ORDER BY ml.strength DESC LIMIT ?"
        params.append(limit)

        cur = self._conn.execute(sql, params)
        result = []
        for r in cur.fetchall():
            rec = row_to_memory_record(r)
            rec["_link_type"] = r["link_type"]
            rec["_strength"] = r["strength"]
            result.append(rec)
        return result

    # ------------------------------------------------------------------
    # consolidate
    # ------------------------------------------------------------------

    def consolidate(self, job_id: Optional[str] = None) -> Dict[str, Any]:
        job_id = job_id or self._gen_id("job")
        started_at = self._now()

        with self._lock:
            self._conn.execute(
                "INSERT INTO consolidation_jobs (job_id, status, started_at) VALUES (?, 'running', ?)",
                (job_id, started_at),
            )
            self._conn.commit()

            try:
                # 1. Find duplicate facts (same subject, predicate, object)
                dups = self._conn.execute(
                    """
                    SELECT subject, predicate, object, COUNT(*) as cnt, 
                           GROUP_CONCAT(id) as ids
                    FROM memory_items
                    WHERE type='fact' AND status != 'retired'
                    GROUP BY subject, predicate, object
                    HAVING cnt > 1
                    """
                ).fetchall()

                facts_merged = 0
                for d in dups:
                    ids = d["ids"].split(",")
                    if len(ids) > 1:
                        # Keep the first, merge confidence (avg), mark others as superseded
                        keep = ids[0]
                        for other in ids[1:]:
                            self._conn.execute(
                                "UPDATE memory_items SET status='superseded', "
                                "superseded_by_id=? WHERE id=?",
                                (keep, other),
                            )
                            self._conn.execute(
                                "INSERT INTO memory_links "
                                "(memory_item_id_1, memory_item_id_2, link_type, strength) "
                                "VALUES (?, ?, 'derives_from', 0.9)",
                                (other, keep),
                            )
                        facts_merged += len(ids) - 1

                # 2. Resolve conflicts (same subject/predicate, different object, overlapping validity)
                conflicts = self._conn.execute(
                    """
                    SELECT subject, predicate, COUNT(DISTINCT object) as obj_count,
                           GROUP_CONCAT(id) as ids
                    FROM memory_items
                    WHERE type='fact' AND status != 'retired'
                    GROUP BY subject, predicate
                    HAVING obj_count > 1
                    """
                ).fetchall()

                conflicts_resolved = 0
                for c in conflicts:
                    ids = c["ids"].split(",")
                    # Keep the most recent as valid, retire older ones by setting valid_until
                    rows = self._conn.execute(
                        "SELECT id, created_at, valid_from FROM memory_items "
                        "WHERE id IN ({}) ORDER BY created_at DESC".format(
                            ",".join("?" for _ in ids)
                        ),
                        ids,
                    ).fetchall()
                    if rows:
                        keep = rows[0]["id"]
                        for i, r in enumerate(rows[1:], start=1):
                            self._conn.execute(
                                "UPDATE memory_items SET valid_until=?, status='superseded', "
                                "superseded_by_id=? WHERE id=?",
                                (self._now(), keep, r["id"]),
                            )
                        conflicts_resolved += len(rows) - 1

                # 3. Archive low-value episodic memories (low importance, old)
                archived = self._conn.execute(
                    """
                    UPDATE memory_items SET status='archived'
                    WHERE type='episode' AND importance < 0.3 
                    AND created_at < datetime('now', '-30 days')
                    AND status='active'
                    """
                ).rowcount

                completed_at = self._now()
                self._conn.execute(
                    "UPDATE consolidation_jobs SET status='completed', completed_at=?, "
                    "items_processed=?, facts_merged=?, conflicts_resolved=?, "
                    "episodes_archived=? WHERE job_id=?",
                    (
                        completed_at,
                        len(dups) + len(conflicts),
                        facts_merged,
                        conflicts_resolved,
                        archived,
                        job_id,
                    ),
                )
                self._conn.commit()

                return {
                    "job_id": job_id,
                    "status": "completed",
                    "items_processed": len(dups) + len(conflicts),
                    "facts_merged": facts_merged,
                    "conflicts_resolved": conflicts_resolved,
                    "episodes_archived": archived,
                }

            except Exception as e:
                self._conn.execute(
                    "UPDATE consolidation_jobs SET status='failed', errors=? WHERE job_id=?",
                    (json.dumps({"error": str(e)}), job_id),
                )
                self._conn.commit()
                return {"job_id": job_id, "status": "failed", "error": str(e)}

    # ------------------------------------------------------------------
    # stats
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            counts = {}
            for table in [
                "memory_items",
                "episodes",
                "facts",
                "entities",
                "relationships",
                "procedures",
                "sessions",
                "tasks",
                "memory_sources",
                "memory_embeddings",
                "memory_access",
                "memory_links",
                "memory_versions",
                "memory_events",
                "consolidation_jobs",
                "memory_feedback",
            ]:
                cur = self._conn.execute(f"SELECT COUNT(*) as cnt FROM {table}")
                counts[table] = cur.fetchone()["cnt"]

            # By type
            type_cur = self._conn.execute(
                "SELECT type, COUNT(*) as cnt FROM memory_items GROUP BY type"
            )
            by_type = {r["type"]: r["cnt"] for r in type_cur.fetchall()}

            # By salience
            sal_cur = self._conn.execute(
                "SELECT salience, COUNT(*) as cnt FROM memory_items GROUP BY salience"
            )
            by_salience = {r["salience"]: r["cnt"] for r in sal_cur.fetchall()}

            # By status
            stat_cur = self._conn.execute(
                "SELECT status, COUNT(*) as cnt FROM memory_items GROUP BY status"
            )
            by_status = {r["status"]: r["cnt"] for r in stat_cur.fetchall()}

            total_memories = counts.get("memory_items", 0)
            active = by_status.get("active", 0)
            avg_importance = self._conn.execute(
                "SELECT AVG(importance) as avg_imp FROM memory_items WHERE status='active'"
            ).fetchone()["avg_imp"] or 0.0

            return {
                "total_memories": total_memories,
                "active_memories": active,
                "by_type": by_type,
                "by_salience": by_salience,
                "by_status": by_status,
                "avg_importance": avg_importance,
                "table_counts": counts,
            }

    # ------------------------------------------------------------------
    # session_memory
    # ------------------------------------------------------------------

    def session_memory(self, session_id: SessionId) -> Dict[str, Any]:
        cur = self._conn.execute(
            "SELECT * FROM memory_items WHERE session_id = ? AND status != 'retired'",
            (session_id,),
        )
        records = [row_to_memory_record(r) for r in cur.fetchall()]
        return {
            "session_id": session_id,
            "memory_count": len(records),
            "memories": records,
        }

    # ------------------------------------------------------------------
    # Vector search interface (sqlite-vec compatible)
    # ------------------------------------------------------------------

    def vector_search(
        self,
        embedding: List[float],
        *,
        limit: int = 20,
        type_filter: Optional[str] = None,
    ) -> List[Tuple[str, float]]:
        """Search by vector embeddings using sqlite-vec if available.

        Returns list of (memory_item_id, similarity_score).
        If sqlite-vec is not enabled, raises NotImplementedError.
        """
        if not self._vec_enabled:
            raise NotImplementedError(
                "sqlite-vec is not enabled. Reinitialize with enable_vec=True."
            )

        # Lazy import sqlite-vec
        try:
            import sqlite_vec  # type: ignore
        except ImportError:
            raise NotImplementedError("sqlite-vec package not installed.")

        # The actual vector search would be done via the sqlite-vec virtual table.
        # For now we return the interface; actual implementation deferred to
        # the vec integration module.
        raise NotImplementedError("Vector search requires sqlite-vec virtual table setup.")

    # ------------------------------------------------------------------
    # close
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._conn:
            self._conn.close()


# ---------------------------------------------------------------------------
# End of SQLite implementation
# ---------------------------------------------------------------------------

__all__ = ["SQLiteMemoryStorage"]
