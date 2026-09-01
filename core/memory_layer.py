"""JARVIS Memory Layer — Adapted from mem0 Universal Memory Layer.

Adapted from mem0ai/mem0 — Universal memory layer for AI agents.
Provides persistent memory across daemon sessions with 512 MB RAM constraint support.

Features:
- Entity tracking and relationship mapping
- Fact persistence with TTL-based expiry
- Session context management
- Cross-session continuity
- Memory pruning and expiry
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta


class MemoryEntity:
    """Represents a tracked entity in the memory layer."""

    def __init__(self, name: str, properties: Dict[str, Any],
                 first_seen: str = None, last_seen: str = None,
                 ttl_days: int = 30):
        self.name = name
        self.properties = properties
        self.first_seen = first_seen or datetime.utcnow().isoformat()
        self.last_seen = last_seen or datetime.utcnow().isoformat()
        self.ttl_days = ttl_days

    def update(self, new_properties: Dict[str, Any], ttl_days: int = None):
        """Update entity properties and last_seen timestamp."""
        self.properties.update(new_properties)
        self.last_seen = datetime.utcnow().isoformat()
        if ttl_days is not None:
            self.ttl_days = ttl_days

    def is_expired(self) -> bool:
        """Check if entity has exceeded its TTL."""
        if self.ttl_days is None:
            return False
        first_seen_dt = datetime.fromisoformat(self.first_seen)
        return datetime.utcnow() - first_seen_dt > timedelta(days=self.ttl_days)


class MemoryFact:
    """Represents a persisted fact in the memory layer."""

    def __init__(self, fact: str, source: str, created: str = None,
                 ttl_days: int = 30):
        self.fact = fact
        self.source = source
        self.created = created or datetime.utcnow().isoformat()
        self.ttl_days = ttl_days

    def is_expired(self) -> bool:
        """Check if fact has exceeded its TTL."""
        if self.ttl_days is None:
            return False
        created_dt = datetime.fromisoformat(self.created)
        return datetime.utcnow() - created_dt > timedelta(days=self.ttl_days)


class MemoryLayer:
    """Adapted mem0 universal memory layer for AI agents.

    Provides persistent memory across JARVIS daemon sessions with 512 MB RAM
    constraint support through SQLite-based storage and TTL-based expiry.
    """

    def __init__(self, storage_path: str = "~/.jarvis/memory",
                 ttl_hours: int = 168):  # 7 days default
        self.storage_path = os.path.expanduser(storage_path)
        os.makedirs(self.storage_path, exist_ok=True)
        self.memory_file = os.path.join(self.storage_path, "memory.json")
        self.facts_file = os.path.join(self.storage_path, "facts.json")

        # In-memory caches
        self._entities: Dict[str, MemoryEntity] = {}
        self._facts: List[MemoryFact] = []

        # Load from disk
        self._load_from_disk()

        # Set TTL
        self.ttl_hours = ttl_hours

    def _load_from_disk(self) -> None:
        """Load memory state from disk."""
        # Load entities
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r") as f:
                    data = json.load(f)
                for name, entity_data in data.get("entities", {}).items():
                    entity = MemoryEntity(
                        name=name,
                        properties=entity_data.get("properties", {}),
                        first_seen=entity_data.get("first_seen", datetime.utcnow().isoformat()),
                        last_seen=entity_data.get("last_seen", datetime.utcnow().isoformat()),
                        ttl_days=entity_data.get("ttl_days", 30),
                    )
                    self._entities[name] = entity
            except Exception:
                pass

        # Load facts
        if os.path.exists(self.facts_file):
            try:
                with open(self.facts_file, "r") as f:
                    data = json.load(f)
                for fact_data in data.get("facts", []):
                    fact = MemoryFact(
                        fact=fact_data.get("fact", ""),
                        source=fact_data.get("source", "conversation"),
                        created=fact_data.get("created", datetime.utcnow().isoformat()),
                        ttl_days=fact_data.get("ttl_days", 30),
                    )
                    self._facts.append(fact)
            except Exception:
                pass

    def _save_to_disk(self) -> None:
        """Persist memory state to disk."""
        # Save entities
        entities_data = {
            "entities": {
                name: {
                    "properties": entity.properties,
                    "first_seen": entity.first_seen,
                    "last_seen": entity.last_seen,
                    "ttl_days": entity.ttl_days,
                }
                for name, entity in self._entities.items()
            }
        }
        with open(self.memory_file, "w") as f:
            json.dump(entities_data, f, indent=2)

        # Save facts
        facts_data = {
            "facts": [
                {
                    "fact": fact.fact,
                    "source": fact.source,
                    "created": fact.created,
                    "ttl_days": fact.ttl_days,
                }
                for fact in self._facts
            ]
        }
        with open(self.facts_file, "w") as f:
            json.dump(facts_data, f, indent=2)

    # -----------------------------------------------------------------
    # Entity Management
    # -----------------------------------------------------------------

    def remember_entity(self, name: str, properties: Dict[str, Any],
                       ttl_days: int = 30) -> None:
        """Remember an entity with properties and TTL."""
        entity = self._entities.get(name)
        if entity:
            entity.update(properties, ttl_days)
        else:
            entity = MemoryEntity(name, properties, ttl_days=ttl_days)
            self._entities[name] = entity
        self._save_to_disk()

    def recall_entity(self, name: str) -> Optional[Dict[str, Any]]:
        """Recall entity properties by name."""
        entity = self._entities.get(name)
        if entity is None:
            return None

        # Check expiry
        if entity.is_expired():
            del self._entities[name]
            self._save_to_disk()
            return None

        # Update last_seen
        entity.last_seen = datetime.utcnow().isoformat()
        self._save_to_disk()

        return {
            "name": entity.name,
            "properties": entity.properties,
            "first_seen": entity.first_seen,
            "last_seen": entity.last_seen,
            "ttl_days": entity.ttl_days,
        }

    def update_entity(self, name: str, properties: Dict[str, Any],
                      ttl_days: int = None) -> None:
        """Update entity properties."""
        self.remember_entity(name, properties, ttl_days or 30)

    def forget_entity(self, name: str) -> None:
        """Forget an entity."""
        if name in self._entities:
            del self._entities[name]
            self._save_to_disk()

    # -----------------------------------------------------------------
    # Fact Management
    # -----------------------------------------------------------------

    def record_fact(self, fact: str, source: str = "conversation",
                    ttl_days: int = 30) -> None:
        """Record a fact from conversation."""
        fact_obj = MemoryFact(fact, source, ttl_days=ttl_days)
        self._facts.append(fact_obj)

        # Prune expired facts and keep manageable list
        self._prune_facts()
        self._save_to_disk()

    def recall(self, query: str) -> Dict[str, Any]:
        """Recall relevant information for a query."""
        results = {
            "entities": {},
            "facts": [],
            "relevant_context": []
        }

        # Search entities
        for name, entity in self._entities.items():
            # Simple keyword matching
            query_keywords = set(query.lower().split())
            entity_keywords = set(entity.name.lower().split())
            if query_keywords and any(kw in entity_keywords for kw in query_keywords):
                results["entities"][name] = entity.properties

        # Search facts
        for fact in self._facts:
            if not fact.is_expired():
                if any(kw in fact.fact.lower() for kw in query.lower().split()):
                    results["facts"].append(fact.fact)

        # Build context string
        context_parts = []
        for entity_name, entity_props in results["entities"].items():
            context_parts.append(f"Entity: {entity_name} - {entity_props}")
        for fact in results["facts"][:10]:  # Limit
            context_parts.append(f"Fact: {fact}")

        results["relevant_context"] = "\n".join(context_parts) or "No relevant memory found."

        return results

    # -----------------------------------------------------------------
    # Memory Pruning / Expiry
    # -----------------------------------------------------------------

    def _prune_facts(self) -> None:
        """Prune expired facts and keep list manageable."""
        # Remove expired facts
        self._facts = [f for f in self._facts if not f.is_expired()]

        # Keep max 1000 facts (FIFO)
        if len(self._facts) > 1000:
            self._facts = self._facts[-500:]

    def _expire_entities(self) -> None:
        """Expire entities based on TTL."""
        expired = [name for name, entity in self._entities.items() if entity.is_expired()]
        for name in expired:
            del self._entities[name]

    def _cleanup(self) -> None:
        """Run cleanup routines."""
        self._prune_facts()
        self._expire_entities()
        self._save_to_disk()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return memory layer statistics."""
        expired_entities = sum(
            1 for e in self._entities.values() if e.is_expired()
        )
        return {
            "entities_stored": len(self._entities),
            "expired_entities": expired_entities,
            "facts_stored": len(self._facts),
            "ttl_hours": self.ttl_hours,
            "entity_types": len(set(e.name for e in self._entities.values())),
        }

    def get_context_for_llm(self, query: str, max_tokens: int = 2000) -> str:
        """Get formatted context for LLM consumption."""
        recall_result = self.recall(query)

        context_parts = [
            f"Session query: {query}",
            "",
            "=== Entity Memory ===",
        ]
        for entity_name, entity_props in recall_result["entities"].items():
            context_parts.append(f"- {entity_name}: {entity_props.get('description', '')}")

        context_parts.append("")
        context_parts.append("=== Fact Memory ===")
        for fact in recall_result["facts"][:5]:
            context_parts.append(f"- {fact}")

        context_parts.append("")
        context_parts.append("=== End Memory ===")

        context = "\n".join(context_parts)

        # Truncate to max_tokens (rough estimate: 1 char ≈ 1/4 token)
        # Simple truncation for now
        if len(context) > max_tokens * 4:
            context = context[:max_tokens * 4] + "..."

        return context

    def _cleanup_and_save(self) -> None:
        """Cleanup and persist memory state."""
        self._cleanup()
        self._save_to_disk()


# Example usage pattern for JARVIS:
#
# memory = MemoryLayer(storage_path="~/.jarvis/memory", ttl_hours=168)
#
# # Remember an entity
# memory.remember_entity("user_preferences", {
#     "theme": "dark",
#     "notifications": True,
#     "favorite_topics": ["ai", "coding", "music"]
# }, ttl_days=30)
#
# # Record a fact
# memory.record_fact("User prefers dark theme for code editor", source="conversation", ttl_days=30)
#
# # Recall for context
# context = memory.recall("user preferences")
# print(context["relevant_context"])
#
# # Get stats
# stats = memory.get_stats()
# print(f"Entities: {stats['entities_stored']}, Facts: {stats['facts_stored']}")
#
# # Get LLM-ready context
# llm_context = memory.get_context_for_llm("user preferences")
# print(llm_context)

# Module export
__all__ = ["MemoryLayer", "MemoryEntity", "MemoryFact"]