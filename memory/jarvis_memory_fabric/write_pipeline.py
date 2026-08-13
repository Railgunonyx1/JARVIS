"""
JARVIS Memory Fabric — Write Pipeline

Deterministic, LLM-free write path:
  input
    → candidate detection (memory-worthiness)
    → classification (type)
    → validation (schema + trust)
    → deduplication
    → conflict detection (temporal)
    → importance/salience scoring
    → persistence (via MemoryFabric)

LLM extraction is optional and injected via an extractor callable.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any, Callable, Tuple
import re


# ---------------------------------------------------------------------------
# Candidate detection — memory-worthiness scoring
# ---------------------------------------------------------------------------

# Patterns that indicate low memory value
TRIVIAL_PATTERNS = [
    r"^(ok|okay|k|yes|no|sure|thanks|thank you|hi|hello|hey)\.?\s*$",
    r"^(got it|noted|cool|nice|great|awesome|lol|haha)\.?\s*$",
    r"^\W*$",
]

MEMORY_WORTHY_INDICATORS = [
    # decisions / preferences
    r"\b(use|uses|prefer|preference|decide|decided|choose|chose|architecture|ADR)\b",
    # facts
    r"\b(is|are|was|were|means|means that|port|version|path|location|file|command)\b",
    # procedures
    r"\b(how to|steps to|run|start|stop|install|build|deploy|configure)\b",
    # identity
    r"\b(jarvis|daemon|agent|model|tts|engine|backend|frontend)\b",
]


def memory_worthiness(
    text: str,
    *,
    importance: float = 0.5,
    confidence: float = 1.0,
    future_usefulness: float = 0.5,
    novelty: float = 0.5,
    persistence_probability: float = 0.5,
) -> float:
    """Compute a memory-worthiness score (section 12).

    score = importance × confidence × future_usefulness × novelty × persistence_probability
    """
    base = (
        importance
        * confidence
        * future_usefulness
        * novelty
        * persistence_probability
    )
    # Boost for strong indicators
    if any(re.search(p, text, re.IGNORECASE) for p in MEMORY_WORTHY_INDICATORS):
        base = min(1.0, base * 1.4)
    return base


def is_candidate(text: str, threshold: float = 0.15) -> bool:
    """Return True if text is worth remembering (not trivial)."""
    # Trivial short utterances are discarded
    for pat in TRIVIAL_PATTERNS:
        if re.search(pat, text.strip(), re.IGNORECASE):
            return False
    # Strong memory indicators (decisions, facts, procedures, identity) are
    # always treated as candidates per the spec examples.
    if any(re.search(p, text, re.IGNORECASE) for p in MEMORY_WORTHY_INDICATORS):
        return True
    # Compute worthiness with defaults as a fallback
    score = memory_worthiness(
        text,
        importance=0.5,
        confidence=1.0,
        future_usefulness=0.5,
        novelty=0.5,
        persistence_probability=0.5,
    )
    return score >= threshold


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify(text: str, subject: Optional[str] = None, predicate: Optional[str] = None, obj: Optional[str] = None) -> str:
    """Classify a memory into one of the supported types.

    Priority: if subject/predicate/object present → 'fact'.
    Else heuristics on keywords.
    """
    if subject and predicate and obj:
        return "fact"
    low = text.lower()
    if any(k in low for k in ["how to", "steps", "procedure", "run", "command", "start", "install"]):
        return "procedure"
    if any(k in low for k in ["happened", "did", "when we", "session", "task", "episode"]):
        return "episode"
    # Default to fact for assertions
    return "fact"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate(
    *,
    type: str,
    content: str,
    confidence: float,
    importance: float,
    trust_class: str = "UNTRUSTED",
) -> Tuple[bool, List[str]]:
    """Validate a candidate memory. Returns (ok, errors)."""
    errors: List[str] = []
    if not content or not content.strip():
        errors.append("content is empty")
    if type not in {"episode", "fact", "procedure", "entity", "relationship"}:
        errors.append(f"invalid type: {type}")
    if not (0.0 <= confidence <= 1.0):
        errors.append("confidence out of range [0,1]")
    if not (0.0 <= importance <= 1.0):
        errors.append("importance out of range [0,1]")
    # Untrusted input with very high confidence is suspicious — clamp instead of rejecting
    if trust_class == "UNTRUSTED" and confidence > 0.7:
        errors.append("untrusted source confidence capped at 0.7; clamping recommended")
    return (len(errors) == 0, errors)


# ---------------------------------------------------------------------------
# Deduplication check
# ---------------------------------------------------------------------------


def find_duplicate(
    fabric: "MemoryFabric",  # type: ignore
    *,
    subject: Optional[str],
    predicate: Optional[str],
    obj: Optional[str],
    content: str,
) -> Optional[str]:
    """Return existing memory id if a duplicate exists."""
    results = fabric.search(
        subject=subject,
        predicate=predicate,
        obj=obj,
        limit=10,
    )
    for r in results:
        if (
            (r.get("subject") or "") == (subject or "")
            and (r.get("predicate") or "") == (predicate or "")
            and (r.get("object") or "") == (obj or "")
        ):
            return r["id"]
        # loose content match
        if (r.get("content") or "").strip().lower() == content.strip().lower():
            return r["id"]
    return None


# ---------------------------------------------------------------------------
# Conflict detection (temporal)
# ---------------------------------------------------------------------------


def detect_conflict(
    fabric: "MemoryFabric",  # type: ignore
    *,
    subject: str,
    predicate: str,
    obj: str,
) -> Optional[Dict[str, Any]]:
    """Detect an existing fact with same subject+predicate but different object.

    Returns the conflicting record dict if found, else None.
    """
    results = fabric.search(subject=subject, predicate=predicate, type="fact", limit=20)
    for r in results:
        if (r.get("object") or "") != (obj or "") and r.get("status") == "active":
            return r
    return None


# ---------------------------------------------------------------------------
# Salience classification
# ---------------------------------------------------------------------------


def classify_salience(
    type: str,
    importance: float,
    confidence: float,
) -> str:
    """Map a memory to a salience tier (section 13)."""
    if type == "fact" and importance >= 0.8:
        return "CRITICAL"
    if type == "procedure" and importance >= 0.7:
        return "HIGH"
    if importance >= 0.7:
        return "HIGH"
    if importance >= 0.4:
        return "MEDIUM"
    if importance > 0.15:
        return "LOW"
    return "EPHEMERAL"


# ---------------------------------------------------------------------------
# Deterministic (LLM-free) extractor
# ---------------------------------------------------------------------------

_FILLER = {"now", "currently", "the", "a", "an", "primary", "main", "default", "as"}


def simple_extractor(text: str) -> Dict[str, Any]:
    """Lightweight rule-based extractor (no LLM).

    Handles common assertion patterns:
      - "<subj> uses <obj>"
      - "<subj> is <obj>"
      - "<subj> <predicate> <obj>"
    Returns dict with optional subject/predicate/object.
    """
    t = text.strip().rstrip(".!?")
    # Pattern: subject verb object
    m = re.match(r"^([A-Za-z0-9_\-]+)\s+(uses|prefers|is|was|are|were|means|runs|depends on|contains|has)\s+(.+)$", t, re.IGNORECASE)
    if m:
        subj = m.group(1)
        pred = m.group(2).lower()
        obj = m.group(3)
        # Clean object of filler words
        obj_tokens = [w for w in re.split(r"\s+", obj) if w.lower().strip(".,") not in _FILLER]
        obj_clean = " ".join(obj_tokens).strip(" .,")
        return {"subject": subj, "predicate": pred, "object": obj_clean}
    # Pattern: "<subj> <predicate-noun> is <object>"
    m = re.match(r"^([A-Za-z0-9_\-]+)\s+([A-Za-z0-9_\-]+)\s+is\s+(.+)$", t, re.IGNORECASE)
    if m:
        subj = m.group(1)
        pred = m.group(2).lower()
        obj = m.group(3)
        obj_tokens = [w for w in re.split(r"\s+", obj) if w.lower().strip(".,") not in _FILLER]
        obj_clean = " ".join(obj_tokens).strip(" .,")
        return {"subject": subj, "predicate": pred, "object": obj_clean}
    # Fallback: two-word subject is object
    m2 = re.match(r"^([A-Za-z0-9_\-]+)\s+([A-Za-z0-9_\-]+)\s+(.+)$", t)
    if m2:
        return {
            "subject": m2.group(1),
            "predicate": m2.group(2).lower(),
            "object": m2.group(3).strip(" .,"),
        }
    return {}


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------


class WritePipeline:
    """Deterministic write pipeline. No LLM required.

    Optional `extractor` callable can be injected to convert raw text into
    structured (subject, predicate, obj) triples when available.
    """

    def __init__(
        self,
        fabric: "MemoryFabric",  # type: ignore
        *,
        extractor: Optional[Callable[[str], Dict[str, Any]]] = None,
        worthiness_threshold: float = 0.15,
    ) -> None:
        self._fabric = fabric
        self._extractor = extractor or simple_extractor
        self._threshold = worthiness_threshold

    def process(
        self,
        text: str,
        *,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        source: str = "conversation",
        trust_class: str = "UNTRUSTED",
        confidence_override: Optional[float] = None,
        importance_override: Optional[float] = None,
        min_confidence: float = 0.0,
    ) -> Dict[str, Any]:
        """Run the full pipeline. Returns a result dict describing what happened."""
        # 1. Candidate detection
        if not is_candidate(text, threshold=self._threshold):
            return {"status": "discarded", "reason": "not_memory_worthy"}

        # 2. Classification + optional extraction
        subject = predicate = obj = None
        extracted = None
        if self._extractor:
            extracted = self._extractor(text)
            subject = extracted.get("subject")
            predicate = extracted.get("predicate")
            obj = extracted.get("object")

        mtype = classify(text, subject, predicate, obj)

        # 3. Importance/salience (before validation so we can clamp)
        importance = importance_override if importance_override is not None else 0.5
        confidence = confidence_override if confidence_override is not None else 1.0
        if trust_class == "UNTRUSTED":
            confidence = min(confidence, 0.7)
        salience = classify_salience(mtype, importance, confidence)

        # 4. Validation
        ok, errors = validate(
            type=mtype,
            content=text,
            confidence=confidence,
            importance=importance,
            trust_class=trust_class,
        )
        if not ok:
            return {"status": "rejected", "errors": errors}

        # 5. Deduplication
        dup_id = find_duplicate(
            self._fabric,
            subject=subject,
            predicate=predicate,
            obj=obj,
            content=text,
        )
        if dup_id:
            # Update access but skip re-insert
            self._fabric.recall(dup_id)
            return {"status": "duplicate", "memory_id": dup_id}

        # 6. Conflict detection (temporal)
        conflict = None
        if mtype == "fact" and subject and predicate and obj:
            conflict = detect_conflict(self._fabric, subject=subject, predicate=predicate, obj=obj)
        if conflict:
            # Set old fact's valid_until = now, keep new as active
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
            self._fabric.update(conflict["id"], valid_until=now, status="superseded")
            # superseded_by_id will be set to the new memory id after insertion

        # 7. Persist
        mid = self._fabric.remember(
            type=mtype,
            content=text,
            subject=subject,
            predicate=predicate,
            obj=obj,
            confidence=confidence,
            importance=importance,
            salience=salience,
            session_id=session_id,
            task_id=task_id,
            source=source,
        )

        # Link conflict resolution to the new memory id
        if conflict:
            self._fabric._storage._conn.execute(
                "UPDATE memory_items SET superseded_by_id=? WHERE id=?",
                (mid, conflict["id"]),
            )
            self._fabric._storage._conn.commit()

        # Record source provenance
        self._fabric._storage._conn.execute(
            "INSERT INTO memory_sources "
            "(id, memory_item_id, source_type, source_reference, confidence, user_confirmed) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"src_{mid[4:]}",
                mid,
                source,
                session_id or "unknown",
                confidence,
                1 if trust_class == "USER_CONFIRMED" else 0,
            ),
        )
        self._fabric._storage._conn.commit()

        return {
            "status": "stored",
            "memory_id": mid,
            "type": mtype,
            "salience": salience,
            "confidence": confidence,
            "importance": importance,
            "conflict_resolved": conflict is not None,
        }


# ---------------------------------------------------------------------------
# End of write pipeline
# ---------------------------------------------------------------------------

__all__ = [
    "WritePipeline",
    "memory_worthiness",
    "is_candidate",
    "classify",
    "validate",
    "detect_conflict",
    "classify_salience",
]
