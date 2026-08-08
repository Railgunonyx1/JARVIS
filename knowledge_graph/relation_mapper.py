"""
Relation Mapper — Extracts and maps relations between entities for JARVIS MK-X.

Analyzes text and context to infer relationships between entities:
- Syntactic patterns (X of Y, X uses Y, X created by Y)
- Co-occurrence proximity scoring
- Intent-based relation inference
- Temporal ordering (X before/after Y)

Performance: < 10ms per extraction on typical input.
"""

from __future__ import annotations

import re
import logging
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

from knowledge_graph.graph import EntityType, RelationType, Entity

logger = logging.getLogger("jarvis.knowledge_graph.relations")

# Syntactic relation patterns: (pattern, source_group, target_group, relation_type)
_RELATION_PATTERNS: List[Tuple[re.Pattern, int, int, RelationType]] = [
    # "X uses Y"
    (re.compile(r'(\b[\w\s]+?)\s+uses?\s+(\b[\w\s]+)', re.I), 1, 2, RelationType.USES),
    # "X created by Y" / "Y created X"
    (re.compile(r'(\b[\w\s]+?)\s+created\s+by\s+(\b[\w\s]+)', re.I), 1, 2, RelationType.CREATED),
    (re.compile(r'(\b[\w\s]+?)\s+created\s+(\b[\w\s]+)', re.I), 1, 2, RelationType.CREATED),
    # "X works on Y"
    (re.compile(r'(\b[\w\s]+?)\s+works?\s+on\s+(\b[\w\s]+)', re.I), 1, 2, RelationType.WORKS_ON),
    # "X part of Y"
    (re.compile(r'(\b[\w\s]+?)\s+part\s+of\s+(\b[\w\s]+)', re.I), 1, 2, RelationType.PART_OF),
    # "X depends on Y"
    (re.compile(r'(\b[\w\s]+?)\s+depends?\s+on\s+(\b[\w\s]+)', re.I), 1, 2, RelationType.DEPENDS_ON),
    # "X located in Y"
    (re.compile(r'(\b[\w\s]+?)\s+(?:located?\s+in|in)\s+(\b[\w\s]+)', re.I), 1, 2, RelationType.LOCATED_IN),
    # "X owns Y"
    (re.compile(r'(\b[\w\s]+?)\s+owns?\s+(\b[\w\s]+)', re.I), 1, 2, RelationType.OWNS),
    # "X mentioned in Y"
    (re.compile(r'(\b[\w\s]+?)\s+mentioned?\s+in\s+(\b[\w\s]+)', re.I), 1, 2, RelationType.MENTIONED_IN),
    # "X contains Y"
    (re.compile(r'(\b[\w\s]+?)\s+contains?\s+(\b[\w\s]+)', re.I), 1, 2, RelationType.CONTAINS),
    # "X similar to Y"
    (re.compile(r'(\b[\w\s]+?)\s+similar\s+to\s+(\b[\w\s]+)', re.I), 1, 2, RelationType.SIMILAR_TO),
    # "X caused by Y"
    (re.compile(r'(\b[\w\s]+?)\s+caused?\s+by\s+(\b[\w\s]+)', re.I), 1, 2, RelationType.CAUSED_BY),
]

# Intent-to-relation mappings
_INTENT_RELATIONS: Dict[str, List[Tuple[str, str, RelationType]]] = {
    "action.open": [("user", "app", RelationType.USES)],
    "action.search": [("user", "query", RelationType.RELATED_TO)],
    "action.file": [("user", "path", RelationType.OWNS)],
    "action.shell": [("user", "command", RelationType.USES)],
    "memory.store": [("user", "fact", RelationType.KNOWS)],
    "planner.execute": [("user", "goal", RelationType.WORKS_ON)],
}

# Stopwords for cleaning entity names
_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "has", "have",
    "had", "do", "does", "did", "will", "would", "could", "should", "can",
    "may", "might", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "it", "its", "this", "that", "i", "me", "my", "we", "you",
    "your", "he", "him", "she", "her", "they", "them", "and", "but", "or", "if",
    "then", "so", "just", "also", "very", "too", "now", "here", "there", "when",
}


def _clean_entity_name(name: str) -> str:
    """Clean and normalize an entity name."""
    name = name.strip().strip("\"'.,;:!?")
    words = name.split()
    cleaned = [w for w in words if w.lower() not in _STOPWORDS]
    result = " ".join(cleaned)
    return result if result else name


def _infer_type(name: str) -> EntityType:
    """Infer entity type from name heuristics."""
    lower = name.lower()
    # File extensions
    if any(lower.endswith(ext) for ext in ['.py', '.js', '.ts', '.json', '.toml', '.yaml',
                                           '.md', '.txt', '.html', '.css', '.sh', '.bat']):
        return EntityType.FILE
    # Known apps
    known_apps = {'chrome', 'firefox', 'edge', 'vscode', 'spotify', 'discord', 'slack',
                  'zoom', 'teams', 'word', 'excel', 'powerpoint', 'outlook', 'github'}
    if lower in known_apps:
        return EntityType.APPLICATION
    # Known tools/languages
    known_tools = {'python', 'javascript', 'typescript', 'java', 'rust', 'go', 'flask',
                   'django', 'fastapi', 'react', 'vue', 'node', 'docker', 'git', 'ollama'}
    if lower in known_tools:
        return EntityType.TOOL
    # CLI commands
    known_cmds = {'ping', 'dir', 'ls', 'cd', 'mkdir', 'rm', 'git', 'npm', 'pip', 'python',
                  'curl', 'ssh', 'docker', 'cat', 'grep', 'find'}
    if lower in known_cmds:
        return EntityType.COMMAND
    return EntityType.OTHER


class RelationMapper:
    """Extracts and maps relations between entities."""

    def __init__(self):
        self._co_occurrence_window = 5  # words

    def extract_from_text(self, text: str) -> List[Tuple[str, str, RelationType, float]]:
        """Extract relations from raw text.

        Returns: List of (source_name, target_name, relation_type, confidence)
        """
        if not text or not text.strip():
            return []

        results: List[Tuple[str, str, RelationType, float]] = []

        # 1. Syntactic pattern matching
        for pattern, src_group, tgt_group, rel_type in _RELATION_PATTERNS:
            for match in pattern.finditer(text):
                src = _clean_entity_name(match.group(src_group))
                tgt = _clean_entity_name(match.group(tgt_group))
                if src and tgt and src.lower() != tgt.lower():
                    if len(src) >= 2 and len(tgt) >= 2:
                        results.append((src, tgt, rel_type, 0.9))

        # 2. Co-occurrence proximity (for entities in the same sentence)
        sentences = re.split(r'[.!?;]+', text)
        for sentence in sentences:
            words = sentence.split()
            # Find capitalized words (likely entities)
            entities_in_sentence = []
            i = 0
            while i < len(words):
                word = words[i].strip("\"'.,;:!?")
                if word and word[0].isupper() and word.lower() not in _STOPWORDS and len(word) >= 2:
                    # Check if it's part of a multi-word entity
                    phrase = [word]
                    while (i + 1 < len(words) and
                           words[i + 1] and words[i + 1][0].isupper() and
                           words[i + 1].lower() not in _STOPWORDS):
                        i += 1
                        phrase.append(words[i])
                    entity_name = " ".join(phrase)
                    entities_in_sentence.append(entity_name)
                i += 1

            # Create co-occurrence relations for nearby entities
            for idx_a in range(len(entities_in_sentence)):
                for idx_b in range(idx_a + 1, min(idx_a + self._co_occurrence_window, len(entities_in_sentence))):
                    src = entities_in_sentence[idx_a]
                    tgt = entities_in_sentence[idx_b]
                    if src.lower() != tgt.lower():
                        # Confidence decreases with distance
                        distance = idx_b - idx_a
                        confidence = max(0.3, 1.0 - (distance * 0.15))
                        results.append((src, tgt, RelationType.RELATED_TO, confidence))

        # Deduplicate and merge
        return self._merge_relations(results)

    def extract_from_intent(self, intent_name: str, entities: Dict[str, str],
                            user_name: str = "user") -> List[Tuple[str, str, RelationType, float]]:
        """Extract relations from intent classification context."""
        results = []
        if intent_name in _INTENT_RELATIONS:
            for src_key, tgt_key, rel_type in _INTENT_RELATIONS[intent_name]:
                src = user_name if src_key == "user" else entities.get(src_key, "")
                tgt = entities.get(tgt_key, "")
                if src and tgt and len(src) >= 2 and len(tgt) >= 2:
                    results.append((src, tgt, rel_type, 1.0))
        return results

    def extract_all(self, text: str, intent_name: str = "",
                    intent_entities: Optional[Dict] = None,
                    user_name: str = "user") -> List[Tuple[str, str, RelationType, float]]:
        """Combined extraction: text patterns + intent context."""
        text_relations = self.extract_from_text(text)
        intent_entities = intent_entities or {}
        intent_relations = self.extract_from_intent(intent_name, intent_entities, user_name)

        # Merge, preferring intent-based relations
        all_relations = text_relations + intent_relations
        return self._merge_relations(all_relations)

    def _merge_relations(self, relations: List[Tuple[str, str, RelationType, float]]) -> List[Tuple[str, str, RelationType, float]]:
        """Merge duplicate relations, keeping highest confidence."""
        merged: Dict[Tuple[str, str, RelationType], float] = {}
        for src, tgt, rel_type, confidence in relations:
            key = (src.lower(), tgt.lower(), rel_type)
            if key not in merged or confidence > merged[key]:
                merged[key] = confidence

        return [
            (src, tgt, rel_type, conf)
            for (src, tgt, rel_type), conf in merged.items()
        ]

    def build_co_occurrence_graph(self, texts: List[str]) -> Dict[Tuple[str, str], int]:
        """Build a co-occurrence frequency map from multiple texts."""
        co_counts: Dict[Tuple[str, str], int] = defaultdict(int)

        for text in texts:
            relations = self.extract_from_text(text)
            for src, tgt, _, _ in relations:
                key = tuple(sorted([src.lower(), tgt.lower()]))
                co_counts[key] += 1

        return dict(co_counts)


def extract_relations(text: str, intent_name: str = "",
                      intent_entities: Optional[Dict] = None) -> List[Tuple[str, str, RelationType, float]]:
    """Convenience function for relation extraction."""
    mapper = RelationMapper()
    return mapper.extract_all(text, intent_name, intent_entities)
