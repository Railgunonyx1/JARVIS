"""Memory API v1 — store, recall, search, delete memories.

All memory operations go through this API, never directly to MemoryStore.
"""
import logging
from typing import Any

from api.v1.models import MemoryItem

logger = logging.getLogger("jarvis.api.v1.memory")


class MemoryAPI:
    """Stable interface to JARVIS memory systems."""

    def __init__(self, memory_store, vector_memory=None,
                 config_service=None):
        self._store = memory_store
        self._vector = vector_memory
        self._config = config_service

    def store(self, item: MemoryItem) -> bool:
        try:
            self._store.store(
                key=item.key,
                value=item.value,
                category=item.tags[0] if item.tags else "general",
                importance=0.5,
            )
            return True
        except Exception as e:
            logger.error("MemoryAPI.store failed: %s", e)
            return False

    def recall(self, key: str) -> str | None:
        try:
            return self._store.recall(key)
        except Exception as e:
            logger.error("MemoryAPI.recall failed: %s", e)
            return None

    def search(self, query: str, top_k: int = 5) -> list[MemoryItem]:
        results = []
        try:
            if self._vector:
                matches = self._vector.search_similar(query, top_k=top_k)
                for m in matches:
                    results.append(MemoryItem(
                        key=m.get("key", ""),
                        value=m.get("text", ""),
                        tags=m.get("tags", []),
                        source="vector",
                        timestamp=m.get("timestamp", 0.0),
                    ))
        except Exception as e:
            logger.error("MemoryAPI.search failed: %s", e)
        return results

    def delete(self, key: str) -> bool:
        logger.warning("MemoryAPI.delete: not supported by current MemoryStore")
        return False

    def list_keys(self, prefix: str = "", limit: int = 100) -> list[str]:
        logger.warning("MemoryAPI.list_keys: not supported by current MemoryStore")
        return []

    def get_stats(self) -> dict[str, Any]:
        try:
            return self._store.get_stats()
        except Exception:
            return {}
