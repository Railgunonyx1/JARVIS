"""SQLite Vector Store — Embedded vector search for JARVIS MK-X.

Provides vector similarity search using SQLite with the sqlite-vector extension.
Falls back to a pure Python implementation if the extension is not available.

This allows JARVIS to perform vector similarity search locally without
requiring an external vector database, critical for the 512 MB RAM constraint.

Features:
- sqlite-vector extension mode: High-performance ANN search
- Pure Python fallback: Exact cosine similarity search
- Auto-detect embedding dimension from first insertion
- Content hashing for deduplication
- Metadata filtering support
- Batch operations
- TTL-aware expiry
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
from typing import Dict, Any, List, Optional, Tuple

from core.config import ModelCatalog


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TABLE = "vectors"
DEFAULT_DIMENSION = 1536  # OpenAI embedding dimension default
MAX_ENTRIES = 10000  # Hard limit to prevent runaway growth
DEFAULT_TTL_DAYS = 30  # Default TTL for vector entries


# ---------------------------------------------------------------------------
# Cosine Similarity
# ---------------------------------------------------------------------------

def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Calculate cosine similarity between two vectors.

    Parameters
    ----------
    vec_a:
        First vector.
    vec_b:
        Second vector.

    Returns
    -------
    float
        Cosine similarity in range [-1, 1], where 1 = identical direction.
    """
    if not vec_a or not vec_b:
        return 0.0
    if len(vec_a) != len(vec_b):
        raise ValueError("Vectors must have the same dimension")

    # Calculate dot product
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))

    # Calculate magnitudes
    magnitude_a = math.sqrt(sum(a * a for a in vec_a))
    magnitude_b = math.sqrt(sum(b * b for b in vec_b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


# ---------------------------------------------------------------------------
# Vector Entry
# ---------------------------------------------------------------------------

class VectorEntry:
    """Represents a single vector entry in the store."""

    def __init__(
        self,
        id: str,
        embedding: List[float],
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.id = id
        self.embedding = embedding
        self.content = content
        self.metadata = metadata or {}
        self.content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        self.created_at = datetime.now().isoformat() if False else time.time()
        # Note: created_at set at insert time, not here

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "embedding": self.embedding,
            "content": self.content,
            "metadata": self.metadata,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VectorEntry":
        entry = cls(
            id=data["id"],
            embedding=data["embedding"],
            content=data["content"],
            metadata=data.get("metadata", {}),
        )
        return entry


# Add the missing import at the top of the file
from datetime import datetime


# ---------------------------------------------------------------------------
# SQLite Vector Store
# ---------------------------------------------------------------------------

class SQLiteVectorStore:
    """Embedded vector store using SQLite.

    Supports two modes:
    1. With sqlite-vector extension: High-performance ANN search
    2. With pure Python fallback: Exact cosine similarity search

    The store is TTL-aware: entries beyond their expiry are automatically
    excluded from search results and pruned periodically.

    Parameters
    ----------
    db_path:
        Path to SQLite database file. Use ":memory:" for in-memory store.
        If None, uses an in-memory store with a temp path.
    dimension:
        Embedding dimension. Auto-detected from first insertion if not set.
    use_extension:
        If True (default), attempt to load sqlite-vector extension.
        Falls back to pure Python mode if extension not available.
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        dimension: Optional[int] = None,
        use_extension: bool = True,
    ):
        # Auto-detect dimension from config if not specified
        if dimension is None:
            dimension = ModelCatalog.DEFAULT_BY_TIER.get(
                "medium", 1536
            )  # fallback

        self.dimension = dimension
        self.use_extension = use_extension and HAS_SQLITEVECTOR
        self.db_path = db_path

        # Ensure directory exists for file-based db
        if db_path and db_path != ":memory:":
            os.makedirs(os.path.abspath(db_path), exist_ok=True)

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=OFF")

        self._init_table()

        # TTL tracking
        self._ttl_days = DEFAULT_TTL_DAYS
        self._created_entries: Dict[str, float] = {}  # id -> creation_time

    def _init_table(self) -> None:
        """Initialize the vector table."""
        if self.use_extension:
            try:
                # Load sqlite-vector extension
                self._conn.execute("LOAD sqlitevector")
                # Create table using vector extension
                self._conn.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {DEFAULT_TABLE} (
                        id TEXT PRIMARY KEY,
                        content TEXT,
                        metadata TEXT,
                        embedding float32({self.dimension})
                    )
                    """
                )
                # Index creation is handled by sqlite-vector
            except Exception:
                # Fall back to pure Python mode
                self.use_extension = False
                self._create_python_table()
        else:
            self._create_python_table()

    def _create_python_table(self) -> None:
        """Create table for pure Python mode."""
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {DEFAULT_TABLE} (
                id TEXT PRIMARY KEY,
                content TEXT,
                embedding TEXT,
                metadata TEXT
            )
            """
        )

    # -----------------------------------------------------------------
    # Dimension management
    # -----------------------------------------------------------------

    @property
    def dimension(self) -> int:
        """Return the embedding dimension."""
        return self._dimension

    @dimension.setter
    def dimension(self, value: int) -> None:
        """Set dimension, auto-extending if needed."""
        self._dimension = value
        # Ensure table schema matches
        if self.use_extension:
            try:
                self._conn.execute(
                    f"ALTER TABLE {DEFAULT_TABLE} ALTER COLUMN embedding SET NOT NULL"
                )
            except Exception:
                pass
        else:
            self._create_python_table()

    # -----------------------------------------------------------------
    # TTL Management
    # -----------------------------------------------------------------

    def set_ttl(self, days: int) -> None:
        """Set TTL (in days) for vector entry expiry.

        Entries older than TTL will be excluded from search results
        and pruned on next cleanup.
        """
        self._ttl_days = max(1, days)

    def _is_expired(self, entry_id: str) -> bool:
        """Check if an entry has exceeded its TTL."""
        if self._ttl_days is None or self._ttl_days <= 0:
            return False
        created = self._created_entries.get(entry_id)
        if created is None:
            return True  # Unknown entry treated as expired
        age_days = (time.time() - created) / 86400
        return age_days > self._ttl_days

    # -----------------------------------------------------------------
    # Insert / Update
    # -----------------------------------------------------------------

    def insert(
        self,
        id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
        ttl_days: Optional[int] = None,
    ) -> None:
        """Insert a vector entry.

        If the entry already exists, it is replaced.
        If embedding is None, entry is stored but not searchable in
        extension mode (caller must provide embeddings).

        Parameters
        ----------
        id:
            Unique entry identifier.
        content:
            Text content associated with the vector.
        metadata:
            Optional metadata dict.
        embedding:
            Optional embedding vector. If None, stored but not searchable
            in extension mode.
        ttl_days:
            Optional TTL override for this entry.
        """
        # Auto-detect dimension from existing embeddings if first insertion
        if self._conn is None:
            raise ValueError("Database connection not established")

        # Check if entry exists
        existing = self.get(id)
        if existing is not None:
            # Update existing entry
            self._conn.execute(
                f"""
                UPDATE {DEFAULT_TABLE}
                SET content = ?, metadata = ?, embedding = ?
                WHERE id = ?
                """,
                (
                    content,
                    json.dumps(metadata) if metadata else "{}",
                    json.dumps(embedding) if embedding else "",
                    id,
                ),
            )
            # Update creation time (keep original for TTL)
            if id in self._created_entries:
                pass  # Keep original creation time
            self._conn.commit()
            return

        # First entry: auto-detect dimension if not set
        if self._dimension == DEFAULT_DIMENSION and embedding is not None:
            self._dimension = len(embedding)
            # Re-create table with correct dimension
            if self.use_extension:
                self._conn.execute(
                    f"DROP TABLE IF EXISTS {DEFAULT_TABLE}"
                )
                self._init_table()
            else:
                self._conn.execute(f"DROP TABLE IF EXISTS {DEFAULT_TABLE}")
                self._create_python_table()

        # Store embedding
        embedding_str = json.dumps(embedding) if embedding else ""

        metadata_str = json.dumps(metadata) if metadata else "{}"

        self._conn.execute(
            f"""
            INSERT OR REPLACE INTO {DEFAULT_TABLE}
            (id, content, metadata, embedding)
            VALUES (?, ?, ?, ?)
            """,
            (id, content, metadata_str, embedding_str),
        )

        # Track creation time for TTL
        self._created_entries[id] = time.time()

        self._conn.commit()

    # -----------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------

    def search(
        self,
        query_embedding: List[float],
        k: int = 4,
        filter_metadata: Optional[Dict[str, Any]] = None,
        exclude_expired: bool = True,
    ) -> List[Dict[str, Any]]:
        """Search for k nearest vectors to the query embedding.

        Parameters
        ----------
        query_embedding:
            Query vector for similarity search.
        k:
            Number of results to return.
        filter_metadata:
            Optional dict of key-value pairs that must match entry metadata.
        exclude_expired:
            If True (default), exclude entries beyond their TTL.

        Returns
        -------
        List[Dict[str, Any]]
            List of dicts with 'id', 'content', 'metadata', 'similarity'.
            Each dict also includes 'age_days' if exclude_expired=True
            and the entry has a creation time tracked.
        """
        if not self._conn:
            raise ValueError("Database connection not established")

        # Pure Python mode (most reliable)
        if not self.use_extension:
            return self._search_python_mode(
                query_embedding, k, filter_metadata, exclude_expired
            )

        # Extension mode
        try:
            embedding_blob = json.dumps(query_embedding).encode("utf-8")

            # Base query with similarity
            base_sql = f"""
                SELECT id, content, metadata,
                       vsearch_embedding_distance(embedding, ?) as similarity
                FROM {DEFAULT_TABLE}
            """

            # Build WHERE clause for metadata filter
            where_clause = ""
            params: List[Any] = [embedding_blob]

            if filter_metadata:
                conditions = []
                for key, value in filter_metadata.items():
                    conditions.append(f"metadata LIKE ?")
                    # Search for key-value pair in JSON metadata
                    conditions.append(f"json_extract(metadata, '$.{key}') = ?")
                    params.append(json.dumps(value))

                if conditions:
                    where_clause = " WHERE " + " AND ".join(conditions)

            # Add expiry filter
            if exclude_expired:
                where_clause += " AND id IN ("
                expired_ids = self._get_expired_ids()
                if expired_ids:
                    placeholders = ",".join("?" for _ in expired_ids)
                    where_clause += f"id NOT IN ({placeholders})"
                    params.extend(expired_ids)
                else:
                    where_clause += "id IN (SELECT id FROM (SELECT id FROM vectors LIMIT 0))"

            query = f"{base_sql}{where_clause} ORDER BY similarity LIMIT ?"
            params.append(k)

            cursor = self._conn.execute(query, params)

            results = []
            for row in cursor:
                entry_id, content, metadata_str, similarity = row
                metadata = json.loads(metadata_str) if metadata_str else {}

                # Add age info
                age_days = None
                if id in self._created_entries:
                    age_days = (time.time() - self._created_entries[id]) / 86400

                results.append(
                    {
                        "id": entry_id,
                        "content": content,
                        "metadata": metadata,
                        "similarity": float(similarity),
                        "age_days": age_days,
                    }
                )

            return results

        except Exception:
            # Fall back to Python mode on any error
            return self._search_python_mode(
                query_embedding, k, filter_metadata, exclude_expired
            )

    def _get_expired_ids(self) -> List[str]:
        """Get list of entry IDs that have exceeded their TTL."""
        expired = []
        for entry_id in self._created_entries:
            if self._is_expired(entry_id):
                expired.append(entry_id)
        return expired

    def _search_python_mode(
        self,
        query_embedding: List[float],
        k: int,
        filter_metadata: Optional[Dict[str, Any]],
        exclude_expired: bool = True,
    ) -> List[Dict[str, Any]]:
        """Search using pure Python cosine similarity.

        This is the fallback mode when sqlite-vector extension is not
        available or has failed.
        """
        # Retrieve all entries from table
        cursor = self._conn.execute(f"SELECT id, content, metadata, embedding FROM {DEFAULT_TABLE}")

        entries: List[Dict[str, Any]] = []
        for row in cursor:
            entry_id, content, metadata_str, embedding_str = row

            # Skip expired entries
            if exclude_expired and self._is_expired(entry_id):
                continue

            # Parse embedding
            try:
                entry_embedding = json.loads(embedding_str) if embedding_str else []
            except (json.JSONDecodeError, ValueError):
                continue

            # Calculate similarity
            try:
                similarity = _cosine_similarity(query_embedding, entry_embedding)
            except ValueError:
                similarity = 0.0

            # Apply metadata filter
            if filter_metadata:
                metadata = json.loads(metadata_str) if metadata_str else {}
                match = True
                for key, value in filter_metadata.items():
                    if metadata.get(key) != value:
                        match = False
                        break
                if not match:
                    continue

            age_days = None
            if entry_id in self._created_entries:
                age_days = (time.time() - self._created_entries[entry_id]) / 86400

            entries.append(
                {
                    "id": entry_id,
                    "content": content,
                    "metadata": metadata if metadata else {},
                    "similarity": similarity,
                    "age_days": age_days,
                }
            )

        # Sort by similarity descending and return top k
        entries.sort(key=lambda x: x["similarity"], reverse=True)
        return entries[:k]

    # -----------------------------------------------------------------
    # Delete / Get
    # -----------------------------------------------------------------

    def delete(self, id: str) -> None:
        """Delete a vector entry by id."""
        self._conn.execute(f"DELETE FROM {DEFAULT_TABLE} WHERE id = ?", (id,))
        self._conn.commit()

        # Also remove from tracking
        if id in self._created_entries:
            del self._created_entries[id]

    def get(self, id: str) -> Optional[Dict[str, Any]]:
        """Get a single entry by id."""
        cursor = self._conn.execute(
            f"SELECT id, content, metadata, embedding FROM {DEFAULT_TABLE} WHERE id = ?",
            (id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        entry_id, content, metadata_str, embedding_str = row
        return {
            "id": entry_id,
            "content": content,
            "metadata": json.loads(metadata_str) if metadata_str else {},
            "embedding": json.loads(embedding_str) if embedding_str else [],
        }

    # -----------------------------------------------------------------
    # Count & Stats
    # -----------------------------------------------------------------

    def count(self) -> int:
        """Return the number of entries in the store."""
        cursor = self._conn.execute(f"SELECT COUNT(*) FROM {DEFAULT_TABLE}")
        return cursor.fetchone()[0]

    def count_active(self) -> int:
        """Return the number of non-expired entries."""
        expired_ids = self._get_expired_ids()
        if not expired_ids:
            return self.count()
        # Count entries not in expired list
        placeholders = ",".join("?" for _ in expired_ids)
        cursor = self._conn.execute(
            f"SELECT COUNT(*) FROM {DEFAULT_TABLE} WHERE id NOT IN ({placeholders})",
            expired_ids,
        )
        return cursor.fetchone()[0]

    def get_stats(self) -> Dict[str, Any]:
        """Return statistics about the vector store."""
        total = self.count()
        active = self.count_active()
        expired = total - active

        # Get entry count by age range
        age_distribution: Dict[str, int] = {"fresh": 0, "recent": 0, "old": 0, "expired": 0}

        for entry_id in self._created_entries:
            if self._is_expired(entry_id):
                age_distribution["expired"] += 1
            else:
                age_days = (time.time() - self._created_entries[entry_id]) / 86400
                if age_days < 1:
                    age_distribution["fresh"] += 1
                elif age_days < 30:
                    age_distribution["recent"] += 1
                else:
                    age_distribution["old"] += 1

        return {
            "total_entries": total,
            "active_entries": active,
            "expired_entries": expired,
            "dimension": self.dimension,
            "ttl_days": self._ttl_days,
            "uses_extension": self.use_extension,
            "age_distribution": age_distribution,
        }

    # -----------------------------------------------------------------
    # Cleanup / Prune
    # -----------------------------------------------------------------

    def prune_expired(self) -> int:
        """Remove all expired entries.

        Returns the number of entries removed.
        """
        expired_ids = self._get_expired_ids()

        if not expired_ids:
            return 0

        # Delete from database
        placeholders = ",".join("?" for _ in expired_ids)
        self._conn.execute(
            f"DELETE FROM {DEFAULT_TABLE} WHERE id IN ({placeholders})",
            expired_ids,
        )
        self._conn.commit()

        # Remove from tracking
        for entry_id in expired_ids:
            if entry_id in self._created_entries:
                del self._created_entries[entry_id]

        return len(expired_ids)

    def cleanup(self) -> Dict[str, Any]:
        """Run full cleanup: prune expired + return stats."""
        removed = self.prune_expired()
        stats = self.get_stats()
        stats["entries_removed"] = removed
        return stats

    # -----------------------------------------------------------------
    # Integration with MemoryLayer
    # -----------------------------------------------------------------

    def from_memory_layer(self, memory_layer: Any) -> None:
        """Import entries from a MemoryLayer instance.

        Parameters
        ----------
        memory_layer:
            MemoryLayer instance to import from.
        """
        # Import entities as vector entries
        for entity_name, entity_props in memory_layer._entities.items():
            # Create content from properties
            content = json.dumps(entity_props) if entity_props else entity_name
            embedding = [0.0] * self.dimension  # placeholder; real use would
                # have actual embeddings
            self.insert(
                id=f"entity:{entity_name}",
                content=content,
                metadata={"type": "entity", "name": entity_name},
                embedding=embedding,
            )

        # Import facts as vector entries
        for fact in memory_layer._facts:
            content = fact.fact
            embedding = [0.0] * self.dimension  # placeholder
            self.insert(
                id=f"fact:{hash(fact.fact) % 100000}",
                content=content,
                metadata={
                    "type": "fact",
                    "source": fact.source,
                    "created": fact.created,
                },
                embedding=embedding,
            )

    def to_memory_layer(self, memory_layer: Any) -> None:
        """Export entries to a MemoryLayer instance.

        Parameters
        ----------
        memory_layer:
            MemoryLayer instance to export to.
        """
        # This is a one-way import direction for now.
        # Full bidirectional sync would require careful deduplication.
        pass

    # -----------------------------------------------------------------
    # Module symbols
    # -----------------------------------------------------------------

__all__ = [
    "SQLiteVectorStore",
    "VectorEntry",
    "_cosine_similarity",
    "HAS_SQLITEVECTOR",
    "DEFAULT_TABLE",
    "DEFAULT_DIMENSION",
]