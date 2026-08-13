from __future__ import annotations
import time
"""
JARVIS Memory Fabric — Memory Extraction & Consolidation

Handles the write pipeline's consolidation phase and optional LLM-based
extraction. All operations are deterministic; LLM calls are optional and
injected via callables.

Consolidation converts:
  experience → knowledge
  
  Raw episodes → merged facts → entities → relationships → resolved state
"""

import time
from __future__ import annotations

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
import json
import re


# ---------------------------------------------------------------------------
# Optional LLM extraction
# ---------------------------------------------------------------------------

ExtractorFn = Optional[callable]  # type alias


def default_extractor(text: str) -> Dict[str, Any]:
    """Deterministic rule-based extractor (no LLM required).

    Handles common patterns found in agent conversation:
      - "X uses Y"
      - "X is Y"
      - "how to do Z"
      - "the daemon ..."
      - "port Y"
    Returns dict with optional subject/predicate/object/confidence/importance.
    """
    t = text.strip().rstrip(".!?;:,")
    result: Dict[str, Any] = {"subject": None, "predicate": None, "object": None,
                              "confidence": 1.0, "importance": 0.5}

    # Pattern: "<subj> uses/uses/prefers <obj>"
    m = re.match(r"^([A-Za-z0-9_\-]+)\s+(uses|prefers|is|was|are|means)\s+(.+)$", t, re.IGNORECASE)
    if m:
        result["subject"] = m.group(1)
        result["predicate"] = m.group(2).lower()
        result["object"] = m.group(3).strip(" .,")
        result["confidence"] = 0.9
        result["importance"] = 0.7
        return result

    # Pattern: "<subj> is <obj>"
    m = re.match(r"^([A-Za-z0-9_\-]+)\s+is\s+(.+)$", t, re.IGNORECASE)
    if m:
        result["subject"] = m.group(1)
        result["predicate"] = "is"
        result["object"] = m.group(2).strip(" .,")
        result["confidence"] = 0.8
        result["importance"] = 0.6
        return result

    # Pattern: "port <number>"
    m = re.match(r"port\s+(\d+)", t, re.IGNORECASE)
    if m:
        result["object"] = m.group(1)
        result["predicate"] = "uses"
        result["confidence"] = 0.95
        return result

    # Pattern: "how to <procedure>"
    m = re.match(r"how\s+to\s+(.+)$", t, re.IGNORECASE)
    if m:
        result["content"] = m.group(1).strip(" .,")
        result["type"] = "procedure"
        result["importance"] = 0.8
        return result

    # Fallback: treat whole thing as a fact with subject="JARVIS" if mentioned
    if "jarvis" in t.lower() or "daemon" in t.lower():
        result["subject"] = "JARVIS"
        result["content"] = t
        result["importance"] = 0.5
        return result

    return result


# ---------------------------------------------------------------------------
# Consolidation engine
# ---------------------------------------------------------------------------

class ConsolidationEngine:
    """Async consolidation: merges duplicates, resolves conflicts, creates entities."""

    def __init__(self, fabric: "MemoryFabric", *, extractor: ExtractorFn = None) -> None:
        self._fabric = fabric
        self._extractor = extractor or default_extractor

    def run(self, job_id: str = "") -> Dict[str, Any]:
        """Run the full consolidation pass.

        Returns dict with counts of items processed, merged, archived, etc.
        """
        started = datetime.now(timezone.utc).isoformat()
        job_id = job_id or f"consolidate_{int(time.time())}"

        with self._fabric._storage._lock:
            # 1. Find duplicate facts (same subject+predicate+object, active)
            dups = self._fabric._conn.execute(
                """
                SELECT mi.id, mi.subject, mi.predicate, mi.object, mi.content,
                       mi.importance, mi.confidence, mi.valid_from, mi.valid_until
                FROM memory_items mi
                WHERE mi.type = 'fact' AND mi.status != 'retired'
                GROUP BY mi.subject, mi.predicate, mi.object, mi.valid_from
                HAVING COUNT(*) > 1
                """
            ).fetchall()

            facts_merged = 0
            for d in dups:
                # Keep the one with highest importance*confidence; retire others
                rows = self._fabric._conn.execute(
                    "SELECT id, importance, confidence, valid_from, valid_until "
                    "FROM memory_items WHERE subject=? AND predicate=? AND object=? "
                    "AND valid_from=? AND status != 'retired'",
                    (d["subject"], d["predicate"], d["object"], d["valid_from"]),
                ).fetchall()

                # Sort by importance*confidence descending
                rows.sort(key=lambda r: r["importance"] * r["confidence"], reverse=True)
                keep = rows[0]["id"]
                for r in rows[1:]:
                    self._fabric._conn.execute(
                        "UPDATE memory_items SET status='superseded', valid_until=? WHERE id=?",
                        (datetime.now(timezone.utc).isoformat(), r["id"]),
                    )
                    self._fabric._conn.execute(
                        "INSERT INTO memory_links "
                        "(memory_item_id_1, memory_item_id_2, link_type, strength) "
                        "VALUES (?, ?, 'derives_from', 0.9)",
                        (r["id"], keep),
                    )
                    facts_merged += 1

            # 2. Find entities: subjects/objects that appear frequently as fact participants
            entity_candidates = self._fabric._conn.execute(
                """
                SELECT subject AS name FROM memory_items WHERE type='fact' AND subject IS NOT NULL
                UNION
                SELECT object AS name FROM memory_items WHERE type='fact' AND object IS NOT NULL
                """
            ).fetchall()

        # Count occurrences
        name_counts: Dict[str, int] = {}
        for r in entity_candidates:
            n = r["name"]
            name_counts[n] = name_counts.get(n, 0) + 1

        # Entities appearing in 3+ facts are "real"
        entity_threshold = 3
        new_entities = 0
        for name, count in name_counts.items():
            if count >= entity_threshold and name not in (
                "JARVIS", "daemon", "UI", "TTS", "Piper", "React", "WebSocket"
            ):
                # Check if entity already exists
                existing = self._fabric._conn.execute(
                    "SELECT id FROM entities WHERE name=?",
                    (name,),
                ).fetchone()
                if not existing:
                    eid = self._fabric.remember(
                        type="entity",
                        content=f"Entity identified from memory: {name}",
                        subject=name,
                        predicate=None,
                        obj=None,
                        importance=0.6,
                        salience="HIGH",
                    )
                    # Link to associated facts
                    related_facts = self._fabric._conn.execute(
                        "SELECT id FROM memory_items WHERE type='fact' AND (subject=? OR object=?)",
                        (name, name),
                    ).fetchall()
                    for f in related_facts:
                        self._fabric._conn.execute(
                            "INSERT INTO memory_links "
                            "(memory_item_id_1, memory_item_id_2, link_type, strength) "
                            "VALUES (?, ?, 'related_to', 0.8)",
                            (eid, f["id"]),
                        )
                    new_entities += 1

            # 3. Upgrade HIGH-salience facts to CRITICAL if they involve known entities
        critical_candidates = self._fabric._conn.execute(
            """SELECT mi.id FROM memory_items mi
               WHERE mi.type='fact' AND mi.salience='HIGH'
               AND EXISTS (
                  SELECT 1 FROM entities e WHERE e.name IN (mi.subject, mi.object)
               )"""
        ).fetchall()

        for r in critical_candidates:
            self._fabric.update(r["id"], salience="CRITICAL")

        # 4. Archive low-importance old episodes
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        archived = self._fabric._conn.execute(
            """UPDATE memory_items SET status='archived'
               WHERE type='episode' AND importance < 0.3
               AND created_at < ?
               AND status='active'""",
            (cutoff,),
        ).rowcount

        # 5. Record consolidation event
        self._fabric._conn.execute(
            "INSERT INTO consolidation_jobs "
            "(job_id, status, started_at, completed_at, items_processed, facts_merged, "
            "entities_created, episodes_archived) VALUES (?, 'completed', ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                started,
                datetime.now(timezone.utc).isoformat(),
                len(dups) + len(critical_candidates) + 1,  # rough count
                facts_merged,
                new_entities,
                archived,
            ),
        )
        self._fabric._conn.commit()

        completed = datetime.now(timezone.utc).isoformat()
        return {
            "job_id": job_id,
            "status": "completed",
            "started_at": started,
            "completed_at": completed,
            "facts_merged": facts_merged,
            "entities_created": new_entities,
            "episodes_archived": archived,
        }


# ---------------------------------------------------------------------------
# End of consolidation/extraction module
# ---------------------------------------------------------------------------

__all__ = ["ConsolidationEngine", "default_extractor"]