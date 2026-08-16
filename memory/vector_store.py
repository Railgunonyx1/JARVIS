"""
Semantic RAG Vector Memory Store for JARVIS MK-X — sqlite-vec backend.

Drop-in replacement for memory/vector_store.py's VectorMemoryStore.
Same public methods (store_vector, search_similar, close) so callers
don't need to change.

Embeddings: real semantic vectors via sentence-transformers
(all-MiniLM-L6-v2, 384-dim) — cosine similarity now reflects meaning,
not just shared vocabulary. The model loads lazily on first use; if it
is unavailable the store falls back to a deterministic hash-bucket
embedding at the same dimension so the schema stays valid.

Storage: embeddings live in a `vec0` virtual table (sqlite-vec KNN),
so search stays fast as memory grows. The DB file is suffixed by the
embedding dimension to avoid schema mismatches across backends.

Install: pip install sqlite-vec sentence-transformers
"""

from __future__ import annotations

import logging
import sqlite3
import struct
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # annotations are strings (PEP 563) — keep numpy lazy
    import numpy as np

logger = logging.getLogger("jarvis.memory.vector")

# Fixed dimension keeps the vec0 schema and DB file stable regardless of whether
# the MiniLM model is available at runtime (hash fallback adapts to any dim).
# Prevents a machine without sentence-transformers from silently opening a
# different-dimension DB and isolating all previously stored embeddings.
EMBED_DIM = 384


_embed_model = None
_embed_ready = False
_embed_lock = threading.Lock()


def _get_model():
    """Lazily load the MiniLM model once; never retry after a failure."""
    global _embed_model, _embed_ready
    if _embed_model is not None or _embed_ready:
        return _embed_model
    with _embed_lock:
        if _embed_model is not None or _embed_ready:
            return _embed_model
        try:
            from sentence_transformers import SentenceTransformer
            _embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            logger.info("MiniLM embedding model loaded")
        except Exception as e:
            logger.warning("MiniLM embedding model unavailable (%s); using hash-bucket fallback", e)
            _embed_model = None
        _embed_ready = True
        return _embed_model


def _hash_vector(text: str, dim: int) -> np.ndarray:
    """Deterministic hash-bucket bag-of-words fallback (any dimension)."""
    import numpy as np
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


def _text_to_vector(text: str, dim: int = EMBED_DIM) -> np.ndarray:
    """Real semantic embedding (MiniLM) with a hash-bucket fallback."""
    import numpy as np
    model = _get_model()
    if model is not None:
        vec = model.encode([text], normalize_embeddings=True)[0]
        if vec.shape[0] != dim:
            padded = np.zeros(dim, dtype=np.float32)
            n = min(vec.shape[0], dim)
            padded[:n] = vec[:n]
            return padded
        return vec.astype(np.float32)
    return _hash_vector(text, dim)


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
        if db_path is None:
            db_path = Path.home() / ".jarvis" / "data" / f"vector_memory_{EMBED_DIM}.db"
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._conn_lock = threading.Lock()
        self._db_lock = threading.Lock()  # serializes reads/writes on the connection
        self._cache = _LRUCache(max_size=64)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        with self._conn_lock:
            if self._conn is None:
                conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=10.0)
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.enable_load_extension(True)
                import sqlite_vec
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
            with self._db_lock:
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
        with self._db_lock:
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

    def count(self) -> int:
        conn = self._get_conn()
        try:
            with self._db_lock:
                row = conn.execute("SELECT COUNT(*) AS c FROM vector_meta").fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def close(self):
        with self._conn_lock:
            if self._conn:
                self._conn.close()
                self._conn = None
