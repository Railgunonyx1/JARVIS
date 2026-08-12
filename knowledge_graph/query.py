"""
Graph Query Engine — Query interface for JARVIS Knowledge Graph.

Provides high-level query operations:
- Natural language graph queries
- Context-aware entity lookup
- Graph summarization for LLM prompts
- Path finding and reasoning
- Temporal queries (recent, old entities)

All queries return formatted strings for direct LLM injection.
"""

from __future__ import annotations

import logging
import time

from knowledge_graph.entity_extractor import EntityExtractor
from knowledge_graph.graph import EntityType, KnowledgeGraph, RelationType, get_knowledge_graph
from knowledge_graph.relation_mapper import RelationMapper

logger = logging.getLogger("jarvis.knowledge_graph.query")


class GraphQuery:
    """High-level query interface for the knowledge graph."""

    def __init__(self, graph: KnowledgeGraph | None = None):
        self.graph = graph or get_knowledge_graph()
        self.extractor = EntityExtractor()
        self.mapper = RelationMapper()

    def ingest_conversation(self, user_text: str, assistant_text: str,
                            intent_name: str = "", intent_entities: dict | None = None):
        """Extract and store entities/relations from a conversation turn."""
        # Extract from user text
        user_entities = self.extractor.extract_all(user_text, intent_name, intent_entities)
        for name, etype in user_entities:
            self.graph.add_entity(name, etype)

        # Extract from assistant text
        asst_entities = self.extractor.extract_from_text(assistant_text)
        for name, etype in asst_entities:
            self.graph.add_entity(name, etype)

        # Extract relations
        all_text = f"{user_text} {assistant_text}"
        relations = self.mapper.extract_all(all_text, intent_name, intent_entities)
        for src, tgt, rel_type, confidence in relations:
            if confidence >= 0.5:  # Only store confident relations
                self.graph.add_relation(src, tgt, rel_type, weight=confidence)

        # Store user-entity relation for context
        self.graph.add_relation("user", "Aayan", RelationType.KNOWS, weight=1.0)

    def ingest_memory(self, key: str, value: str, category: str = "general"):
        """Ingest a memory entry into the knowledge graph."""
        self.graph.add_entity(key, EntityType.CONCEPT, {"value": value, "category": category})
        self.graph.add_relation("user", key, RelationType.KNOWS, weight=0.8)

    def query_entity(self, name: str) -> str:
        """Get formatted context for an entity."""
        return self.graph.get_entity_context(name)

    def query_related(self, name: str, depth: int = 2) -> str:
        """Get all related entities up to depth hops."""
        neighbors = self.graph.get_neighbors(name, max_depth=depth)
        if not neighbors:
            return f"No information found about '{name}'."

        lines = [f"Knowledge about '{name}':"]
        for entity, rel_type, hop in neighbors:
            prefix = "  " * hop
            lines.append(f"{prefix}--[{rel_type.value}]--> {entity.name} ({entity.entity_type.value})")
            if entity.properties:
                for k, v in list(entity.properties.items())[:3]:
                    lines.append(f"{prefix}    {k}: {v}")

        return "\n".join(lines)

    def query_path(self, source: str, target: str) -> str:
        """Find and format the shortest path between two entities."""
        path = self.graph.find_path(source, target)
        if not path:
            return f"No path found between '{source}' and '{target}'."

        parts = []
        for i, entity in enumerate(path.entities):
            parts.append(entity.name)
            if i < len(path.relations):
                parts.append(f"  --[{path.relations[i].relation_type.value}]-->")

        return "Path: " + " ".join(parts)

    def query_by_type(self, entity_type: EntityType, limit: int = 20) -> str:
        """Get all entities of a specific type."""
        conn = self.graph._get_conn()
        rows = conn.execute(
            "SELECT name, entity_type, properties, importance FROM entities "
            "WHERE entity_type = ? ORDER BY importance DESC LIMIT ?",
            (entity_type.value, limit)
        ).fetchall()

        if not rows:
            return f"No {entity_type.value} entities found."

        lines = [f"{entity_type.value} entities:"]
        for r in rows:
            props = f" ({r['properties'][:50]}...)" if r['properties'] and r['properties'] != '{}' else ""
            lines.append(f"  - {r['name']}{props}")

        return "\n".join(lines)

    def query_recent(self, hours: float = 24.0, limit: int = 20) -> str:
        """Get recently accessed entities."""
        cutoff = time.time() - (hours * 3600)
        conn = self.graph._get_conn()
        rows = conn.execute(
            "SELECT name, entity_type, updated_at FROM entities "
            "WHERE updated_at > ? ORDER BY updated_at DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()

        if not rows:
            return "No recent entities found."

        lines = [f"Recent entities (last {int(hours)}h):"]
        for r in rows:
            age_h = (time.time() - r["updated_at"]) / 3600
            lines.append(f"  - {r['name']} ({r['entity_type']}, {age_h:.1f}h ago)")

        return "\n".join(lines)

    def query_central(self, top_k: int = 10) -> str:
        """Get most connected (central) entities."""
        central = self.graph.get_central_entities(top_k)
        if not central:
            return "No entities in graph."

        lines = ["Most connected entities:"]
        for entity, degree in central:
            lines.append(f"  - {entity.name} ({entity.entity_type.value}): {degree} connections")

        return "\n".join(lines)

    def summarize_for_context(self, max_entities: int = 30) -> str:
        """Generate a concise graph summary for LLM system prompts.

        Focuses on the most important/connected entities.
        """
        stats = self.graph.get_graph_stats()
        if stats["entities"] == 0:
            return ""

        lines = [f"[Knowledge Graph: {stats['entities']} entities, {stats['relations']} relations]"]

        # Central entities with their context
        central = self.graph.get_central_entities(min(max_entities, stats["entities"]))
        for entity, degree in central[:15]:
            neighbors = self.graph.get_neighbors(entity.name, max_depth=1)
            if neighbors:
                rel_names = [f"{e.name}({rt.value})" for e, rt, _ in neighbors[:5]]
                lines.append(f"  {entity.name} [{entity.entity_type.value}]: {', '.join(rel_names)}")
            else:
                lines.append(f"  {entity.name} [{entity.entity_type.value}]")

        # Type distribution summary
        if stats["entity_types"]:
            types_str = ", ".join(f"{k}:{v}" for k, v in list(stats["entity_types"].items())[:5])
            lines.append(f"  Types: {types_str}")

        return "\n".join(lines)

    def get_stats(self) -> str:
        """Get formatted graph statistics."""
        stats = self.graph.get_graph_stats()
        lines = [
            "Knowledge Graph Statistics:",
            f"  Entities: {stats['entities']}",
            f"  Relations: {stats['relations']}",
            f"  Cache size: {stats['cache_size']}",
        ]
        if stats["entity_types"]:
            lines.append("  Entity types:")
            for etype, count in stats["entity_types"].items():
                lines.append(f"    {etype}: {count}")
        if stats["relation_types"]:
            lines.append("  Relation types:")
            for rtype, count in stats["relation_types"].items():
                lines.append(f"    {rtype}: {count}")
        return "\n".join(lines)


def query_graph(query_type: str, **kwargs) -> str:
    """Convenience function for graph queries."""
    gq = GraphQuery()
    handlers = {
        "entity": lambda: gq.query_entity(kwargs.get("name", "")),
        "related": lambda: gq.query_related(kwargs.get("name", ""), kwargs.get("depth", 2)),
        "path": lambda: gq.query_path(kwargs.get("source", ""), kwargs.get("target", "")),
        "type": lambda: gq.query_by_type(EntityType(kwargs.get("type", "OTHER"))),
        "recent": lambda: gq.query_recent(kwargs.get("hours", 24.0)),
        "central": lambda: gq.query_central(kwargs.get("top_k", 10)),
        "summary": lambda: gq.summarize_for_context(kwargs.get("max_entities", 30)),
        "stats": lambda: gq.get_stats(),
    }
    handler = handlers.get(query_type)
    if handler:
        return handler()
    return f"Unknown query type: {query_type}. Available: {', '.join(handlers.keys())}"
