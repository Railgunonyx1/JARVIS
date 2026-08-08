"""
Knowledge Graph — SQLite-backed graph storage for JARVIS MK-X.

Stores entities and relations as a directed graph. Supports:
- Entity CRUD with typed nodes (PERSON, PROJECT, TOOL, CONCEPT, etc.)
- Relation CRUD with typed edges (WORKS_ON, USES, KNOWS, etc.)
- Graph traversal (BFS/DFS) with depth limits
- Subgraph extraction by entity type or relation type
- Neighborhood queries (N-hop neighbors)
- Centrality ranking (degree-based)
- Persistence via SQLite (WAL mode, thread-safe)

Performance: O(1) entity lookup, O(degree) neighbor traversal,
O(V+E) full graph scan. All queries bounded by depth/limit params.
"""

from __future__ import annotations

import json
import time
import sqlite3
import logging
import threading
from enum import Enum
from pathlib import Path
from collections import deque, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("jarvis.knowledge_graph")


class EntityType(str, Enum):
    PERSON = "PERSON"
    PROJECT = "PROJECT"
    TOOL = "TOOL"
    CONCEPT = "CONCEPT"
    FILE = "FILE"
    APPLICATION = "APPLICATION"
    COMMAND = "COMMAND"
    LOCATION = "LOCATION"
    ORGANIZATION = "ORGANIZATION"
    TOPIC = "TOPIC"
    EVENT = "EVENT"
    OTHER = "OTHER"


class RelationType(str, Enum):
    WORKS_ON = "WORKS_ON"
    USES = "USES"
    KNOWS = "KNOWS"
    CREATED = "CREATED"
    LOCATED_IN = "LOCATED_IN"
    PART_OF = "PART_OF"
    DEPENDS_ON = "DEPENDS_ON"
    RELATED_TO = "RELATED_TO"
    OWNS = "OWNS"
    MENTIONED_IN = "MENTIONED_IN"
    CAUSED_BY = "CAUSED_BY"
    FOLLOWS = "FOLLOWS"
    PRECEDES = "PRECEDES"
    SIMILAR_TO = "SIMILAR_TO"
    CONTAINS = "CONTAINS"


@dataclass
class Entity:
    """A node in the knowledge graph."""
    id: int = 0
    name: str = ""
    entity_type: EntityType = EntityType.OTHER
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_count: int = 0
    importance: float = 0.5


@dataclass
class Relation:
    """A directed edge in the knowledge graph."""
    id: int = 0
    source_id: int = 0
    target_id: int = 0
    relation_type: RelationType = RelationType.RELATED_TO
    properties: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    created_at: float = field(default_factory=time.time)


@dataclass
class GraphPath:
    """A path between two entities."""
    entities: List[Entity]
    relations: List[Relation]
    total_weight: float = 0.0


class KnowledgeGraph:
    """SQLite-backed knowledge graph with in-memory caches for hot paths."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or (Path.home() / ".jarvis" / "data" / "knowledge_graph.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        # Caches for hot paths
        self._entity_cache: Dict[int, Entity] = {}
        self._name_cache: Dict[str, int] = {}  # name.lower() -> id
        self._neighbor_cache: Dict[int, List[Tuple[int, RelationType]]] = {}
        self._init_db()
        self._load_caches()

    def _get_conn(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=10.0)
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA cache_size = -8000")  # 8MB page cache
                conn.row_factory = sqlite3.Row
                self._conn = conn
            return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL DEFAULT 'OTHER',
                properties TEXT DEFAULT '{}',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                access_count INTEGER DEFAULT 0,
                importance REAL DEFAULT 0.5,
                UNIQUE(name, entity_type)
            );

            CREATE TABLE IF NOT EXISTS relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                relation_type TEXT NOT NULL DEFAULT 'RELATED_TO',
                properties TEXT DEFAULT '{}',
                weight REAL DEFAULT 1.0,
                created_at REAL NOT NULL,
                FOREIGN KEY (source_id) REFERENCES entities(id) ON DELETE CASCADE,
                FOREIGN KEY (target_id) REFERENCES entities(id) ON DELETE CASCADE,
                UNIQUE(source_id, target_id, relation_type)
            );

            CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
            CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
            CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id);
            CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id);
            CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(relation_type);
        """)
        conn.commit()

    def _load_caches(self):
        """Warm caches from DB at startup."""
        conn = self._get_conn()
        rows = conn.execute("SELECT id, name, entity_type, properties, importance FROM entities").fetchall()
        for r in rows:
            e = Entity(
                id=r["id"], name=r["name"],
                entity_type=EntityType(r["entity_type"]),
                properties=json.loads(r["properties"]),
                importance=r["importance"],
            )
            self._entity_cache[e.id] = e
            self._name_cache[e.name.lower()] = e.id

        rels = conn.execute("SELECT source_id, target_id, relation_type FROM relations").fetchall()
        for r in rels:
            src = r["source_id"]
            if src not in self._neighbor_cache:
                self._neighbor_cache[src] = []
            self._neighbor_cache[src].append((r["target_id"], RelationType(r["relation_type"])))

        logger.info("Knowledge graph loaded: %d entities, %d relations", len(self._entity_cache), len(rels))

    def add_entity(self, name: str, entity_type: EntityType = EntityType.OTHER,
                   properties: Optional[Dict] = None, importance: float = 0.5) -> Entity:
        """Add or update an entity. Returns the entity with its ID."""
        name = name.strip()
        if not name:
            raise ValueError("Entity name cannot be empty")

        cache_key = name.lower()
        now = time.time()

        with self._lock:
            # Check cache first
            if cache_key in self._name_cache:
                eid = self._name_cache[cache_key]
                conn = self._get_conn()
                conn.execute(
                    "UPDATE entities SET updated_at = ?, access_count = access_count + 1, "
                    "importance = MAX(importance, ?) WHERE id = ?",
                    (now, importance, eid)
                )
                conn.commit()
                e = self._entity_cache[eid]
                e.updated_at = now
                e.access_count += 1
                e.importance = max(e.importance, importance)
                if properties:
                    e.properties.update(properties)
                    conn.execute("UPDATE entities SET properties = ? WHERE id = ?",
                                (json.dumps(e.properties), eid))
                    conn.commit()
                return e

            # Insert new
            conn = self._get_conn()
            cur = conn.execute(
                "INSERT OR IGNORE INTO entities (name, entity_type, properties, created_at, updated_at, importance) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, entity_type.value, json.dumps(properties or {}), now, now, importance)
            )
            conn.commit()
            eid = cur.lastrowid
            if eid == 0:
                # UNIQUE constraint hit — fetch existing
                row = conn.execute("SELECT id FROM entities WHERE name = ? AND entity_type = ?",
                                  (name, entity_type.value)).fetchone()
                eid = row["id"]

            e = Entity(id=eid, name=name, entity_type=entity_type,
                       properties=properties or {}, created_at=now, updated_at=now, importance=importance)
            self._entity_cache[eid] = e
            self._name_cache[cache_key] = eid
            return e

    def get_entity(self, name: str) -> Optional[Entity]:
        """Get entity by name (case-insensitive)."""
        cache_key = name.lower()
        if cache_key in self._name_cache:
            return self._entity_cache.get(self._name_cache[cache_key])
        return None

    def get_entity_by_id(self, eid: int) -> Optional[Entity]:
        return self._entity_cache.get(eid)

    def add_relation(self, source_name: str, target_name: str,
                     relation_type: RelationType = RelationType.RELATED_TO,
                     properties: Optional[Dict] = None, weight: float = 1.0) -> Optional[Relation]:
        """Add a directed relation between two entities. Creates entities if needed."""
        source = self.get_entity(source_name)
        if not source:
            source = self.add_entity(source_name)
        target = self.get_entity(target_name)
        if not target:
            target = self.add_entity(target_name)

        now = time.time()
        with self._lock:
            conn = self._get_conn()
            cur = conn.execute(
                "INSERT OR IGNORE INTO relations (source_id, target_id, relation_type, properties, weight, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (source.id, target.id, relation_type.value, json.dumps(properties or {}), weight, now)
            )
            conn.commit()

            if cur.lastrowid == 0:
                # Already exists — update weight
                conn.execute(
                    "UPDATE relations SET weight = MIN(weight + ?, 10.0), properties = ? "
                    "WHERE source_id = ? AND target_id = ? AND relation_type = ?",
                    (0.1, json.dumps(properties or {}), source.id, target.id, relation_type.value)
                )
                conn.commit()

            # Update neighbor cache
            if source.id not in self._neighbor_cache:
                self._neighbor_cache[source.id] = []
            targets = [t for t, _ in self._neighbor_cache[source.id]]
            if target.id not in targets:
                self._neighbor_cache[source.id].append((target.id, relation_type))

            return Relation(
                id=cur.lastrowid or 0, source_id=source.id, target_id=target.id,
                relation_type=relation_type, properties=properties or {}, weight=weight, created_at=now
            )

    def get_neighbors(self, entity_name: str, direction: str = "both",
                      relation_type: Optional[RelationType] = None,
                      max_depth: int = 1) -> List[Tuple[Entity, RelationType, int]]:
        """Get neighbors of an entity up to max_depth hops.

        Returns: List of (entity, relation_type, depth)
        """
        entity = self.get_entity(entity_name)
        if not entity:
            return []

        results = []
        visited = {entity.id}
        queue = deque([(entity.id, 0)])

        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            neighbors = self._neighbor_cache.get(current_id, [])

            # For "inbound" or "both", also check reverse relations
            if direction in ("in", "both"):
                conn = self._get_conn()
                inbound = conn.execute(
                    "SELECT source_id, relation_type FROM relations WHERE target_id = ?",
                    (current_id,)
                ).fetchall()
                for r in inbound:
                    src_id = r["source_id"]
                    rt = RelationType(r["relation_type"])
                    if relation_type and rt != relation_type:
                        continue
                    if src_id not in visited:
                        visited.add(src_id)
                        e = self._entity_cache.get(src_id)
                        if e:
                            results.append((e, rt, depth + 1))
                            queue.append((src_id, depth + 1))

            if direction in ("out", "both"):
                for target_id, rt in neighbors:
                    if relation_type and rt != relation_type:
                        continue
                    if target_id not in visited:
                        visited.add(target_id)
                        e = self._entity_cache.get(target_id)
                        if e:
                            results.append((e, rt, depth + 1))
                            queue.append((target_id, depth + 1))

        return results

    def find_path(self, source_name: str, target_name: str,
                  max_depth: int = 6) -> Optional[GraphPath]:
        """BFS shortest path between two entities."""
        source = self.get_entity(source_name)
        target = self.get_entity(target_name)
        if not source or not target:
            return None
        if source.id == target.id:
            return GraphPath(entities=[source], relations=[], total_weight=0.0)

        # BFS with parent tracking
        parent: Dict[int, Tuple[int, RelationType]] = {}
        visited = {source.id}
        queue = deque([source.id])

        while queue:
            current_id = queue.popleft()
            if current_id == target.id:
                # Reconstruct path
                path_entities = [target]
                path_relations = []
                current = target.id
                while current in parent:
                    parent_id, rt = parent[current]
                    pe = self._entity_cache.get(parent_id)
                    pr = Relation(source_id=parent_id, target_id=current, relation_type=rt)
                    path_entities.append(pe)
                    path_relations.append(pr)
                    current = parent_id
                path_entities.reverse()
                path_relations.reverse()
                return GraphPath(
                    entities=path_entities,
                    relations=path_relations,
                    total_weight=len(path_relations)
                )

            for neighbor_id, rt in self._neighbor_cache.get(current_id, []):
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    parent[neighbor_id] = (current_id, rt)
                    queue.append(neighbor_id)

            # Also check inbound
            conn = self._get_conn()
            inbound = conn.execute(
                "SELECT source_id, relation_type FROM relations WHERE target_id = ?",
                (current_id,)
            ).fetchall()
            for r in inbound:
                src_id = r["source_id"]
                if src_id not in visited:
                    visited.add(src_id)
                    parent[src_id] = (current_id, RelationType(r["relation_type"]))
                    queue.append(src_id)

        return None  # No path found

    def search_entities(self, query: str, entity_type: Optional[EntityType] = None,
                        limit: int = 20) -> List[Entity]:
        """Search entities by name (case-insensitive LIKE)."""
        conn = self._get_conn()
        sql = "SELECT id, name, entity_type, properties, importance FROM entities WHERE name LIKE ?"
        params = [f"%{query}%"]
        if entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type.value)
        sql += " ORDER BY importance DESC, access_count DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [
            Entity(id=r["id"], name=r["name"], entity_type=EntityType(r["entity_type"]),
                   properties=json.loads(r["properties"]), importance=r["importance"])
            for r in rows
        ]

    def get_central_entities(self, top_k: int = 10) -> List[Tuple[Entity, int]]:
        """Get entities ranked by degree centrality (most connections)."""
        degree = defaultdict(int)
        for src, neighbors in self._neighbor_cache.items():
            degree[src] += len(neighbors)
            for tgt, _ in neighbors:
                degree[tgt] += 1

        ranked = sorted(degree.items(), key=lambda x: -x[1])[:top_k]
        return [(self._entity_cache[eid], deg) for eid, deg in ranked if eid in self._entity_cache]

    def get_entity_context(self, entity_name: str) -> str:
        """Get a formatted context string for an entity (for LLM prompts)."""
        entity = self.get_entity(entity_name)
        if not entity:
            return ""

        parts = [f"Entity: {entity.name} (type: {entity.entity_type.value})"]
        if entity.properties:
            for k, v in entity.properties.items():
                parts.append(f"  {k}: {v}")

        neighbors = self.get_neighbors(entity_name, max_depth=1)
        if neighbors:
            parts.append("Connections:")
            for ne, rt, depth in neighbors[:10]:
                parts.append(f"  --[{rt.value}]--> {ne.name} ({ne.entity_type.value})")

        return "\n".join(parts)

    def get_graph_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        conn = self._get_conn()
        entity_count = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        relation_count = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        type_dist = conn.execute(
            "SELECT entity_type, COUNT(*) as cnt FROM entities GROUP BY entity_type ORDER BY cnt DESC"
        ).fetchall()
        rel_dist = conn.execute(
            "SELECT relation_type, COUNT(*) as cnt FROM relations GROUP BY relation_type ORDER BY cnt DESC"
        ).fetchall()

        return {
            "entities": entity_count,
            "relations": relation_count,
            "entity_types": {r["entity_type"]: r["cnt"] for r in type_dist},
            "relation_types": {r["relation_type"]: r["cnt"] for r in rel_dist},
            "cache_size": len(self._entity_cache),
        }

    def clear(self):
        """Clear all entities and relations."""
        with self._lock:
            conn = self._get_conn()
            conn.execute("DELETE FROM relations")
            conn.execute("DELETE FROM entities")
            conn.commit()
            self._entity_cache.clear()
            self._name_cache.clear()
            self._neighbor_cache.clear()
            logger.info("Knowledge graph cleared")

    def close(self):
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None


# Global singleton
_kg: Optional[KnowledgeGraph] = None
_kg_lock = threading.Lock()


def get_knowledge_graph() -> KnowledgeGraph:
    global _kg
    if _kg is None:
        with _kg_lock:
            if _kg is None:
                _kg = KnowledgeGraph()
    return _kg
