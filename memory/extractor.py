"""Memory extraction from conversation text (Stage 1G).

Pattern-based extraction (no LLM call required for basic facts). Writes are
deferred to the background worker so extraction never blocks the chat path.
Promoted from core/memory_v2.py into the memory package.
"""

from __future__ import annotations

import re

from memory.models import IDENTITY, NOTE, PREFERENCE, PROJECT, RELATIONSHIP, MemoryItem
from memory.ranking import ImportanceScorer


class MemoryExtractor:
    """Extract structured MemoryItems from free-form conversation text."""

    def __init__(self, importance_scorer: ImportanceScorer | None = None) -> None:
        self._scorer = importance_scorer or ImportanceScorer()

    def extract(self, text: str, source: str = "", project: str = "") -> list[MemoryItem]:
        """Turn a text chunk into candidate MemoryItems (unpersisted)."""
        items = []
        text = text.strip()
        if not text:
            return items

        importance = self._scorer.score(text)

        m = re.search(r"(?:my name is|i am|i'm)\s+([A-Za-z]+)\b", text, re.IGNORECASE)
        if m:
            name = m.group(1)
            skip_words = {"and", "the", "my", "i", "a", "an", "in", "on", "at", "to", "for"}
            if name and len(name) > 2 and name.lower() not in skip_words:
                items.append(MemoryItem(
                    content=f"User name is {name}",
                    type=IDENTITY, importance=0.9, source=source, project=project,
                    tags=["identity", "name"],
                ))

        for pref in re.findall(r"i (?:love|like|enjoy|hate|dislike|don't like|prefer)\s+(.+?)(?:\.|!|\?|$)", text, re.IGNORECASE):
            pref = pref.strip()
            if len(pref) > 1:
                items.append(MemoryItem(
                    content=f"User preference: {pref}",
                    type=PREFERENCE, importance=importance, source=source, project=project,
                    tags=["preference"],
                ))

        for relation, rel_name in re.findall(r"(my\s+(?!name)\w+)\s+(?:is|are|has|have|named?)\s+(.+?)(?:\.|!|\?|$)", text, re.IGNORECASE):
            rel_name = rel_name.strip()
            if len(rel_name) > 1 and 3 < len(rel_name) < 80:
                items.append(MemoryItem(
                    content=f"{relation.strip()} is {rel_name}",
                    type=RELATIONSHIP, importance=importance + 0.1, source=source, project=project,
                    tags=["relationship"],
                ))

        for p in re.findall(r"(?:i['']?m working on|my project|building|creating|developing)\s+(.+?)(?:\.|!|\?|$)", text, re.IGNORECASE):
            items.append(MemoryItem(
                content=f"User project: {p.strip()}",
                type=PROJECT, importance=0.8, source=source, project=project,
                tags=["project"],
            ))

        if not items and len(text) > 40:
            items.append(MemoryItem(
                content=text[:200],
                type=NOTE, importance=importance, source=source, project=project,
                tags=["auto_extracted"],
            ))

        return items
