"""
JARVIS Memory Fabric — sqlite-vec integration

Extension point for vector retrieval. Kept separate so the memory layer does
not depend on sqlite-vec being installed. The SQLiteMemoryStorage exposes a
`vector_search` interface that raises NotImplementedError until this module
sets up the virtual table.

Usage:
    from jarvis_memory_fabric import vec_store
    vec_store.attach(storage)   # loads sqlite-vec + creates virtual table
    vec_store.upsert(storage, memory_id, embedding)
    vec_store.search(storage, embedding, limit=20)
"""

from __future__ import annotations

from typing import List, Tuple, Optional

import sqlite3


VEC_TABLE = "memory_vec"


def _ensure_vec(conn: sqlite3.Connection, dim: int) -> None:
    """Load sqlite-vec extension and create the virtual table if needed."""
    try:
        import sqlite_vec  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "sqlite-vec is not installed. Install with: pip install sqlite-vec"
        ) from e

    # Register the extension
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    # Create the virtual table for embeddings
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {VEC_TABLE} "
        f"USING vec0(embedding float[{dim}])"
    )
    conn.commit()


def attach(storage: "SQLiteMemoryStorage", dim: int = 768) -> None:  # type: ignore
    """Attach sqlite-vec to an existing storage instance."""
    _ensure_vec(storage._conn, dim)
    storage._vec_enabled = True
    storage._vec_dim = dim


def upsert(storage: "SQLiteMemoryStorage", memory_id: str, embedding: List[float]) -> None:  # type: ignore
    """Store/overwrite an embedding for a memory item."""
    if not storage._vec_enabled:
        raise RuntimeError("sqlite-vec not attached. Call attach() first.")
    if len(embedding) != storage._vec_dim:
        raise ValueError(
            f"embedding dim {len(embedding)} != expected {storage._vec_dim}"
        )
    # Use a deterministic 31-bit positive rowid derived from memory_id
    rowid = _rowid_from_id(memory_id)
    emb_blob = _float_list_to_blob(embedding)
    storage._conn.execute(
        f"INSERT OR REPLACE INTO {VEC_TABLE} (rowid, embedding) VALUES (?, ?)",
        (rowid, emb_blob),
    )
    # Record the mapping in metadata table
    storage._conn.execute(
        "INSERT OR REPLACE INTO memory_embeddings "
        "(embedding_id, memory_item_id, dimensions, vec_rowid) VALUES (?, ?, ?, ?)",
        (memory_id, memory_id, len(embedding), rowid),
    )
    storage._conn.commit()


def search(
    storage: "SQLiteMemoryStorage",  # type: ignore
    embedding: List[float],
    *,
    limit: int = 20,
) -> List[Tuple[str, float]]:
    """Return (memory_id, distance) nearest neighbors."""
    if not storage._vec_enabled:
        raise RuntimeError("sqlite-vec not attached. Call attach() first.")
    qblob = _float_list_to_blob(embedding)
    cur = storage._conn.execute(
        f"SELECT rowid, distance FROM {VEC_TABLE} "
        f"WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
        (qblob, limit),
    )
    results: List[Tuple[str, float]] = []
    for row in cur.fetchall():
        # Reverse lookup via memory_embeddings.vec_rowid
        mcur = storage._conn.execute(
            "SELECT memory_item_id FROM memory_embeddings WHERE vec_rowid = ?",
            (row["rowid"],),
        )
        mrow = mcur.fetchone()
        mid = mrow["memory_item_id"] if mrow else f"rowid:{row['rowid']}"
        results.append((mid, row["distance"]))
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _float_list_to_blob(vec: List[float]) -> bytes:
    import struct

    return struct.pack(f"{len(vec)}f", *vec)


def _rowid_from_id(memory_id: str) -> int:
    # deterministic 31-bit positive rowid from id string
    h = hash(memory_id) & 0x7FFFFFFF
    return h if h != 0 else 1
