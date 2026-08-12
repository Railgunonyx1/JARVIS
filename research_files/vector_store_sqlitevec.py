"""
Semantic RAG Vector Memory Store for JARVIS MK-X — sqlite-vec backend.

Drop-in replacement for memory/vector_store.py's VectorMemoryStore.
Same public methods (store_vector, search_similar, close) so callers
don't need to change. Internals differ:

- Old: loads every embedding into a Python list at startup, does a
  full numpy matmul over all of them on every search (O(n) per query,
  the #1 hotspot flagged in your own 04_architecture_recommendations.md).
- New: embeddings live in a `vec0` virtual table inside the same
  SQLite file. sqlite-vec indexes and searches them with a real KNN
  query, so search stays fast as the memory count grows past the
  ~1000-row point where the old approach starts to show up in
  latency numbers.

Still uses the same lightweight deterministic embedding function as
before (hash-bucket bag-of-words) — this only fixes the STORAGE/SEARCH
side, it doesn't change embedding quality. If you upgrade to real
embeddings (sentence-transformers, etc.) later, only `_text_to_vector`
needs to change; the storage layer doesn't care where the vector
came from as long as the dimension matches.

Install: pip install sqlite-vec
"""

from __future__ import annotations

import logging
import sqlite3
import struct
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import sqlite_vec

logger = logging.getLogger("jarvis.memory.vector")

EMBED_DIM = 128


def _text_to_vector(text: str, dim: int = EMBED_DIM) -> np.ndarray:
    """Same deterministic embedding as the original implementation —
    unchanged so existing stored data stays compatible."""
    vec = np.zeros(dim, dtype=np.float32)
    words = text.lower().split()
    if not words:
        return vec
    for idx, word in enumerate(words):
        slot = abs(hash(word)) % dim
        vec[slot] += 1.0 + (0.1 * idx)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def _serialize(vec: np.ndarray) -> bytes:
    """sqlite-vec wants raw packed float32 bytes, not JSON."""
    return struct.pack(f"{len(vec)}f", *vec.tolist())


class _LRUCache:
    """Unchanged from the original — search result cache."""

    def __init__(self, max_size: int = 64):
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
        return None

    def put(self, key: str, value: Any):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)


class VectorMemoryStore:
    """Same public interface as the original VectorMemoryStore, backed
    by sqlite-vec's vec0 virtual table instead of an in-memory numpy list."""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or (Path.home() / ".jarvis" / "data" / "vector_memory.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._conn_lock = threading.Lock()
        self._cache = _LRUCache(max_size=64)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        with self._conn_lock:
            if self._conn is None:
                conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=10.0)
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
                self._conn = conn
            return self._conn

    def _init_db(self):
        conn = self._get_conn()
        # Metadata table: text, category, created_at, keyed by rowid.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vector_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT UNIQUE NOT NULL,
                category TEXT DEFAULT 'general',
                created_at REAL NOT NULL
            )
        """)
        # vec0 virtual table: the actual KNN-searchable index. rowid
        # matches vector_meta.id so a join/lookup is a simple key match.
        conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vector_index USING vec0(
                embedding float[{EMBED_DIM}]
            )
        """)
        conn.commit()

    def store_vector(self, text: str, category: str = "general") -> bool:
        if not text.strip():
            return False

        vec = _text_to_vector(text)
        now = time.time()
        conn = self._get_conn()

        try:
            existing = conn.execute(
                "SELECT id FROM vector_meta WHERE text = ?", (text,)
            ).fetchone()

            if existing:
                row_id = existing[0]
                conn.execute(
                    "UPDATE vector_meta SET category = ?, created_at = ? WHERE id = ?",
                    (category, now, row_id),
                )
                conn.execute("DELETE FROM vector_index WHERE rowid = ?", (row_id,))
                conn.execute(
                    "INSERT INTO vector_index(rowid, embedding) VALUES (?, ?)",
                    (row_id, _serialize(vec)),
                )
            else:
                cur = conn.execute(
                    "INSERT INTO vector_meta (text, category, created_at) VALUES (?, ?, ?)",
                    (text, category, now),
                )
                row_id = cur.lastrowid  # real DB-assigned id, not guessed
                conn.execute(
                    "INSERT INTO vector_index(rowid, embedding) VALUES (?, ?)",
                    (row_id, _serialize(vec)),
                )

            conn.commit()
            self._cache = _LRUCache(max_size=64)  # invalidate on write
            logger.info("Vector memory stored: '%s'", text[:50])
            return True
        except Exception as e:
            logger.error("Failed to store vector memory: %s", e)
            return False

    def search_similar(self, query: str, top_k: int = 3, min_score: float = 0.15) -> list[dict[str, Any]]:
        cache_key = f"{query}|{top_k}|{min_score}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        query_vec = _text_to_vector(query)
        conn = self._get_conn()

        # vec0 returns L2 distance by default; convert to a cosine-like
        # score for consistency with the original API (vectors here are
        # normalized, so this is a reasonable proxy, not an exact match
        # to the old dot-product cosine value).
        rows = conn.execute(
            """
            SELECT vm.id, vm.text, vm.category, vm.created_at, vi.distance
            FROM vector_index vi
            JOIN vector_meta vm ON vm.id = vi.rowid
            WHERE vi.embedding MATCH ? AND k = ?
            ORDER BY vi.distance
            """,
            (_serialize(query_vec), max(top_k * 3, top_k)),  # over-fetch, then filter by score
        ).fetchall()

        results = []
        for row_id, text, category, created_at, distance in rows:
            # L2 distance on normalized vectors: score = 1 - distance/2 gives
            # a 0..1-ish similarity proxy. Good enough for ranking/filtering;
            # not bit-identical to the old cosine number.
            score = max(0.0, 1.0 - (distance / 2.0))
            if score < min_score:
                continue
            results.append({
                "id": row_id,
                "text": text,
                "category": category,
                "score": round(float(score), 3),
                "created_at": created_at,
            })
            if len(results) >= top_k:
                break

        self._cache.put(cache_key, results)
        return results

    def close(self):
        with self._conn_lock:
            if self._conn:
                self._conn.close()
                self._conn = None
