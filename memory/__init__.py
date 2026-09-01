"""JARVIS MK-X Memory - Persistent memory storage + optimization.

Unified memory API (memory/api.py): every write/read goes through
``get_mem()`` → ``MemoryAPI`` → ``MemoryController`` → the backends.
Legacy facades (memory_manager JSON, decision memory, project knowledge)
remain available for direct use.
"""

from memory.api import Mem, MemoryAPI, get_mem
from memory.decision_memory import DecisionMemory, get_decision_memory
from memory.memory_optimizer import MemoryOptimizer, get_memory_optimizer
from memory.project_knowledge import ProjectKnowledge, get_project_knowledge
from memory.store import MemoryEntry, MemoryStore
from memory.tiered_store import TieredMemoryStore, get_tiered_store
from memory.user_profile import (
    USER_PROFILE,
    ensure_user_profile_in_memory,
    get_user_profile,
    inject_into_memory_api,
)
from memory.vector_store import VectorMemoryStore

__all__ = [
    "MemoryStore",
    "MemoryEntry",
    "MemoryOptimizer",
    "get_memory_optimizer",
    "TieredMemoryStore",
    "get_tiered_store",
    "VectorMemoryStore",
    "DecisionMemory",
    "get_decision_memory",
    "ProjectKnowledge",
    "get_project_knowledge",
    "Mem",
    "MemoryAPI",
    "get_mem",
    "USER_PROFILE",
    "get_user_profile",
    "inject_into_memory_api",
    "ensure_user_profile_in_memory",
]
