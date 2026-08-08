"""Semantic Search Engine — TF-IDF-like search across all knowledge sources."""

import re
import math
import time
import logging
import threading
from typing import Optional, List, Dict, Any
from collections import Counter, defaultdict

logger = logging.getLogger("jarvis.knowledge_engine.semantic_search")


def _tokenize(text: str) -> list[str]:
    """Simple word tokenization with lowercase and stop word removal."""
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
        'what', 'which', 'who', 'whom',
    }
    words = re.findall(r'\b[a-zA-Z0-9]+\b', text.lower())
    return [w for w in words if w not in stop_words and len(w) > 1]


class SemanticSearchEngine:
    """TF-IDF-like semantic search across all knowledge sources."""

    def __init__(self):
        self._lock = threading.Lock()
        self._index: Dict[str, dict] = {}
        self._doc_count = 0
        self._total_search_ms = 0.0
        self._search_count = 0
        self._idf_cache: Dict[str, float] = {}
        self._idf_dirty = True

    def index_document(self, doc_id: str, content: str, metadata: dict = None) -> None:
        """Index a document for search."""
        tokens = _tokenize(content)
        tf = Counter(tokens)
        with self._lock:
            self._index[doc_id] = {
                "content": content,
                "metadata": metadata or {},
                "tokens": tokens,
                "tf": dict(tf),
                "indexed_at": time.time(),
            }
            self._idf_dirty = True
            self._doc_count = len(self._index)

    def update_index(self, doc_id: str, content: str) -> None:
        """Update an indexed document."""
        with self._lock:
            if doc_id in self._index:
                metadata = self._index[doc_id].get("metadata", {})
            else:
                metadata = {}
        self.index_document(doc_id, content, metadata)

    def remove_document(self, doc_id: str) -> None:
        """Remove a document from the index."""
        with self._lock:
            if doc_id in self._index:
                del self._index[doc_id]
                self._idf_dirty = True
                self._doc_count = len(self._index)

    def _compute_idf(self, term: str) -> float:
        """Compute inverse document frequency for a term."""
        if not self._idf_dirty and term in self._idf_cache:
            return self._idf_cache[term]
        containing = sum(
            1 for doc in self._index.values() if term in doc["tf"]
        )
        if containing == 0:
            idf = 0.0
        else:
            idf = math.log((self._doc_count + 1) / (containing + 1)) + 1
        self._idf_cache[term] = idf
        return idf

    def _rebuild_idf_cache(self) -> None:
        """Rebuild the entire IDF cache."""
        self._idf_cache.clear()
        all_terms = set()
        for doc in self._index.values():
            all_terms.update(doc["tf"].keys())
        for term in all_terms:
            self._compute_idf(term)
        self._idf_dirty = False

    def _compute_tfidf(self, doc_id: str, query_tokens: list[str]) -> float:
        """Compute TF-IDF similarity score between query and document."""
        doc = self._index.get(doc_id)
        if not doc:
            return 0.0
        score = 0.0
        doc_len = max(len(doc["tokens"]), 1)
        for token in query_tokens:
            tf = doc["tf"].get(token, 0) / doc_len
            idf = self._compute_idf(token)
            score += tf * idf
        return score

    def tokenize(self, text: str) -> list[str]:
        """Public tokenize method."""
        return _tokenize(text)

    def search(self, query: str, max_results: int = 5, min_score: float = 0.3) -> List[dict]:
        """Semantic search across all indexed documents."""
        start = time.perf_counter()
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        with self._lock:
            if self._idf_dirty:
                self._rebuild_idf_cache()
            doc_ids = list(self._index.keys())

        scores = []
        for doc_id in doc_ids:
            score = self._compute_tfidf(doc_id, query_tokens)
            if score >= min_score:
                scores.append((doc_id, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
        for doc_id, score in scores[:max_results]:
            doc = self._index[doc_id]
            results.append({
                "id": doc_id,
                "type": doc.get("metadata", {}).get("type", "document"),
                "content": doc["content"][:500],
                "score": round(score, 4),
                "metadata": doc.get("metadata", {}),
            })

        elapsed = (time.perf_counter() - start) * 1000
        with self._lock:
            self._total_search_ms += elapsed
            self._search_count += 1

        return results

    def get_index_stats(self) -> dict:
        """Return statistics about the search index."""
        with self._lock:
            avg_search = (
                self._total_search_ms / self._search_count
                if self._search_count > 0 else 0.0
            )
            total_tokens = sum(len(d["tokens"]) for d in self._index.values())
            return {
                "total_indexed": self._doc_count,
                "total_tokens": total_tokens,
                "avg_search_ms": round(avg_search, 2),
                "total_searches": self._search_count,
            }


_instance: Optional[SemanticSearchEngine] = None


def get_semantic_search() -> SemanticSearchEngine:
    global _instance
    if _instance is None:
        _instance = SemanticSearchEngine()
    return _instance
