"""
Entity Extractor — NER extraction from text for JARVIS MK-X.

Extracts entities from natural language using:
1. Pattern-based rules (fast, deterministic)
2. Contextual inference from intent/entities
3. Memory-based entity recognition

No ML dependencies — pure Python with regex patterns.
Designed for speed (< 5ms per extraction).
"""

from __future__ import annotations

import re
import logging
from typing import Dict, List, Optional, Set, Tuple

from knowledge_graph.graph import EntityType

logger = logging.getLogger("jarvis.knowledge_graph.extractor")

# Entity patterns — ordered by specificity
_PATTERNS: List[Tuple[EntityType, re.Pattern]] = [
    # File paths (Windows and Unix)
    (EntityType.FILE, re.compile(
        r'(?:[A-Za-z]:\\[\w\\.\-\s]+|~/[\w/.\-]+|\./[\w/.\-]+|/[\w/.\-]+|[\w/\\]+\.\w{1,5})\b'
    )),
    # Applications (known names)
    (EntityType.APPLICATION, re.compile(
        r'\b(chrome|firefox|edge|vscode|visual studio code|notepad\+\+|spotify|discord|'
        r'slack|zoom|teams|word|excel|powerpoint|outlook|file manager|explorer|'
        r'cmd|powershell|terminal|calculator|paint|snipping tool|task manager|'
        r'youtube|github|stackoverflow|chatgpt|ollama|flask|pycharm|pylint)\b',
        re.IGNORECASE
    )),
    # Commands / CLI
    (EntityType.COMMAND, re.compile(
        r'\b(ping|dir|ls|cd|mkdir|rm|del|copy|move|git|npm|pip|python|node|'
        r'curl|wget|ssh|docker|docker-compose|systemctl|brew|choco|winget|'
        r'tasklist|netstat|ipconfig|ifconfig|cat|grep|find|sort|head|tail)\b',
        re.IGNORECASE
    )),
    # Tools / tech
    (EntityType.TOOL, re.compile(
        r'\b(python|javascript|typescript|java|c\+\+|rust|go|ruby|php|swift|'
        r'html|css|sql|json|yaml|toml|xml|api|rest|graphql|grpc|'
        r'flask|django|fastapi|react|vue|angular|node\.?js|express|'
        r'postgresql|mysql|sqlite|mongodb|redis|docker|kubernetes|'
        r'git|github|gitlab|bitbucket|jira|confluence|'
        r'tensorflow|pytorch|scikit-learn|pandas|numpy|'
        r'ollama|groq|gemini|openrouter|openai|anthropic)\b',
        re.IGNORECASE
    )),
    # People (capitalized names after known context words)
    (EntityType.PERSON, re.compile(
        r'(?:created by|made by|built by|owned by|belongs to|for)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
    )),
    # Projects (capitalized multi-word or known project patterns)
    (EntityType.PROJECT, re.compile(
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b(?=\s+(?:project|app|application|system|tool|script))'
    )),
    # Concepts (quoted or emphasized terms)
    (EntityType.CONCEPT, re.compile(
        r'(?:concept of|idea of|notion of|about)\s+["\']?([^"\'.,]+)["\']?'
    )),
    # Organizations
    (EntityType.ORGANIZATION, re.compile(
        r'\b(Google|Microsoft|Apple|Amazon|Meta|OpenAI|Anthropic|'
        r'GitHub|Stack Overflow|Mozilla|Linux Foundation|Apache|'
        r'JetBrains|Visual Studio Code|npm|PyPI)\b'
    )),
]

# Common intent-to-entity mappings
_INTENT_ENTITY_MAP: Dict[str, List[Tuple[str, EntityType]]] = {
    "action.open": [("app", EntityType.APPLICATION)],
    "action.search": [("query", EntityType.CONCEPT)],
    "action.file": [("path", EntityType.FILE)],
    "action.shell": [("command", EntityType.COMMAND)],
    "action.process": [("name", EntityType.APPLICATION)],
    "memory.store": [("fact", EntityType.CONCEPT)],
    "vision.screen_capture": [("prompt", EntityType.CONCEPT)],
}

# Stopwords to skip
_STOPWORDS: Set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just", "and", "but", "or", "if",
    "it", "its", "this", "that", "these", "those", "i", "me", "my", "we",
    "you", "your", "he", "him", "his", "she", "her", "they", "them", "their",
    "what", "which", "who", "whom",
}


class EntityExtractor:
    """Extracts entities from natural language text."""

    def __init__(self):
        self._custom_patterns: List[Tuple[EntityType, re.Pattern]] = []
        self._known_entities: Dict[str, EntityType] = {}  # lowercase name -> type

    def register_entity(self, name: str, entity_type: EntityType):
        """Register a known entity for faster extraction."""
        self._known_entities[name.lower()] = entity_type

    def extract_from_text(self, text: str) -> List[Tuple[str, EntityType]]:
        """Extract entities from raw text. Returns list of (name, type)."""
        if not text or not text.strip():
            return []

        found: Dict[str, EntityType] = {}

        # 1. Check known entities first (O(1) per entity)
        words = re.findall(r'\b\w+\b', text.lower())
        for word in words:
            if word in self._known_entities and word not in found:
                found[word] = self._known_entities[word]

        # 2. Pattern-based extraction
        for entity_type, pattern in _PATTERNS + self._custom_patterns:
            for match in pattern.finditer(text):
                name = match.group(1) if match.lastindex else match.group(0)
                name = name.strip().strip("\"'.,;:!?")
                if len(name) < 2 or name.lower() in _STOPWORDS:
                    continue
                if name not in found:
                    found[name] = entity_type

        # 3. Capitalized phrases (heuristic for proper nouns)
        cap_phrases = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', text)
        for phrase in cap_phrases:
            if phrase not in found and phrase.lower() not in _STOPWORDS:
                # Likely a person or project name
                if len(phrase.split()) <= 2:
                    found[phrase] = EntityType.PERSON
                else:
                    found[phrase] = EntityType.PROJECT

        return [(name, etype) for name, etype in found.items()]

    def extract_from_intent(self, intent_name: str, entities: Dict[str, Any]) -> List[Tuple[str, EntityType]]:
        """Extract entities from intent classification results."""
        results = []
        if intent_name in _INTENT_ENTITY_MAP:
            for key, etype in _INTENT_ENTITY_MAP[intent_name]:
                val = entities.get(key)
                if val and isinstance(val, str) and len(val) >= 2:
                    results.append((val.strip(), etype))
        return results

    def extract_all(self, text: str, intent_name: str = "",
                    intent_entities: Optional[Dict] = None) -> List[Tuple[str, EntityType]]:
        """Combined extraction: text + intent context."""
        text_entities = self.extract_from_text(text)
        intent_entities = intent_entities or {}
        intent_ents = self.extract_from_intent(intent_name, intent_entities)

        # Deduplicate, preferring intent-based type
        seen: Dict[str, Tuple[str, EntityType]] = {}
        for name, etype in text_entities:
            key = name.lower()
            if key not in seen:
                seen[key] = (name, etype)

        for name, etype in intent_ents:
            key = name.lower()
            seen[key] = (name, etype)  # Intent overrides text

        return list(seen.values())


def extract_entities(text: str, intent_name: str = "",
                     intent_entities: Optional[Dict] = None) -> List[Tuple[str, EntityType]]:
    """Convenience function for entity extraction."""
    extractor = EntityExtractor()
    return extractor.extract_all(text, intent_name, intent_entities)
