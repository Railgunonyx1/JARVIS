"""Sprint 18 -- Memory v2: authority-aware, project-scoped, with supersession and handoff.

Extends the existing memory system with:
- Memory provenance (source, confidence, verified_at)
- Authority levels (rule > decision > procedure > session)
- Supersession chains (A -> B -> C, C=current, A=obsolete)
- Project-scoped retrieval
- Handoff packet generation for cross-session continuity
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any


class AuthorityLevel(enum.Enum):
    """How much weight this memory carries when retrieved."""
    RULE = "rule"           # Mandatory constraint (never override)
    DECISION = "decision"   # Deliberate choice (high weight)
    PROCEDURE = "procedure" # How-to knowledge (medium weight)
    GOTCHA = "gotcha"       # Known pitfall (medium-high weight)
    SESSION = "session"     # Historical observation (low weight, untrusted as instruction)


class MemoryStatus(enum.Enum):
    CURRENT = "current"
    SUPERSEDED = "superseded"
    OBSOLETE = "obsolete"


@dataclass(frozen=True)
class MemoryProvenance:
    """Where this memory came from and how trustworthy it is."""
    source: str = ""              # e.g. "user", "observed-config", "test-run"
    confidence: float = 1.0       # 0.0–1.0
    verified_at: float = 0.0      # timestamp of last verification
    evidence: str = ""            # supporting evidence or link


@dataclass
class AuthorityMemory:
    """A single memory entry with full metadata."""
    id: str = ""
    content: str = ""
    authority: AuthorityLevel = AuthorityLevel.SESSION
    project: str = ""
    status: MemoryStatus = MemoryStatus.CURRENT
    provenance: MemoryProvenance = field(default_factory=MemoryProvenance)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    superseded_by: str = ""       # id of the memory that replaced this one
    tags: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()

    def supersede(self, new_id: str) -> None:
        """Mark this memory as superseded by another."""
        object.__setattr__(self, "status", MemoryStatus.SUPERSEDED)
        object.__setattr__(self, "superseded_by", new_id)
        object.__setattr__(self, "updated_at", time.time())

    def obsolete(self) -> None:
        object.__setattr__(self, "status", MemoryStatus.OBSOLETE)
        object.__setattr__(self, "updated_at", time.time())


class AuthorityMemoryStore:
    """In-memory store with authority-aware retrieval and supersession.

    This layer sits above the existing KV/vector stores and adds
    provenance, authority ranking, and supersession logic.
    """

    def __init__(self) -> None:
        self._memories: dict[str, AuthorityMemory] = {}
        self._project_index: dict[str, set[str]] = {}  # project -> {ids}
        self._tag_index: dict[str, set[str]] = {}       # tag -> {ids}
        self._entity_index: dict[str, set[str]] = {}    # entity -> {ids}

    def store(self, memory: AuthorityMemory) -> str:
        if not memory.id:
            memory.id = f"mem_{int(time.time()*1000)}_{len(self._memories)}"
        self._memories[memory.id] = memory
        if memory.project:
            self._project_index.setdefault(memory.project, set()).add(memory.id)
        for tag in memory.tags:
            self._tag_index.setdefault(tag, set()).add(memory.id)
        for entity in memory.entities:
            self._entity_index.setdefault(entity.lower(), set()).add(memory.id)
        return memory.id

    def get(self, memory_id: str) -> AuthorityMemory | None:
        return self._memories.get(memory_id)

    def supersede(self, old_id: str, new_memory: AuthorityMemory) -> str:
        """Replace a memory and mark the old one as superseded."""
        old = self._memories.get(old_id)
        if old:
            old.supersede(new_memory.id)
        new_id = self.store(new_memory)
        return new_id

    def retrieve(
        self,
        query: str = "",
        project: str = "",
        authority_min: AuthorityLevel = AuthorityLevel.SESSION,
        include_superseded: bool = False,
        limit: int = 10,
    ) -> list[AuthorityMemory]:
        """Authority-aware retrieval. Returns only current memories above the
        minimum authority level, ranked by authority then confidence."""
        authority_order = list(AuthorityLevel)
        min_idx = authority_order.index(authority_min) if authority_min in authority_order else 0

        candidates = []
        query_lower = query.lower()

        for mem in self._memories.values():
            if mem.status == MemoryStatus.OBSOLETE:
                continue
            if not include_superseded and mem.status == MemoryStatus.SUPERSEDED:
                continue
            mem_idx = authority_order.index(mem.authority)
            if mem_idx < min_idx:
                continue
            if project and mem.project and mem.project != project:
                continue
            # Simple text matching (could be enhanced with vector search)
            if query_lower and query_lower not in mem.content.lower():
                # Check entity index
                entity_match = any(
                    query_lower in e for e in mem.entities
                )
                if not entity_match:
                    continue
            candidates.append(mem)

        # Sort: higher authority first, then higher confidence
        candidates.sort(
            key=lambda m: (authority_order.index(m.authority), m.provenance.confidence),
            reverse=True,
        )
        return candidates[:limit]

    def recall_decisions(self, project: str = "", limit: int = 10) -> list[AuthorityMemory]:
        return self.retrieve(
            project=project,
            authority_min=AuthorityLevel.DECISION,
            include_superseded=False,
            limit=limit,
        )

    def get_stats(self) -> dict[str, Any]:
        by_authority = {}
        by_status = {}
        for mem in self._memories.values():
            by_authority[mem.authority.value] = by_authority.get(mem.authority.value, 0) + 1
            by_status[mem.status.value] = by_status.get(mem.status.value, 0) + 1
        return {
            "total": len(self._memories),
            "by_authority": by_authority,
            "by_status": by_status,
            "projects": len(self._project_index),
            "entities": len(self._entity_index),
        }


@dataclass(frozen=True)
class HandoffPacket:
    """Cross-session handoff: captures the essential context for continuity."""
    project: str = ""
    objective: str = ""
    completed: tuple[str, ...] = ()
    current: str = ""
    failed_approaches: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    files_changed: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    test_status: str = ""
    next_action: str = ""
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""

    def to_markdown(self) -> str:
        lines = [
            "# JARVIS Handoff",
            "",
            f"**Project:** {self.project}",
            f"**Objective:** {self.objective}",
            f"**Session:** {self.session_id}",
            "",
        ]
        if self.completed:
            lines.append("## Completed")
            for c in self.completed:
                lines.append(f"- [x] {c}")
            lines.append("")
        if self.current:
            lines.append(f"## Current\n{self.current}\n")
        if self.failed_approaches:
            lines.append("## Failed Approaches")
            for f in self.failed_approaches:
                lines.append(f"- [ ] {f}")
            lines.append("")
        if self.decisions:
            lines.append("## Key Decisions")
            for d in self.decisions:
                lines.append(f"- {d}")
            lines.append("")
        if self.files_changed:
            lines.append(f"## Files Changed: {', '.join(self.files_changed)}\n")
        if self.open_questions:
            lines.append("## Open Questions")
            for q in self.open_questions:
                lines.append(f"- {q}")
            lines.append("")
        if self.test_status:
            lines.append(f"## Test Status\n{self.test_status}\n")
        if self.next_action:
            lines.append(f"## Next Action\n{self.next_action}\n")
        return "\n".join(lines)


class HandoffBuilder:
    """Builds a HandoffPacket from agent state and memory."""

    def __init__(self, memory_store: AuthorityMemoryStore | None = None):
        self._memory = memory_store

    def build(
        self,
        project: str = "",
        objective: str = "",
        completed: tuple[str, ...] = (),
        current: str = "",
        failed_approaches: tuple[str, ...] = (),
        files_changed: tuple[str, ...] = (),
        open_questions: tuple[str, ...] = (),
        test_status: str = "",
        next_action: str = "",
        session_id: str = "",
    ) -> HandoffPacket:
        decisions = []
        if self._memory:
            for mem in self._memory.recall_decisions(project=project, limit=5):
                decisions.append(mem.content)

        return HandoffPacket(
            project=project,
            objective=objective,
            completed=completed,
            current=current,
            failed_approaches=failed_approaches,
            decisions=tuple(decisions) if decisions else (),
            files_changed=files_changed,
            open_questions=open_questions,
            test_status=test_status,
            next_action=next_action,
            session_id=session_id,
        )
