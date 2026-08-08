"""Memory object model — the shared data shape for everything the memory
system stores and retrieves (Stage 1B/1C).

One class, ``MemoryItem``, is the foundation: every write funnels through
it and every retrieval returns it. Memory *types* (1C) are just the ``type``
field plus the helpers in ``memory.api``, so the model stays small while the
system grows semantic/episodic/procedural/decision/project memory.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# Memory types (Stage 1C). Decision/project entries map onto real backends
# (DecisionMemory / ProjectKnowledge); semantic/episodic/procedural/note live
# in the KV + vector stores tagged by type.
SEMANTIC = "semantic"        # facts: "JARVIS uses sqlite-vec."
EPISODIC = "episodic"        # events: "Optimized the memory module in Aug 2026."
PROCEDURAL = "procedural"    # methods: "When auditing: read, find, benchmark, fix."
DECISION = "decision"        # what was decided and why (DecisionMemory).
PROJECT = "project"          # per-project sections: architecture/decisions/bugs/...
PREFERENCE = "preference"    # user preferences.
IDENTITY = "identity"        # user identity facts.
RELATIONSHIP = "relationship"
NOTE = "note"

ALL_TYPES = (
    SEMANTIC, EPISODIC, PROCEDURAL, DECISION, PROJECT,
    PREFERENCE, IDENTITY, RELATIONSHIP, NOTE,
)

# Per-project memory sections (Stage 1C #5).
PROJECT_SECTIONS = ("architecture", "decisions", "bugs", "benchmarks", "todo", "research")


@dataclass
class MemoryItem:
    """A single unit of memory, regardless of which backend persists it."""

    id: Optional[str] = None                 # stable logical key ("" or None until stored)
    content: str = ""                        # the actual remembered text
    type: str = SEMANTIC                     # MemoryType
    project: str = ""                        # project scope ("" = global)
    tags: List[str] = field(default_factory=list)
    importance: float = 0.5                  # 0..1 — "does this matter?"
    confidence: float = 1.0                  # 0..1 — "how sure are we?"
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0                    # prior usefulness signal
    embedding: Optional[List[float]] = None  # precomputed vector (optional)
    source: str = ""                         # session/conversation/syslog origin
    relationships: List[str] = field(default_factory=list)  # related memory keys/entities
    metadata: Dict[str, Any] = field(default_factory=dict)  # type-specific extras

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        allowed = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class KnowledgeTriple:
    """Entity-relation-entity triple for the lightweight graph (GraphRAG)."""

    subject: str
    relation: str
    obj: str
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeTriple":
        return cls(**data)
