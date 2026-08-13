"""
JARVIS Memory Fabric — Deterministic Retrieval Engine

Implements:
- FTS5 keyword search
- Vector retrieval interface (sqlite-vec compatible)
- Metadata filtering
- Entity filtering
- Recency / importance / confidence scoring
- Deduplication
- RRF-style reciprocal rank fusion

No LLM is used here; everything is deterministic.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
import math
from collections import defaultdict

from .storage_sqlite import SQLiteMemoryStorage
from .schema import row_to_memory_record


# Default ranking weights from the architecture (section 15)
DEFAULT_WEIGHTS = {
    "semantic": 0.30,   # vector similarity
    "keyword": 0.20,    # FTS5 BM25 score
    "entity": 0.15,     # entity match
    "graph": 0.15,      # graph traversal
    "recency": 0.10,    # recency decay
    "importance": 0.05, # importance score
    "confidence": 0.05, # confidence
}


# ---------------------------------------------------------------------------
# Adaptive RRF weight learning
# ---------------------------------------------------------------------------

class RRFAdaptiveWeights:
    """Learning-based RRF weight adaptation based on retrieval success.

    After each retrieval, we observe which rank list contributed most to
    finding relevant results. Weights are adjusted proportionally.
    """

    def __init__(self, base_weights: Dict[str, float],
                 learning_rate: float = 0.05):
        self.base_weights = dict(base_weights)
        self.weights = dict(base_weights)
        self.learning_rate = learning_rate
        # Track per-method success counts
        self.success_counts: Dict[str, int] = defaultdict(int)
        self.total_counts: Dict[str, int] = defaultdict(int)

    def record_success(self, method: str) -> None:
        """Call when a retrieval using this method found relevant results."""
        self.success_counts[method] += 1
        self.total_counts[method] += 1
        # Gradually shift weight toward this method
        self.weights[method] = (
            self.weights.get(method, self.base_weights.get(method, 0.0))
            + self.learning_rate * (1.0 - self.weights.get(method, 0.0))
        )

    def record_failure(self, method: str) -> None:
        """Call when retrieval using this method was not helpful."""
        self.total_counts[method] += 1
        # Gradually shift weight away from this method
        self.weights[method] = (
            self.weights.get(method, self.base_weights.get(method, 1.0))
            - self.learning_rate * self.weights.get(method, 0.5)
        )

    def get_weights(self) -> Dict[str, float]:
        """Return current adaptive weights, normalized to sum to 1.0."""
        total = sum(self.weights.values())
        if total > 0:
            return {k: v / total for k, v in self.weights.items()}
        return dict(self.base_weights)

    def reset(self) -> None:
        """Reset to base weights."""
        self.weights = dict(self.base_weights)
        self.success_counts.clear()
        self.total_counts.clear()


class RetrievalEngine:
    """Deterministic hybrid retrieval with RRF fusion.

    Supports adaptive weight learning from retrieval success/failure.
    """

    def __init__(
        self,
        storage: SQLiteMemoryStorage,
        *,
        weights: Optional[Dict[str, float]] = None,
        adaptive: bool = True,
    ) -> None:
        self._storage = storage
        if weights is not None:
            self._weights = dict(weights)
        elif adaptive:
            self._weights = dict(DEFAULT_WEIGHTS)
            self._rrf_adaptive = RRFAdaptiveWeights(self._weights)
        else:
            self._weights = dict(DEFAULT_WEIGHTS)
            self._rrf_adaptive = None

    # ------------------------------------------------------------------
    # FTS5 keyword search
    # ------------------------------------------------------------------

    def keyword_search(
        self, query: str, *, limit: int = 50
    ) -> List[Tuple[str, float]]:
        """Return (memory_item_id, bm25_score) from FTS5.

        FTS5's bm25() returns negative values where more negative = better match.
        We invert to positive for ranking convenience.
        """
        sql = """
            SELECT mi.id, fts.rank as bm25_rank
            FROM memory_fts fts
            JOIN memory_items mi ON fts.rowid = mi.rowid
            WHERE memory_fts MATCH ?
            AND mi.status != 'retired'
            ORDER BY bm25_rank
            LIMIT ?
        """
        cur = self._storage._conn.execute(sql, (query, limit))
        results = []
        for row in cur.fetchall():
            # bm25 is negative; convert to positive score in (0, 1]
            raw = row["bm25_rank"]
            score = 1.0 / (1.0 + abs(raw))  # simple squash
            results.append((row["id"], score))
        return results

    # ------------------------------------------------------------------
    # Vector search (pass-through to storage if available)
    # ------------------------------------------------------------------

    def vector_search(
        self, embedding: List[float], *, limit: int = 20
    ) -> List[Tuple[str, float]]:
        """Use storage.vector_search if sqlite-vec is enabled."""
        try:
            return self._storage.vector_search(embedding, limit=limit)
        except NotImplementedError:
            return []

    # ------------------------------------------------------------------
    # Metadata + entity filtering
    # ------------------------------------------------------------------

    def metadata_search(
        self,
        *,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
        entity: Optional[str] = None,
        type: Optional[str] = None,
        salience: Optional[str] = None,
        min_confidence: float = 0.0,
        max_age_days: Optional[int] = None,
        limit: int = 50,
    ) -> List[Tuple[str, float]]:
        """Deterministic metadata filter, returns (id, score)."""
        records = self._storage.search(
            subject=subject,
            predicate=predicate,
            obj=obj,
            entity=entity,
            type=type,
            salience=salience,
            min_confidence=min_confidence,
            max_age_days=max_age_days,
            limit=limit,
        )
        return [(r["id"], 0.8) for r in records]

    # ------------------------------------------------------------------
    # Recency / importance / confidence scoring
    # ------------------------------------------------------------------

    def score_record(self, record: Dict[str, Any]) -> float:
        """Compute composite score from recency, importance, confidence."""
        now = datetime.now(timezone.utc)
        created = record.get("created_at")
        recency = 1.0
        if created:
            try:
                ct = datetime.strptime(created, "%Y-%m-%dT%H:%M:%fZ").replace(tzinfo=timezone.utc)
                age_days = (now - ct).total_seconds() / 86400.0
                # exponential decay with half-life 30 days
                recency = math.exp(-age_days / 30.0)
            except ValueError:
                pass

        importance = float(record.get("importance", 0.5))
        confidence = float(record.get("confidence", 1.0))
        decay = float(record.get("decay_score", 1.0))

        # Weighted sum (deterministic)
        combined = (
            self._weights["recency"] * recency
            + self._weights["importance"] * importance
            + self._weights["confidence"] * confidence
        ) * decay
        return combined

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def deduplicate(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove near-duplicate records by normalized content/subject+predicate+object."""
        seen: set = set()
        out: List[Dict[str, Any]] = []
        for r in records:
            key = (
                (r.get("subject") or "").strip().lower(),
                (r.get("predicate") or "").strip().lower(),
                (r.get("object") or "").strip().lower(),
                (r.get("content") or "").strip().lower()[:200],
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    # ------------------------------------------------------------------
    # Reciprocal Rank Fusion
    # ------------------------------------------------------------------

    def rrf_fuse(
        self,
        rank_lists: List[List[Tuple[str, float]]],
        *,
        k: int = 60,
        weights: Optional[Dict[str, float]] = None,
    ) -> List[Tuple[str, float]]:
        """Combine multiple ranked lists via Reciprocal Rank Fusion.

        rank_lists: list of (id, score) in ranked order (best first).
        weights: per-method weights (query-type specific). If None, uses
          self._weights (adaptive or default).
        Returns fused list sorted by fused score descending.
        """
        if weights is None:
            if self._rrf_adaptive is not None:
                weights = self._rrf_adaptive.get_weights()
            else:
                weights = DEFAULT_WEIGHTS

        # Weights are applied as a multiplier on the rank contribution.
        # Higher weight for a method means its ranks contribute more.
        fused: Dict[str, float] = {}
        for rank_list_idx, rank_list in enumerate(rank_lists):
            w = weights.get(f"method_{rank_list_idx}", 1.0)
            for rank, (item_id, _score) in enumerate(rank_list):
                fused[item_id] = fused.get(item_id, 0.0) + \
                    (1.0 / (k + rank + 1)) * w
        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
        return ranked

    # ------------------------------------------------------------------
    # Graph reasoning
    # ------------------------------------------------------------------

    def neighborhood(
        self,
        entity_id: str,
        link_types: Optional[List[str]] = None,
        depth: int = 1,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Find entities linked to the given item (1-hop by default).

        Walks memory_links outward from memory_item_id_1 or memory_item_id_2.
        Returns the linked memory items with link type and strength.
        """
        sql = f"""
            SELECT mi.*, ml.link_type, ml.strength
            FROM memory_links ml
            JOIN memory_items mi ON (
                mi.id = ml.memory_item_id_2
                OR mi.id = ml.memory_item_id_1
            )
            WHERE ml.memory_item_id_1 = ? OR ml.memory_item_id_2 = ?
            AND mi.status != 'retired'
        """
        params = [entity_id, entity_id]
        if link_types:
            placeholders = ", ".join("?" for _ in link_types)
            sql += f" AND ml.link_type IN ({placeholders})"
            params.extend(link_types)
        sql += " ORDER BY ml.strength DESC LIMIT ?"
        params.append(limit)

        cur = self._storage._conn.execute(sql, params)
        results = []
        for r in cur.fetchall():
            rec = row_to_memory_record(r)
            rec["_link_type"] = r["link_type"]
            rec["_strength"] = r["strength"]
            results.append(rec)
        return results

    def path_between(
        self,
        start_id: str,
        end_id: str,
        max_depth: int = 5,
    ) -> Optional[List[Dict[str, Any]]]:
        """Find the shortest path between two memory items via memory_links.

        Uses a simple BFS. Returns list of items along the path, or None.
        """
        from collections import deque

        # Quick check: are they directly linked?
        direct = self._conn.execute(
            "SELECT 1 FROM memory_links "
            "WHERE (memory_item_id_1 = ? AND memory_item_id_2 = ?) "
            "OR (memory_item_id_1 = ? AND memory_item_id_2 = ?) "
            "AND status != 'retired'",
            (start_id, end_id, end_id, start_id),
        ).fetchone()
        if direct:
            return [self._storage.recall(start_id), self._storage.recall(end_id)]

        # BFS
        visited = {start_id}
        queue = deque([(start_id, [start_id])])
        while queue:
            current, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            neighbors = self.neighborhood(current, depth=1, limit=50)
            for n in neighbors:
                n_id = n["id"]
                if n_id == end_id:
                    return path + [n_id]
                if n_id not in visited:
                    visited.add(n_id)
                    queue.append((n_id, path + [n_id]))
        return None

    # ------------------------------------------------------------------
    # Full hybrid retrieval
    # ------------------------------------------------------------------

    def retrieve(
        self,
        *,
        query: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        obj: Optional[str] = None,
        entity: Optional[str] = None,
        type: Optional[str] = None,
        salience: Optional[str] = None,
        min_confidence: float = 0.0,
        max_age_days: Optional[int] = None,
        limit: int = 15,
        rerank: bool = True,
    ) -> List[Dict[str, Any]]:
        """Run hybrid retrieval and return ranked memory records.

        Pipeline (section 17):
          retrieve 50 → deduplicate → rerank → select top 5-15
        """
        rank_lists: List[List[Tuple[str, float]]] = []

        # 1. FTS5 keyword
        if query:
            kw = self.keyword_search(query, limit=50)
            rank_lists.append(kw)

        # 2. Vector (if available)
        if embedding is not None:
            vec = self.vector_search(embedding, limit=20)
            if vec:
                rank_lists.append(vec)

        # 3. Metadata/entity
        meta = self.metadata_search(
            subject=subject,
            predicate=predicate,
            obj=obj,
            entity=entity,
            type=type,
            salience=salience,
            min_confidence=min_confidence,
            max_age_days=max_age_days,
            limit=50,
        )
        if meta:
            rank_lists.append(meta)

        # 4. Graph traversal (neighborhood of entities mentioned in query/type)
        if entity or type:
            # Search for items matching the entity/type to get starting points
            start_items = self.metadata_search(
                entity=entity or type, limit=5
            )
            graph_ranks: List[Tuple[str, float]] = []
            for item in start_items:
                neighbor_ids = [r["id"] for r in self.neighborhood(item["id"], depth=1, limit=10)]
                for n_id in neighbor_ids:
                    graph_ranks.append((n_id, 0.7))
            if graph_ranks:
                rank_lists.append(graph_ranks)

        # If nothing produced ranks, try a plain search fallback
        if not rank_lists:
            recs = self._storage.search(
                subject=subject,
                predicate=predicate,
                obj=obj,
                entity=entity,
                type=type,
                salience=salience,
                min_confidence=min_confidence,
                max_age_days=max_age_days,
                limit=50,
            )
            records = recs
        else:
            fused = self.rrf_fuse(rank_lists)
            # Fetch full records
            records = []
            for item_id, _ in fused:
                rec = self._storage.recall(item_id)
                if rec:
                    records.append(rec)

        # Deduplicate
        records = self.deduplicate(records)

        # Rerank with composite score if requested
        if rerank:
            records.sort(key=self.score_record, reverse=True)

        return records[:limit]


# ---------------------------------------------------------------------------
# End of retrieval engine
# ---------------------------------------------------------------------------

__all__ = ["RetrievalEngine", "DEFAULT_WEIGHTS"]
