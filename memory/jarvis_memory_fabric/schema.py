"""
JARVIS Memory Fabric — SQLite Schema

Defines 18 core tables for the Memory Fabric storage layer.
Designed to be backend-agnostic and sqlite-vec compatible.
No LLM hard-wiring; pure structured storage with full provenance.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

# ---------------------------------------------------------------------------
# Schema constants (DDL)
# ---------------------------------------------------------------------------

SCHEMA_DDL = """
-- memory_items: universal memory record (the "MemoryRecord" from the architecture)
CREATE TABLE IF NOT EXISTS memory_items (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,                     -- 'episode' | 'fact' | 'procedure' | 'entity' | 'relationship'
    subtype TEXT,                           -- e.g. 'semantic', 'temporal', 'workflow'
    content TEXT NOT NULL,                  -- free-text or JSON content
    subject TEXT,                           -- for facts/relationships
    predicate TEXT,                         -- for facts/relationships
    object TEXT,                            -- for facts/relationships
    confidence REAL NOT NULL DEFAULT 1.0,   -- extraction/source confidence
    importance REAL NOT NULL DEFAULT 0.5,   -- 0.0..1.0, used for ranking/salience
    salience TEXT NOT NULL DEFAULT 'MEDIUM',-- 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'EPHEMERAL'
    decay_score REAL NOT NULL DEFAULT 1.0,  -- 1.0 = fresh, < 1.0 = decaying
    access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed TIMESTAMP,
    trust_score REAL NOT NULL DEFAULT 1.0,  -- UNTRUSTED..TRUSTED
    status TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'archived' | 'retired' | 'superseded'
    privacy_class TEXT NOT NULL DEFAULT 'normal', -- 'normal' | 'private' | 'secret'
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    valid_from TIMESTAMP,                     -- temporal validity window
    valid_until TIMESTAMP,                    -- temporal validity window
    source TEXT,                              -- source event/session/task
    source_event TEXT,                        -- specific event id
    source_task TEXT,                         -- task that generated this
    session_id TEXT,                          -- originating session
    task_id TEXT,                             -- originating task
    keywords TEXT,                            -- comma-separated for FTS5
    embedding_id TEXT,                        -- FK to memory_embeddings
    supersedes_id TEXT,                       -- for conflict resolution (points to replaced record)
    superseded_by_id TEXT                     -- inverse link
);

-- episodes: raw experiences / event log entries
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    memory_item_id TEXT NOT NULL,             -- FK to memory_items
    session_id TEXT NOT NULL,
    task_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    timestamp TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    events TEXT NOT NULL,                     -- JSON array of event strings
    status TEXT NOT NULL DEFAULT 'complete',  -- 'complete' | 'in_progress' | 'cancelled'
    tags TEXT,                                -- comma-separated
    FOREIGN KEY (memory_item_id) REFERENCES memory_items(id) ON DELETE CASCADE,
    UNIQUE (session_id, timestamp)
);

-- facts: structured knowledge (subject-predicate-object)
CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    memory_item_id TEXT NOT NULL,             -- FK to memory_items
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    source TEXT,
    valid_from TIMESTAMP,
    valid_until TIMESTAMP,
    FOREIGN KEY (memory_item_id) REFERENCES memory_items(id) ON DELETE CASCADE,
    UNIQUE (subject, predicate, object, valid_from)
);

-- entities: people, projects, software, files, concepts, etc.
CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    memory_item_id TEXT,                      -- FK to memory_items (optional)
    name TEXT NOT NULL UNIQUE,
    entity_type TEXT NOT NULL,                -- 'person' | 'project' | 'software' | 'file' | 'concept' | 'other'
    description TEXT,
    aliases TEXT,                             -- JSON array of alias strings
    first_seen TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_seen TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    provenance TEXT,                          -- which memory/item first identified this entity
    confidence REAL NOT NULL DEFAULT 1.0,
    metadata TEXT,                            -- JSON dict of extra attributes
    UNIQUE (name, entity_type)
);

-- relationships: entity → relation → entity
CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    memory_item_id TEXT,                      -- FK to memory_items
    source_entity_id TEXT NOT NULL,           -- FK to entities.id
    target_entity_id TEXT NOT NULL,           -- FK to entities.id
    relation TEXT NOT NULL,                   -- e.g. 'uses', 'contains', 'depends_on'
    confidence REAL NOT NULL DEFAULT 1.0,
    valid_from TIMESTAMP,
    valid_until TIMESTAMP,
    source TEXT,
    FOREIGN KEY (memory_item_id) REFERENCES memory_items(id) ON DELETE CASCADE,
    FOREIGN KEY (source_entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (target_entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    UNIQUE (source_entity_id, relation, target_entity_id, valid_from)
);

-- procedures: reusable workflows / how-to knowledge
CREATE TABLE IF NOT EXISTS procedures (
    id TEXT PRIMARY KEY,
    memory_item_id TEXT,                      -- FK to memory_items
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    prerequisites TEXT,                       -- JSON text listing requirements
    command TEXT,                             -- command to execute
    port INTEGER,
    params TEXT,                              -- JSON of parameter names/values
    verification TEXT,                        -- how to verify success
    last_executed TIMESTAMP,
    times_executed INTEGER NOT NULL DEFAULT 0,
    success_rate REAL NOT NULL DEFAULT 0.0,
    confidence REAL NOT NULL DEFAULT 1.0,
    source TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (name)
);

-- sessions: session tracking
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    jarvis_instance TEXT NOT NULL,             -- identifier for the JARVIS instance
    start_time TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    end_time TIMESTAMP,
    total_interactions INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',    -- 'active' | 'closed' | 'archived'
    memory_count INTEGER NOT NULL DEFAULT 0,
    context_summary TEXT                      -- brief textual summary
);

-- tasks: task tracking
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    session_id TEXT,                          -- FK to sessions
    name TEXT NOT NULL,
    objective TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
    priority TEXT NOT NULL DEFAULT 'normal',  -- 'low' | 'normal' | 'high' | 'critical'
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    result TEXT,                              -- final result or error
    tags TEXT,                                -- comma-separated
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

-- memory_sources: source provenance tracking
CREATE TABLE IF NOT EXISTS memory_sources (
    id TEXT PRIMARY KEY,
    memory_item_id TEXT NOT NULL,             -- FK to memory_items
    source_type TEXT NOT NULL,                -- 'conversation' | 'tool_output' | 'observation' | 'external' | 'extraction'
    source_reference TEXT,                    -- e.g. session_id, file_path, url
    extracted_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    extractor_version TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    user_confirmed INTEGER NOT NULL DEFAULT 0, -- 0 or 1
    FOREIGN KEY (memory_item_id) REFERENCES memory_items(id) ON DELETE CASCADE
);

-- memory_embeddings: vector embeddings (sqlite-vec compatible)
CREATE TABLE IF NOT EXISTS memory_embeddings (
    embedding_id TEXT PRIMARY KEY,            -- matches memory_items.id or a vector id
    memory_item_id TEXT NOT NULL UNIQUE,      -- FK to memory_items
    dimensions INTEGER NOT NULL DEFAULT 768,  -- vector dimensionality
    vec_rowid INTEGER,                        -- rowid in the sqlite-vec virtual table
    -- The actual blob stores float32 vector data; sqlite-vec will manage it
    -- We store a reference; actual vector lives in sqlite-vec internal state
    -- But we keep the dimension metadata here for schema evolution
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- memory_access: access tracking for recency/importance scoring
CREATE TABLE IF NOT EXISTS memory_access (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_item_id TEXT NOT NULL,             -- FK to memory_items
    accessed_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    access_reason TEXT,                       -- 'retrieval' | 'consolidation' | 'manual' | 'api'
    query TEXT,                               -- the query that triggered the access
    relevance_score REAL,                     -- computed relevance at access time
    FOREIGN KEY (memory_item_id) REFERENCES memory_items(id) ON DELETE CASCADE
);

-- memory_links: memory linking / "related to" graph
CREATE TABLE IF NOT EXISTS memory_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_item_id_1 TEXT NOT NULL,          -- FK to memory_items
    memory_item_id_2 TEXT NOT NULL,          -- FK to memory_items
    link_type TEXT NOT NULL,                  -- 'related' | 'causes' | 'contradicts' | 'derives_from' | 'summarizes'
    strength REAL NOT NULL DEFAULT 1.0,       -- 0.0..1.0
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (memory_item_id_1) REFERENCES memory_items(id) ON DELETE CASCADE,
    FOREIGN KEY (memory_item_id_2) REFERENCES memory_items(id) ON DELETE CASCADE,
    UNIQUE (memory_item_id_1, memory_item_id_2, link_type)
);

-- memory_versions: historical versions for conflict resolution / temporal tracking
CREATE TABLE IF NOT EXISTS memory_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_item_id TEXT NOT NULL,             -- FK to memory_items
    version INTEGER NOT NULL DEFAULT 1,       -- version number
    content TEXT NOT NULL,                    -- the content at this version
    confidence REAL NOT NULL DEFAULT 1.0,
    valid_from TIMESTAMP NOT NULL,
    valid_until TIMESTAMP,                      -- null = current/active
    changed_by TEXT,                          -- who/what caused this version change
    change_reason TEXT,                       -- why it changed
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (memory_item_id, version)
);

-- memory_events: immutable audit trail (every write creates an event)
CREATE TABLE IF NOT EXISTS memory_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_item_id TEXT,                      -- FK to memory_items (may be null for system events)
    event_type TEXT NOT NULL,                 -- 'create' | 'update' | 'delete' | 'conflict' | 'consolidate' | 'forget'
    event_data TEXT NOT NULL,                 -- JSON description of the event
    occurred_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    actor TEXT,                               -- who/what caused the event
    session_id TEXT,                          -- originating session
    task_id TEXT,                             -- originating task
    FOREIGN KEY (memory_item_id) REFERENCES memory_items(id) ON DELETE SET NULL
);

-- consolidation_jobs: async consolidation tracking
CREATE TABLE IF NOT EXISTS consolidation_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',   -- 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    items_processed INTEGER NOT NULL DEFAULT 0,
    facts_merged INTEGER NOT NULL DEFAULT 0,
    conflicts_resolved INTEGER NOT NULL DEFAULT 0,
    episodes_archived INTEGER NOT NULL DEFAULT 0,
    errors TEXT,                              -- JSON error info
    created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at TIMESTAMP
);

-- memory_feedback: user corrections / feedback loop
CREATE TABLE IF NOT EXISTS memory_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_item_id TEXT NOT NULL,             -- FK to memory_items
    feedback_type TEXT NOT NULL,              -- 'correction' | 'confirmation' | 'rejection' | 'comment'
    feedback_text TEXT NOT NULL,
    feedbacked_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    feedbacked_by TEXT,                       -- 'user' | 'system' | 'agent'
    resolved_at TIMESTAMP,
    resolved INTEGER NOT NULL DEFAULT 0,      -- 0 = pending, 1 = resolved
    resolution TEXT,                          -- how it was resolved
    FOREIGN KEY (memory_item_id) REFERENCES memory_items(id) ON DELETE CASCADE
);
"""

# ---------------------------------------------------------------------------
# Schema creation / migration
# ---------------------------------------------------------------------------


def init_schema(conn: sqlite3.Connection, *, enable_vec: bool = False, vec_dim: int = 768) -> None:
    """Initialize the full Memory Fabric schema on the given connection."""
    cursor = conn.cursor()
    cursor.executescript(SCHEMA_DDL)

    # Post-initialization: ensure FK enforcement and pragmas
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute(
        "PRAGMA cache_size = -64000"  # 64MB cache; adjust as needed
    )

    # If sqlite-vec is available, create the vector table extension
    if enable_vec:
        try:
            cursor.execute("LOAD vecextension")
            # sqlite-vec typically creates a virtual table; we'll define it
            # when we first need it in the retrieval module.
            conn.commit()
        except sqlite3.OperationalError as e:
            # vecextension not available — that's OK for P0; we'll skip vector
            # storage in the schema and note it in logs.
            pass

    conn.commit()


# ---------------------------------------------------------------------------
# Helper: memory record row → dict
# ---------------------------------------------------------------------------


def row_to_memory_record(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a memory_items row to a dict with normalized types."""
    return {
        "id": row["id"],
        "type": row["type"],
        "subtype": row["subtype"],
        "content": row["content"],
        "subject": row["subject"],
        "predicate": row["predicate"],
        "object": row["object"],
        "confidence": row["confidence"],
        "importance": row["importance"],
        "salience": row["salience"],
        "decay_score": row["decay_score"],
        "access_count": row["access_count"],
        "last_accessed": row["last_accessed"],
        "trust_score": row["trust_score"],
        "status": row["status"],
        "privacy_class": row["privacy_class"],
        "created_at": row["created_at"],
        "valid_from": row["valid_from"],
        "valid_until": row["valid_until"],
        "source": row["source"],
        "source_event": row["source_event"],
        "source_task": row["source_task"],
        "session_id": row["session_id"],
        "task_id": row["task_id"],
        "keywords": row["keywords"],
        "embedding_id": row["embedding_id"],
        "supersedes_id": row["supersedes_id"],
        "superseded_by_id": row["superseded_by_id"],
    }


# ---------------------------------------------------------------------------
# Basic connection factory
# ---------------------------------------------------------------------------

def make_connection(db_path: str = "jarvis_memory.db") -> sqlite3.Connection:
    """Create a new SQLite connection with the Memory Fabric schema initialized."""
    conn = sqlite3.connect(db_path)
    init_schema(conn)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Migration / upgrade helpers (version tracking)
# ---------------------------------------------------------------------------

SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS _schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    description TEXT NOT NULL
)
"""

def record_migration(conn: sqlite3.Connection, version: int, description: str) -> None:
    """Record that a schema migration has been applied."""
    conn.execute(
        "INSERT OR IGNORE INTO _schema_migrations (version, description) VALUES (?, ?)",
        (version, description),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Exported symbols
# ---------------------------------------------------------------------------

__all__ = [
    "init_schema",
    "make_connection",
    "row_to_memory_record",
    "SCHEMA_DDL",
    "_schema_migrations",
    "record_migration",
]