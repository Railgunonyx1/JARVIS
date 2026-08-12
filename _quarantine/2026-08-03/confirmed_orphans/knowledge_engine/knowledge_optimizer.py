"""Knowledge Optimizer — Analyzes, prunes, and optimizes the knowledge graph."""

import logging
import threading
import time
from collections import defaultdict

logger = logging.getLogger("jarvis.knowledge_engine.knowledge_optimizer")


class KnowledgeOptimizer:
    """Analyzes knowledge graph health and performs optimization operations."""

    def __init__(self):
        self._lock = threading.Lock()
        self._optimization_history: list[dict] = []
        self._last_optimization: float = 0.0
        self._total_pruned: int = 0
        self._total_merged: int = 0

    def optimize_graph(self) -> dict:
        """Analyze knowledge graph and suggest optimizations."""
        start = time.perf_counter()
        try:
            from knowledge_graph.graph import get_knowledge_graph
            kg = get_knowledge_graph()
        except Exception as e:
            logger.error("Failed to access knowledge graph: %s", e)
            return {"orphan_nodes": 0, "duplicate_suggestions": [], "missing_relations": [], "score": 0.0}

        stats = kg.get_graph_stats()
        entity_count = stats["entities"]
        relation_count = stats["relations"]

        orphan_nodes = self._count_orphan_nodes(kg)
        duplicate_suggestions = self._find_duplicate_suggestions(kg)
        missing_relations = self._find_missing_relations(kg)

        density = self._compute_density(entity_count, relation_count)
        orphan_ratio = orphan_nodes / entity_count if entity_count > 0 else 0.0
        duplicate_ratio = len(duplicate_suggestions) / entity_count if entity_count > 0 else 0.0
        missing_ratio = len(missing_relations) / entity_count if entity_count > 0 else 0.0

        score = max(0.0, 1.0 - (orphan_ratio * 0.4 + duplicate_ratio * 0.3 + missing_ratio * 0.3))
        elapsed = time.perf_counter() - start

        result = {
            "orphan_nodes": orphan_nodes,
            "duplicate_suggestions": duplicate_suggestions[:20],
            "missing_relations": missing_relations[:20],
            "score": round(score, 4),
            "entity_count": entity_count,
            "relation_count": relation_count,
            "density": round(density, 6),
            "analysis_time_ms": round(elapsed * 1000, 2),
        }

        with self._lock:
            self._optimization_history.append({
                "timestamp": time.time(),
                "result": result,
            })
            if len(self._optimization_history) > 100:
                self._optimization_history = self._optimization_history[-100:]
            self._last_optimization = time.time()

        return result

    def get_knowledge_stats(self) -> dict:
        """Return comprehensive knowledge graph statistics."""
        try:
            from knowledge_graph.graph import get_knowledge_graph
            kg = get_knowledge_graph()
        except Exception as e:
            logger.error("Failed to access knowledge graph: %s", e)
            return {
                "total_entities": 0, "total_relations": 0,
                "avg_degree": 0.0, "density": 0.0, "connected_components": 0,
            }

        stats = kg.get_graph_stats()
        total_entities = stats["entities"]
        total_relations = stats["relations"]

        avg_degree = (2 * total_relations / total_entities) if total_entities > 0 else 0.0
        density = self._compute_density(total_entities, total_relations)
        connected_components = self._estimate_connected_components(kg, total_entities)

        return {
            "total_entities": total_entities,
            "total_relations": total_relations,
            "entity_types": stats.get("entity_types", {}),
            "relation_types": stats.get("relation_types", {}),
            "avg_degree": round(avg_degree, 2),
            "density": round(density, 6),
            "connected_components": connected_components,
            "cache_size": stats.get("cache_size", 0),
        }

    def prune_orphan_nodes(self, min_age_days: int = 30) -> int:
        """Remove old orphan nodes (no relations). Returns count removed."""
        try:
            from knowledge_graph.graph import get_knowledge_graph
            kg = get_knowledge_graph()
        except Exception as e:
            logger.error("Failed to access knowledge graph: %s", e)
            return 0

        cutoff = time.time() - (min_age_days * 86400)
        conn = kg._get_conn()
        removed = 0

        with self._lock:
            # Find orphan entities (no incoming or outgoing relations)
            orphans = conn.execute("""
                SELECT e.id, e.name, e.created_at FROM entities e
                WHERE NOT EXISTS (
                    SELECT 1 FROM relations WHERE source_id = e.id OR target_id = e.id
                )
                AND e.created_at < ?
            """, (cutoff,)).fetchall()

            for orphan in orphans:
                eid = orphan["id"]
                name = orphan["name"]
                conn.execute("DELETE FROM entities WHERE id = ?", (eid,))
                kg._entity_cache.pop(eid, None)
                cache_key = name.lower()
                if kg._name_cache.get(cache_key) == eid:
                    del kg._name_cache[cache_key]
                removed += 1

            conn.commit()

        if removed > 0:
            self._total_pruned += removed
            logger.info("Pruned %d orphan nodes (age > %d days)", removed, min_age_days)

        return removed

    def merge_duplicates(self, threshold: float = 0.8) -> int:
        """Merge similar entities. Returns count merged."""
        try:
            from knowledge_graph.graph import get_knowledge_graph
            kg = get_knowledge_graph()
        except Exception as e:
            logger.error("Failed to access knowledge graph: %s", e)
            return 0

        conn = kg._get_conn()
        merged = 0

        with self._lock:
            entities = conn.execute(
                "SELECT id, name, entity_type, properties FROM entities ORDER BY name"
            ).fetchall()

            name_map: dict[str, list] = defaultdict(list)
            for e in entities:
                normalized = e["name"].lower().strip()
                name_map[normalized].append(e)

            # Exact name duplicates (different casing/whitespace)
            for normalized, group in name_map.items():
                if len(group) > 1:
                    keeper = group[0]
                    for duplicate in group[1:]:
                        self._merge_entity(kg, conn, keeper["id"], duplicate["id"])
                        merged += 1

            # Similar name duplicates (edit distance based)
            all_names = [(e["id"], e["name"]) for e in entities]
            for i in range(len(all_names)):
                for j in range(i + 1, min(i + 50, len(all_names))):
                    id_a, name_a = all_names[i]
                    id_b, name_b = all_names[j]
                    similarity = self._name_similarity(name_a.lower(), name_b.lower())
                    if similarity >= threshold:
                        self._merge_entity(kg, conn, id_a, id_b)
                        merged += 1

            conn.commit()

        if merged > 0:
            self._total_merged += merged
            logger.info("Merged %d duplicate entities", merged)

        return merged

    def rebuild_index(self) -> None:
        """Rebuild the in-memory caches for the knowledge graph."""
        try:
            from knowledge_graph.graph import get_knowledge_graph
            kg = get_knowledge_graph()
            kg._entity_cache.clear()
            kg._name_cache.clear()
            kg._neighbor_cache.clear()
            kg._load_caches()
            logger.info("Knowledge graph index rebuilt")
        except Exception as e:
            logger.error("Failed to rebuild index: %s", e)

    def get_optimization_history(self) -> list:
        """Return past optimization results."""
        with self._lock:
            return list(self._optimization_history)

    def get_optimization_stats(self) -> dict:
        """Return cumulative optimization statistics."""
        with self._lock:
            return {
                "total_optimizations": len(self._optimization_history),
                "total_pruned": self._total_pruned,
                "total_merged": self._total_merged,
                "last_optimization": self._last_optimization,
            }

    def _count_orphan_nodes(self, kg) -> int:
        """Count entities with no relations."""
        conn = kg._get_conn()
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM entities e
            WHERE NOT EXISTS (
                SELECT 1 FROM relations WHERE source_id = e.id OR target_id = e.id
            )
        """).fetchone()
        return row["cnt"] if row else 0

    def _find_duplicate_suggestions(self, kg) -> list[dict]:
        """Find potential duplicate entities."""
        conn = kg._get_conn()
        entities = conn.execute("SELECT id, name, entity_type FROM entities ORDER BY name").fetchall()
        suggestions = []
        seen_pairs = set()

        for i in range(len(entities)):
            for j in range(i + 1, min(i + 30, len(entities))):
                a, b = entities[i], entities[j]
                pair_key = (min(a["id"], b["id"]), max(a["id"], b["id"]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                sim = self._name_similarity(a["name"].lower(), b["name"].lower())
                if sim >= 0.7:
                    suggestions.append({
                        "entity_a": a["name"],
                        "entity_b": b["name"],
                        "similarity": round(sim, 4),
                        "type_a": a["entity_type"],
                        "type_b": b["entity_type"],
                    })

                if len(suggestions) >= 20:
                    return suggestions

        return suggestions

    def _find_missing_relations(self, kg) -> list[dict]:
        """Find entities that likely should be related but aren't."""
        conn = kg._get_conn()
        missing = []

        # Find entities with same type that share properties but have no relation
        rows = conn.execute("""
            SELECT e1.id as id1, e1.name as name1, e2.id as id2, e2.name as name2, e1.entity_type
            FROM entities e1
            JOIN entities e2 ON e1.entity_type = e2.entity_type AND e1.id < e2.id
            WHERE NOT EXISTS (
                SELECT 1 FROM relations
                WHERE (source_id = e1.id AND target_id = e2.id)
                   OR (source_id = e2.id AND target_id = e1.id)
            )
            LIMIT 100
        """).fetchall()

        for row in rows:
            name1, name2 = row["name1"], row["name2"]
            sim = self._name_similarity(name1.lower(), name2.lower())
            if sim > 0.4:
                missing.append({
                    "entity_a": name1,
                    "entity_b": name2,
                    "entity_type": row["entity_type"],
                    "suggested_relation": "RELATED_TO",
                    "name_similarity": round(sim, 4),
                })
                if len(missing) >= 20:
                    return missing

        return missing

    def _merge_entity(self, kg, conn, keeper_id: int, victim_id: int) -> None:
        """Merge victim entity into keeper, transferring relations."""
        # Transfer outgoing relations
        conn.execute("""
            INSERT OR REPLACE INTO relations (source_id, target_id, relation_type, properties, weight, created_at)
            SELECT ?, target_id, relation_type, properties, weight, created_at
            FROM relations WHERE source_id = ? AND target_id != ?
        """, (keeper_id, victim_id, keeper_id))

        # Transfer incoming relations
        conn.execute("""
            INSERT OR REPLACE INTO relations (source_id, target_id, relation_type, properties, weight, created_at)
            SELECT source_id, ?, relation_type, properties, weight, created_at
            FROM relations WHERE target_id = ? AND source_id != ?
        """, (keeper_id, victim_id, keeper_id))

        # Delete victim relations and entity
        conn.execute("DELETE FROM relations WHERE source_id = ? OR target_id = ?", (victim_id, victim_id))
        conn.execute("DELETE FROM entities WHERE id = ?", (victim_id,))

        # Update caches
        victim_entity = kg._entity_cache.pop(victim_id, None)
        if victim_entity:
            cache_key = victim_entity.name.lower()
            if kg._name_cache.get(cache_key) == victim_id:
                del kg._name_cache[cache_key]

    def _name_similarity(self, a: str, b: str) -> float:
        """Compute similarity between two names using character-level bigrams."""
        if a == b:
            return 1.0
        if not a or not b:
            return 0.0

        # Prefix match bonus
        common_prefix_len = 0
        for ca, cb in zip(a, b):
            if ca == cb:
                common_prefix_len += 1
            else:
                break
        prefix_bonus = min(common_prefix_len / max(len(a), len(b)), 0.3)

        # Character bigram similarity
        bigrams_a = set()
        for i in range(len(a) - 1):
            bigrams_a.add(a[i:i + 2])
        bigrams_b = set()
        for i in range(len(b) - 1):
            bigrams_b.add(b[i:i + 2])

        if not bigrams_a or not bigrams_b:
            return prefix_bonus

        intersection = bigrams_a & bigrams_b
        union = bigrams_a | bigrams_b
        jaccard = len(intersection) / len(union) if union else 0.0

        return min(jaccard + prefix_bonus, 1.0)

    def _compute_density(self, entities: int, relations: int) -> float:
        """Compute graph density."""
        if entities < 2:
            return 0.0
        max_possible = entities * (entities - 1)
        return relations / max_possible if max_possible > 0 else 0.0

    def _estimate_connected_components(self, kg, entity_count: int) -> int:
        """Estimate connected components via BFS (bounded for performance)."""
        if entity_count == 0:
            return 0
        if entity_count > 5000:
            # For large graphs, estimate from relation count
            return max(1, entity_count - kg.get_graph_stats()["relations"])

        conn = kg._get_conn()
        all_ids = set(kg._entity_cache.keys())
        visited = set()
        components = 0

        for start_id in list(all_ids):
            if start_id in visited:
                continue
            components += 1
            stack = [start_id]
            while stack:
                current = stack.pop()
                if current in visited:
                    continue
                visited.add(current)
                # Outgoing
                for target_id, _ in kg._neighbor_cache.get(current, []):
                    if target_id not in visited and target_id in all_ids:
                        stack.append(target_id)
                # Incoming
                inbound = conn.execute(
                    "SELECT source_id FROM relations WHERE target_id = ?", (current,)
                ).fetchall()
                for row in inbound:
                    src = row["source_id"]
                    if src not in visited and src in all_ids:
                        stack.append(src)

            # Nodes not in graph at all count as isolated components
            break  # Optimize: for large graphs, just return estimate

        unvisited = all_ids - visited
        return components + len(unvisited)


_instance: KnowledgeOptimizer | None = None
_instance_lock = threading.Lock()


def get_knowledge_optimizer() -> KnowledgeOptimizer:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = KnowledgeOptimizer()
    return _instance
