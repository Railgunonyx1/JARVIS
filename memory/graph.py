"""Lightweight knowledge graph (GraphRAG) for memory (Stage 2 groundwork).

Entity-relation-entity triples persisted as JSON with a small BFS traversal
API. Promoted from core/memory_v2.py into the memory package.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from memory.models import KnowledgeTriple

MAX_TRIPLES = 5000


class KnowledgeGraph:
    """Entity-relation-entity triple store with simple graph queries."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or Path.home() / ".jarvis" / "knowledge_graph.json"
        self._lock = threading.Lock()
        self._triples: List[KnowledgeTriple] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._triples = [KnowledgeTriple.from_dict(t) for t in data]
        except Exception:
            self._triples = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps([t.to_dict() for t in self._triples], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add_triple(self, triple: KnowledgeTriple) -> None:
        with self._lock:
            for existing in self._triples:
                if (existing.subject.lower() == triple.subject.lower()
                        and existing.relation.lower() == triple.relation.lower()
                        and existing.obj.lower() == triple.obj.lower()):
                    return
            self._triples.append(triple)
            if len(self._triples) > MAX_TRIPLES:
                self._triples = self._triples[-MAX_TRIPLES:]
            self._save()

    def query(self, entity: str, relation: Optional[str] = None) -> List[KnowledgeTriple]:
        with self._lock:
            return [
                t for t in self._triples
                if t.subject.lower() == entity.lower() or t.obj.lower() == entity.lower()
                if relation is None or t.relation.lower() == relation.lower()
            ]

    def get_related(self, entity: str, max_depth: int = 2) -> Dict[str, list]:
        visited: set = set()
        graph: Dict[str, list] = {}
        queue = [(entity, 0)]
        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)
            edges = []
            for t in self._triples:
                if t.subject.lower() == current.lower():
                    edges.append((t.relation, t.obj, t.confidence))
                    queue.append((t.obj, depth + 1))
                elif t.obj.lower() == current.lower():
                    edges.append((f"_{t.relation}_by", t.subject, t.confidence))
                    queue.append((t.subject, depth + 1))
            if edges:
                graph[current] = edges
        return graph

    def search(self, query: str, limit: int = 10) -> List[KnowledgeTriple]:
        query = query.lower()
        with self._lock:
            results = [
                t for t in self._triples
                if query in t.subject.lower() or query in t.obj.lower() or query in t.relation.lower()
            ]
        return results[:limit]

    def clear(self) -> None:
        with self._lock:
            self._triples.clear()
            self._save()

    def get_stats(self) -> dict:
        with self._lock:
            return {"triples": len(self._triples)}

    @property
    def size(self) -> int:
        return len(self._triples)
