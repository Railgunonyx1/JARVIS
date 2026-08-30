"""DeepSeek Memory Module — Persistent storage for non-personal information.

This module survives session restarts and provides basic CRUD operations
for non-personal information. Uses JSON file for persistence.

Features:
- Adds/removes/remembers information across sessions
- Stores data in ~/.deepseek_memory.json
- Session-independent (works after new sessions launch)
- No personal info filtering (store what you need, be responsible)
- Simple, reliable persistence

"""
from __future__ import annotations

from typing import Any, Optional
import json
import os

# Path to persistent storage (user home directory)
_STORAGE_PATH = os.path.expanduser("~/.deepseek_memory.json")


class DeepSeekMemory:
    """Persistent memory for DeepSeek harness across sessions."""

    def __init__(self, storage_path: str = _STORAGE_PATH) -> None:
        self.storage_path = storage_path
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load existing memory from disk."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        """Save memory to disk."""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def add(self, key: str, value: Any, *, category: str = "general") -> bool:
        """Add information to memory.

        Args:
            key: Memory key
            value: Value to store
            category: Category for organization

        Returns:
            True if stored successfully
        """
        self._data[key] = {
            "value": value,
            "category": category,
            "original_type": "normal",
            "access_count": 0,
        }
        self._save()
        return True

    def remove(self, key: str) -> bool:
        """Remove information from memory by key.

        Args:
            key: The memory key to remove

        Returns:
            True if key was found and removed, False otherwise
        """
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def recall(self, key: str) -> Optional[dict[str, Any]]:
        """Retrieve information from memory by key.

        Args:
            key: The memory key to look up

        Returns:
            Memory entry dict, or None if not found
        """
        if key in self._data:
            entry = self._data[key]
            entry["access_count"] = entry.get("access_count", 0) + 1
            self._save()
            return entry
        return None

    def list_all(self) -> list[dict[str, Any]]:
        """List all stored memory entries.

        Returns:
            List of dicts with "key" and "entry" keys, sorted by access count
        """
        entries: list[dict[str, Any]] = []
        for key, entry in self._data.items():
            entries.append({"key": key, "entry": entry})
        # Sort by access count (most used first)
        entries.sort(key=lambda x: x["entry"].get("access_count", 0), reverse=True)
        return entries

    def clear(self) -> None:
        """Clear all memory and reset storage file."""
        self._data = {}
        if os.path.exists(self.storage_path):
            os.remove(self.storage_path)

    def get_category(self, category: str) -> list[dict[str, Any]]:
        """Get all entries in a specific category.

        Args:
            category: The category filter

        Returns:
            List of memory entries in that category
        """
        return [
            entry["entry"]
            for entry in self._data.values()
            if entry.get("category") == category
        ]


# Global memory instance (singleton pattern)
_memory_instance: Optional[DeepSeekMemory] = None


def get_memory() -> DeepSeekMemory:
    """Get the global memory instance."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = DeepSeekMemory()
    return _memory_instance


# Convenience functions
def remember(key: str, value: Any, category: str = "general") -> bool:
    """Add information to memory (convenience function)."""
    return get_memory().add(key, value, category=category)


def recall(key: str) -> Optional[dict[str, Any]]:
    """Retrieve information from memory (convenience function)."""
    return get_memory().recall(key)


def forget(key: str) -> bool:
    """Remove information from memory (convenience function)."""
    return get_memory().remove(key)


# End of module