"""Shared Embedding Cache — Avoid regenerating embeddings by hashing input text.

SHA256(text) → cached embedding vector.
Huge savings during repeated coding sessions and similar queries.
"""
import hashlib
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("cache_system.shared_embedding_cache")


class SharedEmbeddingCache:
    """Cache embeddings using SHA256 of input text as key.

    Stores in SQLite for cross-session persistence.
    Embedding generation is expensive (~100-500ms); cache hit is ~0.01ms.
    """

    def __init__(self, db_path: str = "cache/embeddings.db"):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._mem_cache: dict[str, list[float]] = {}
        self._hits = 0
        self._misses = 0
        self._generated = 0
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    hash TEXT PRIMARY KEY,
                    text_preview TEXT,
                    embedding TEXT NOT NULL,
                    model TEXT DEFAULT 'default',
                    dimension INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    access_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_model ON embeddings(model)")
            conn.commit()
            conn.close()

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, text: str, model: str = "default") -> list[float] | None:
        key = self.hash_text(text)

        # Check memory cache first
        if key in self._mem_cache:
            self._hits += 1
            return self._mem_cache[key]

        # Check SQLite
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT embedding, model FROM embeddings WHERE hash = ? AND model = ?",
                (key, model)
            ).fetchone()
            if row:
                embedding = json.loads(row[0])
                conn.execute(
                    "UPDATE embeddings SET access_count = access_count + 1 WHERE hash = ?",
                    (key,)
                )
                conn.commit()
                conn.close()
                self._mem_cache[key] = embedding
                self._hits += 1
                return embedding
            conn.close()

        self._misses += 1
        return None

    def put(self, text: str, embedding: list[float], model: str = "default") -> None:
        key = self.hash_text(text)
        self._mem_cache[key] = embedding

        embedding_str = json.dumps(embedding)
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (hash, text_preview, embedding, model, dimension, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (key, text[:100], embedding_str, model, len(embedding), time.time())
            )
            conn.commit()
            conn.close()

    def get_or_generate(self, text: str, generator_fn, model: str = "default") -> list[float]:
        """Get cached embedding or generate and cache it."""
        cached = self.get(text, model)
        if cached is not None:
            return cached

        embedding = generator_fn(text)
        self.put(text, embedding, model)
        self._generated += 1
        return embedding

    def batch_get(self, texts: list[str], model: str = "default") -> tuple[list[list[float] | None], list[int]]:
        """Get multiple embeddings. Returns (results, missing_indices)."""
        results = []
        missing = []
        for i, text in enumerate(texts):
            emb = self.get(text, model)
            results.append(emb)
            if emb is None:
                missing.append(i)
        return results, missing

    def batch_put(self, texts: list[str], embeddings: list[list[float]], model: str = "default") -> None:
        for text, embedding in zip(texts, embeddings):
            self.put(text, embedding, model)

    def get_size(self) -> int:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()
            conn.close()
            return row[0] if row else 0

    def get_stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "cached_embeddings": self.get_size(),
            "mem_cache_size": len(self._mem_cache),
            "hits": self._hits,
            "misses": self._misses,
            "generated": self._generated,
            "hit_rate": round(self._hits / max(total, 1) * 100, 1),
        }

    def clear(self) -> None:
        self._mem_cache.clear()
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("DELETE FROM embeddings")
            conn.commit()
            conn.close()


_embedding_cache_instance: SharedEmbeddingCache | None = None


def get_shared_embedding_cache() -> SharedEmbeddingCache:
    global _embedding_cache_instance
    if _embedding_cache_instance is None:
        _embedding_cache_instance = SharedEmbeddingCache()
    return _embedding_cache_instance
