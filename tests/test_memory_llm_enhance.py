"""Tests for 1B-powered memory retrieval enhancements.

Tests the reformulate, rerank, and condense modules without requiring
a running Ollama instance (uses mocked responses).
"""

from unittest.mock import patch

import pytest


def _ollama_available() -> bool:
    """Check if Ollama is running."""
    import urllib.request
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── Query Reformulation Tests ───────────────────────────────────────────────

class TestReformulate:
    """Test query reformulation (regex fast path + 1B fallback)."""

    def test_strip_filler_words(self):
        """Common filler words are removed."""
        from memory.llm.reformulate import reformulate_query

        with patch("memory.llm.reformulate.ensure_model", return_value=False):
            result = reformulate_query("what is my name?")
            assert len(result) > 0

    def test_preserve_content_words(self):
        """Content words are preserved."""
        from memory.llm.reformulate import reformulate_query

        with patch("memory.llm.reformulate.ensure_model", return_value=False):
            result = reformulate_query("tell me about the authentication bug")
            assert "authentication" in result.lower()
            assert "bug" in result.lower()

    def test_empty_query(self):
        """Empty query returns empty."""
        from memory.llm.reformulate import reformulate_query

        result = reformulate_query("")
        assert result == ""

    def test_llm_fallback(self):
        """Complex queries fall back to 1B model."""
        from memory.llm.reformulate import reformulate_query

        with patch("memory.llm.reformulate.ensure_model", return_value=True), \
             patch("memory.llm.reformulate.query_ollama", return_value="authentication security vulnerability"):
            result = reformulate_query("can you tell me everything you know about the security issues we found last week?")
            assert "authentication" in result.lower() or "security" in result.lower()


# ── Reranking Tests ─────────────────────────────────────────────────────────

class TestRerank:
    """Test memory reranking with 1B model."""

    def test_single_memory_passthrough(self):
        """Single memory passes through without reranking."""
        from memory.llm.rerank import rerank_memories

        memories = [{"content": "user name is Aayan", "type": "identity"}]
        result = rerank_memories("what is my name?", memories)
        assert len(result) == 1
        assert result[0]["content"] == "user name is Aayan"

    def test_empty_memories(self):
        """Empty memories return empty."""
        from memory.llm.rerank import rerank_memories

        result = rerank_memories("query", [])
        assert result == []

    def test_max_results_limit(self):
        """Results are limited to max_results."""
        from memory.llm.rerank import rerank_memories

        memories = [
            {"content": f"memory {i}", "type": "note"}
            for i in range(10)
        ]
        with patch("memory.llm.rerank.ensure_model", return_value=False):
            result = rerank_memories("query", memories, max_results=3)
            assert len(result) <= 3

    def test_rerank_with_mock(self):
        """1B model reranking reorders results."""
        from memory.llm.rerank import rerank_memories

        memories = [
            {"content": "user likes Python", "type": "preference"},
            {"content": "project uses TypeScript", "type": "project"},
            {"content": "user name is Aayan", "type": "identity"},
        ]
        with patch("memory.llm.rerank.ensure_model", return_value=True), \
             patch("memory.llm.rerank.query_ollama", return_value="[3, 2, 9]"):
            result = rerank_memories("what is my name?", memories, max_results=2)
            # Score 9 (identity) should be first
            assert result[0]["content"] == "user name is Aayan"


# ── Condensation Tests ──────────────────────────────────────────────────────

class TestCondense:
    """Test context condensation with 1B model."""

    def test_empty_memories(self):
        """Empty memories return empty string."""
        from memory.llm.condense import condense_memories

        result = condense_memories([])
        assert result == ""

    def test_short_memories_passthrough(self):
        """Short memories pass through without condensation."""
        from memory.llm.condense import condense_memories

        memories = [{"content": "short memory"}]
        result = condense_memories(memories, max_chars=500)
        assert "short memory" in result

    def test_long_memories_condensed(self):
        """Long memories are condensed by 1B model."""
        from memory.llm.condense import condense_memories

        memories = [
            {"content": "user name is Aayan, software developer, works on JARVIS project"},
            {"content": "prefers Python over JavaScript, uses VS Code"},
            {"content": "project uses Ollama for local inference, has 2GB MX130 GPU"},
        ]
        with patch("memory.llm.condense.ensure_model", return_value=True), \
             patch("memory.llm.condense.query_ollama", return_value="- Aayan: software developer\n- Prefers Python\n- JARVIS project with Ollama"):
            result = condense_memories(memories, query="tell me about the user", max_chars=200)
            assert "Aayan" in result
            assert len(result) <= 200


# ── Common Utilities Tests ──────────────────────────────────────────────────

class TestCommon:
    """Test shared utilities."""

    def test_model_name_default(self):
        """Default model is qwen2.5:1.5b."""
        from memory.llm.common import MODEL_NAME
        assert MODEL_NAME == "qwen2.5:1.5b"

    def test_query_ollama_failure(self):
        """query_ollama returns None on connection failure."""
        from memory.llm.common import query_ollama

        result = query_ollama("nonexistent-model", "test", timeout=1.0)
        assert result is None


# ── Integration Tests ───────────────────────────────────────────────────────

@pytest.mark.skipif(not _ollama_available(), reason="Ollama not running")
class TestIntegration:
    """Integration tests (require Ollama running with qwen2.5:1.5b)."""

    def test_reformulate_live(self):
        """Live test: reformulate a real query."""
        from memory.llm.reformulate import reformulate_query

        result = reformulate_query("what do you know about my name?")
        assert len(result) > 0
        assert isinstance(result, str)

    def test_condense_live(self):
        """Live test: condense real memories."""
        from memory.llm.condense import condense_memories

        memories = [
            {"content": "User name is Aayan, software developer"},
            {"content": "Project is JARVIS MK-X, autonomous engineering agent"},
            {"content": "Platform: Windows, uses Ollama for local inference"},
        ]
        result = condense_memories(memories)
        assert len(result) > 0
        assert "Aayan" in result or "JARVIS" in result
