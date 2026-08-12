"""Knowledge Distiller — Extracts, consolidates, and manages facts from conversations."""

import logging
import re
import threading
import time
from collections import Counter

logger = logging.getLogger("jarvis.knowledge_engine.knowledge_distiller")


def _extract_keywords(text: str, top_n: int = 10) -> list[str]:
    """Extract most frequent meaningful keywords from text."""
    stop_words = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'shall', 'can', 'need', 'dare', 'ought',
        'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
        'as', 'into', 'through', 'during', 'before', 'after', 'above', 'below',
        'between', 'out', 'off', 'over', 'under', 'again', 'further', 'then',
        'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'both',
        'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
        'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 'just',
        'don', 'now', 'and', 'but', 'or', 'if', 'while', 'this', 'that',
        'these', 'those', 'it', 'its', 'i', 'me', 'my', 'we', 'our', 'you',
        'your', 'he', 'him', 'his', 'she', 'her', 'they', 'them', 'their',
        'what', 'which', 'who', 'whom', 'about', 'also', 'like', 'know',
        'think', 'want', 'make', 'get', 'go', 'come', 'see', 'look',
        'use', 'say', 'tell', 'give', 'take', 'let', 'keep', 'put', 'try',
        'ask', 'set', 'run', 'move', 'show', 'help', 'start', 'turn', 'play',
    }
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    filtered = [w for w in words if w not in stop_words]
    counts = Counter(filtered)
    return [w for w, _ in counts.most_common(top_n)]


def _extract_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    sentences = re.split(r'[.!?]+', text)
    return [s.strip() for s in sentences if len(s.strip()) > 10]


def _is_factual(sentence: str) -> bool:
    """Heuristic: check if a sentence looks factual."""
    factual_patterns = [
        r'\bis\b.*\bwas\b', r'\bare\b', r'\bmeans\b', r'\bdefined as\b',
        r'\blocated in\b', r'\bcreated in\b', r'\bby\b.*\bauthor\b',
        r'\bversion\b', r'\buses\b', r'\bbased on\b', r'\bsupports\b',
        r'\btype\b', r'\bcategory\b', r'\bpart of\b', r'\bbelongs to\b',
    ]
    lower = sentence.lower()
    return any(re.search(p, lower) for p in factual_patterns)


def _extract_entities_from_text(text: str) -> list[dict]:
    """Simple entity extraction from text."""
    entities = []
    proper_nouns = re.findall(r'\b([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)*)\b', text)
    for name in set(proper_nouns):
        etype = "concept"
        if any(w in name.lower() for w in ['python', 'java', 'javascript', 'rust', 'go']):
            etype = "language"
        elif any(w in name.lower() for w in ['windows', 'linux', 'macos', 'android']):
            etype = "platform"
        elif any(w in name.lower() for w in ['openai', 'google', 'microsoft', 'apple']):
            etype = "organization"
        entities.append({"name": name, "type": etype})
    return entities


def _extract_relationships(entities: list[dict], text: str) -> list[dict]:
    """Extract relationships between entities found in the same sentence."""
    relationships = []
    sentences = _extract_sentences(text)
    for sent in sentences:
        found = [e for e in entities if e["name"] in sent]
        if len(found) >= 2:
            for i in range(len(found)):
                for j in range(i + 1, len(found)):
                    relationships.append({
                        "source": found[i]["name"],
                        "target": found[j]["name"],
                        "context": sent[:100],
                    })
    return relationships


class KnowledgeDistiller:
    """Extracts, consolidates, and manages facts from conversations."""

    def __init__(self):
        self._lock = threading.Lock()
        self._facts: list[dict] = []
        self._fact_counter = 0

    def distill(self, conversation: str) -> dict:
        """Extract key knowledge from a conversation."""
        sentences = _extract_sentences(conversation)
        facts = []
        for sent in sentences:
            if _is_factual(sent):
                facts.append({
                    "text": sent.strip(),
                    "source": "conversation",
                    "timestamp": time.time(),
                    "confidence": 0.6,
                    "topics": _extract_keywords(sent, 5),
                })
        entities = _extract_entities_from_text(conversation)
        relationships = _extract_relationships(entities, conversation)
        summary = self._generate_summary(conversation)

        with self._lock:
            for fact in facts:
                self._fact_counter += 1
                fact["id"] = f"fact_{self._fact_counter}"
                self._facts.append(fact)
            if len(self._facts) > 5000:
                self._facts = self._facts[-2500:]

        return {
            "facts": facts,
            "entities": entities,
            "relationships": relationships,
            "summary": summary,
        }

    def _generate_summary(self, text: str) -> str:
        """Generate a simple extractive summary."""
        sentences = _extract_sentences(text)
        if not sentences:
            return text[:200]
        keywords = _extract_keywords(text, 5)
        scored = []
        for sent in sentences:
            score = sum(1 for kw in keywords if kw in sent.lower())
            scored.append((score, sent))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [s for _, s in scored[:3]]
        return ". ".join(top) + "."

    def consolidate(self, facts: list[dict]) -> list[dict]:
        """Merge and deduplicate facts."""
        seen_texts = set()
        consolidated = []
        for fact in facts:
            normalized = re.sub(r'\s+', ' ', fact.get("text", "").lower().strip())
            if normalized not in seen_texts and normalized:
                seen_texts.add(normalized)
                consolidated.append(fact)
        return consolidated

    def get_facts(self, limit: int = 50) -> list[dict]:
        """Return recent facts."""
        with self._lock:
            return list(reversed(self._facts[-limit:]))

    def get_facts_by_topic(self, topic: str) -> list[dict]:
        """Return facts about a specific topic."""
        topic_lower = topic.lower()
        with self._lock:
            return [
                f for f in self._facts
                if topic_lower in " ".join(f.get("topics", [])).lower()
                or topic_lower in f.get("text", "").lower()
            ]

    def confidence_score(self, fact: str) -> float:
        """Return confidence for a fact based on repetition across sources."""
        fact_lower = fact.lower().strip()
        with self._lock:
            count = sum(
                1 for f in self._facts
                if fact_lower in f.get("text", "").lower()
            )
        if count == 0:
            return 0.1
        return min(1.0, 0.3 + (count * 0.15))


_instance: KnowledgeDistiller | None = None


def get_knowledge_distiller() -> KnowledgeDistiller:
    global _instance
    if _instance is None:
        _instance = KnowledgeDistiller()
    return _instance
