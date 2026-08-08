"""Memory API — the single entry point for the memory system (Stage 1A).

Everything goes through:

    memory.store()
    memory.retrieve()
    memory.update()
    memory.delete()

plus memory-type helpers (Stage 1C). ``get_mem()`` returns the process-wide
instance that the agent loop, CLI and cockpit already use, so the existing
``Mem`` surface keeps working while the internals are now a unified pipeline:

    API → Controller → KV / Vector / Decisions / Knowledge / Metadata / Tiers
                     ↘ Lifecycle worker (embeddings, extraction, graph, decay)

External code never touches the backends directly.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from memory.controller import MemoryController
from memory.models import (
    DECISION,
    EPISODIC,
    PROCEDURAL,
    PROJECT,
    PROJECT_SECTIONS,
    SEMANTIC,
    MemoryItem,
)

logger = logging.getLogger("jarvis.memory.api")

_instance: MemoryAPI | None = None
_instance_lock = threading.Lock()


class MemoryAPI:
    """Unified facade over MemoryController + background lifecycle."""

    def __init__(
        self,
        kv=None,
        vector=None,
        decisions=None,
        knowledge=None,
        mirror_json: bool = False,
    ):
        self._mirror_json = mirror_json
        self._controller = MemoryController(
            kv=kv, vector=vector, decisions=decisions, knowledge=knowledge,
        )

    @property
    def controller(self) -> MemoryController:
        return self._controller

    # Direct backend access — kept for legacy/tests. New code should use the
    # unified methods above, never these.
    @property
    def _kv(self):
        return self._controller._kv

    @property
    def _vector(self):
        return self._controller._vector

    @property
    def _decisions(self):
        return self._controller._decisions

    @property
    def _knowledge(self):
        return self._controller._knowledge

    # ── unified write path ────────────────────────────────────────────
    def store(
        self,
        content: str,
        key: str | None = None,
        type: str = SEMANTIC,
        project: str = "",
        tags: list[str] | None = None,
        importance: float | None = None,
        confidence: float = 1.0,
        source: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Store a memory; returns the stable key.

        When ``importance`` is omitted the ImportanceScorer estimates it.
        """
        if importance is None:
            importance = self._controller._scorer.score(content)
        item = MemoryItem(
            content=content, type=type, project=project,
            tags=list(tags or []), importance=importance, confidence=confidence,
            source=source, metadata=metadata or {},
        )
        return self._controller.store(item, key=key)

    def update(
        self,
        key: str,
        content: str | None = None,
        type: str | None = None,
        project: str | None = None,
        tags: list[str] | None = None,
        importance: float | None = None,
        **metadata: Any,
    ) -> str:
        """Overwrite an existing memory by key."""
        item = MemoryItem(
            content=content or "",
            type=type or SEMANTIC,
            project=project or "",
            tags=list(tags or []),
            importance=importance if importance is not None else 0.5,
            metadata=metadata,
        )
        return self._controller.update(key, item)

    def delete(self, key: str) -> bool:
        """Delete a memory by key from every backend."""
        return self._controller.delete(key)

    # ── memory types (Stage 1C) ───────────────────────────────────────
    def store_semantic(self, content: str, project: str = "", **kw) -> str:
        return self.store(content, type=SEMANTIC, project=project, **kw)

    def store_episodic(self, content: str, when: str | None = None,
                       project: str = "", **kw) -> str:
        text = f"{when}: {content}" if when else content
        return self.store(text, type=EPISODIC, project=project, **kw)

    def store_procedural(self, content: str, project: str = "", **kw) -> str:
        return self.store(content, type=PROCEDURAL, project=project, **kw)

    def store_decision(
        self,
        goal: str,
        decision: str = "completed",
        rationale: str = "",
        alternatives: list[str] | None = None,
        impact: str = "",
        related_files: list[str] | None = None,
        outcome: str = "",
        project: str = "",
        **kw,
    ) -> str:
        """Decision = what + why + alternatives + impact + date + related files."""
        meta = {
            "goal": goal, "decision": decision, "rationale": rationale,
            "outcome": outcome,
            "alternatives": list(alternatives or []),
            "impact": impact,
            "related_files": list(related_files or []),
            "date": time.strftime("%Y-%m-%d"),
        }
        return self.store(goal, type=DECISION, project=project, metadata=meta, **kw)

    def store_project_item(self, project: str, section: str, key: str,
                           content: str, **kw) -> str:
        """Store a per-project section item (architecture/decisions/bugs/...)."""
        if section not in PROJECT_SECTIONS:
            section = "notes"
        item_key = f"{project}:{section}:{key}"
        item = MemoryItem(
            content=content, type=PROJECT, project=project,
            tags=[section], id=item_key, metadata={"section": section},
        )
        stored = self._controller.store(item, key=item_key)
        self._controller._knowledge.set(project, f"{section}:{key}", content,
                                        category=f"project_{section}")
        return stored

    # ── conversation extraction pipeline ──────────────────────────────
    def process_conversation(self, text: str, source: str = "",
                             project: str = "") -> list[MemoryItem]:
        """Extract + persist facts from a conversation (background, HIGH)."""
        return self._controller.process_conversation(text, source=source, project=project)

    def flush_async(self) -> int:
        """Drain the background worker synchronously (tests/CLI/shutdown)."""
        return self._controller._lifecycle.drain()

    def start_background(self) -> None:
        """Start the background worker thread (production singletons only).

        ``get_mem()`` calls this so embeddings/extraction run off the chat
        path; tests that construct ``MemoryAPI`` directly stay deterministic
        because the worker never starts unless this is called.
        """
        self._controller._lifecycle.start()

    # ── retrieval ─────────────────────────────────────────────────────
    def retrieve(
        self,
        query: str,
        project: str = "",
        top_k: int = 3,
        min_score: float = 0.15,
    ) -> list[dict[str, Any]]:
        """Merged, deduped, hybrid-ranked results (legacy dict shape)."""
        from runtime.observability.tracer import get_tracer

        with get_tracer().span("memory.retrieve", {
            "query": query[:80], "project": project, "top_k": top_k,
        }):
            return self._controller.retrieve(query, project=project, top_k=top_k, min_score=min_score)

    def retrieve_items(
        self,
        query: str,
        project: str = "",
        top_k: int = 3,
        min_score: float = 0.15,
    ) -> list[MemoryItem]:
        return self._controller.retrieve_items(query, project=project, top_k=top_k, min_score=min_score)

    def recall_session(self, query: str, top_k: int = 5) -> list[MemoryItem]:
        return self._controller._lifecycle.recall_session(query, top_k=top_k)

    # ── legacy Mem-compatible surface ─────────────────────────────────
    def remember(self, key: str, value: str, category: str = "notes") -> str:
        """Legacy key/value remember (writes KV now + background embed)."""
        if self._controller._kv is not None:
            self.store(value, key=key, type=category, tags=[key])
            msg = f"Remembered: {category}/{key} = {value}"
        else:
            from memory.memory_manager import remember as _remember
            return _remember(key, value, category)
        if self._mirror_json:
            try:
                from memory.memory_manager import update_memory
                update_memory({category: {key: {"value": value}}})
            except Exception:
                pass
        return msg

    def forget(self, key: str, category: str = "notes") -> str:
        self._controller.delete(key)
        from memory.memory_manager import forget as _forget
        return _forget(key, category)

    def record_decision(self, goal: str, decision: str, rationale: str = "",
                        outcome: str = "", project: str = "",
                        metadata: dict[str, Any] | None = None) -> int | None:
        item = MemoryItem(
            content=goal, type=DECISION, project=project,
            metadata={"goal": goal, "decision": decision, "rationale": rationale,
                      "outcome": outcome, **(metadata or {})},
        )
        return self._controller.record_decision(item)

    def recall_decisions(self, project: str = "", query: str = "",
                         limit: int = 5) -> list[dict[str, Any]]:
        if self._controller._decisions is None:
            return []
        return self._controller._decisions.recall(project=project, query=query, limit=limit)

    def set_knowledge(self, project: str, key: str, content: str,
                      category: str = "note") -> None:
        if self._controller._knowledge is not None:
            self._controller._knowledge.set(project, key, content, category=category)

    def get_knowledge(self, project: str, key: str) -> str | None:
        if self._controller._knowledge is None:
            return None
        return self._controller._knowledge.get(project, key)

    def forget_knowledge(self, project: str, key: str) -> bool:
        if self._controller._knowledge is None:
            return False
        return self._controller._knowledge.forget(project, key)

    def import_project_docs(self, project: str, root_path: Path) -> int:
        if self._controller._knowledge is None:
            return 0
        return self._controller._knowledge.import_docs(project, root_path)

    # ── prompt rendering ──────────────────────────────────────────────
    def format_for_prompt(self, project: str, max_tokens: int = 4000) -> str:
        """Render a token-bounded memory section for the system prompt."""
        from runtime.observability.tracer import get_tracer

        with get_tracer().span("memory.prompt", {"project": project, "max_tokens": max_tokens}):
            c = self._controller
            sections = []
            if c._knowledge is not None:
                knowledge = c._knowledge.format_for_prompt(project, max_tokens=max_tokens)
                if knowledge:
                    sections.append(knowledge)
            if c._decisions is not None:
                decisions = c._decisions.recall(project=project, query="", limit=5)
                if decisions:
                    lines = ["[DECISION MEMORY]"]
                    for d in decisions:
                        lines.append(
                            f"- {d['goal'][:100]} → {d['decision']}"
                            + (f" | {d['rationale'][:120]}" if d["rationale"] else "")
                        )
                    sections.append("\n".join(lines))
            if c._kv is not None:
                recent = c._kv.recent(limit=8)
                if recent:
                    lines = ["[RECENT MEMORY]"]
                    for r in recent:
                        value = str(r["value"]).replace("\n", " ")[:200]
                        lines.append(f"- {r['key']}: {value}")
                    sections.append("\n".join(lines))
            if not sections:
                return ""
            text = "\n\n".join(sections)
            budget_chars = max(80, max_tokens * 4)
            if len(text) > budget_chars:
                text = text[: budget_chars] + "\n"
            return text

    # ── stats / lifecycle ─────────────────────────────────────────────
    def get_stats(self) -> dict[str, Any]:
        return self._controller.get_stats()

    def schedule_decay(self) -> None:
        self._controller.schedule_decay()

    def close(self) -> None:
        self._controller.close()


def get_mem() -> MemoryAPI:
    """Process-wide memory instance (replaces the old Mem singleton)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                from memory.decision_memory import get_decision_memory
                from memory.project_knowledge import get_project_knowledge
                from memory.store import MemoryStore
                from memory.vector_store import VectorMemoryStore
                _instance = MemoryAPI(
                    kv=MemoryStore(),
                    vector=VectorMemoryStore(),
                    decisions=get_decision_memory(),
                    knowledge=get_project_knowledge(),
                    mirror_json=True,
                )
                _instance.start_background()
    return _instance


# Backwards-compatible alias: existing imports of Mem still work.
Mem = MemoryAPI
