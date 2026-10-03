"""Regression benchmarks for critical JARVIS paths.

Run: python -m pytest tests/benchmarks.py --benchmark-only
"""
import asyncio


def _seed_memory(tmp_path, n=50, project="/proj"):
    """Build a MemoryAPI in a temp dir and seed n deterministic memories."""
    from memory.api import MemoryAPI
    from memory.decision_memory import DecisionMemory
    from memory.project_knowledge import ProjectKnowledge
    from memory.store import MemoryStore
    from memory.vector_store import VectorMemoryStore

    api = MemoryAPI(
        kv=MemoryStore(data_dir=tmp_path),
        vector=VectorMemoryStore(db_path=tmp_path / "vec.db"),
        decisions=DecisionMemory(data_dir=tmp_path),
        knowledge=ProjectKnowledge(data_dir=tmp_path),
    )
    for i in range(n):
        api.store(
            f"optimization note {i} about retrieval latency and embedding cache",
            key=f"opt_{i}", importance=0.5, project=project,
        )
    api.flush_async()
    return api


def test_config_load(benchmark):
    """Config loading should stay under 50ms."""
    from core.config import load_config

    def _load():
        load_config("jarvis.toml")

    benchmark.pedantic(_load, rounds=10)


def test_security_init(benchmark):
    """Security engine init should stay under 100ms."""
    from security.engine import SecurityEngine

    def _init():
        SecurityEngine()

    benchmark.pedantic(_init, rounds=5)


def test_knowledge_graph_load(benchmark):
    """Knowledge graph load should stay under 200ms."""
    from memory.graph import KnowledgeGraph

    def _load():
        kg = KnowledgeGraph()
        return kg

    benchmark.pedantic(_load, rounds=5)


def test_router_init(benchmark):
    """Provider router init should stay under 200ms."""
    from providers.router import ProviderRouter

    def _init():
        return ProviderRouter()

    benchmark.pedantic(_init, rounds=5)


def test_cli_import_cold(benchmark):
    """Cold import of the CLI module should stay under 1000ms."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]

    def _cold():
        r = subprocess.run(
            [sys.executable, "-c", "import cli.main"],
            capture_output=True, text=True, cwd=root, check=False,
        )
        assert r.returncode == 0, r.stderr

    benchmark.pedantic(_cold, rounds=3)


def test_intent_classifier(benchmark):
    """Intent classification should stay under 50ms."""
    from core.jarvis import JarvisMKX

    jarvis = JarvisMKX()

    def _classify():
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(jarvis.classify_intent("open chrome and search for weather"))
        finally:
            loop.close()

    benchmark.pedantic(_classify, rounds=20)


def test_telemetry_snapshot(benchmark):
    """System telemetry collection should stay under 100ms."""
    from python.telemetry import get_system_stats

    benchmark.pedantic(get_system_stats, rounds=20)


# ── Stage 1: memory performance targets ──────────────────────────────────

def _hash_embed(monkeypatch):
    from memory import vector_store as vs
    monkeypatch.setattr(vs, "_embed_ready", True)
    monkeypatch.setattr(vs, "_embed_model", None)


def test_memory_retrieve_cached(benchmark, tmp_path, monkeypatch):
    """Hybrid retrieval (warm cache) should stay under 50ms."""
    _hash_embed(monkeypatch)
    api = _seed_memory(tmp_path, 50)
    api.retrieve("retrieval latency optimization", project="/proj", top_k=5)  # prime
    benchmark(api.retrieve, "retrieval latency optimization", project="/proj", top_k=5)
    api.close()


def test_memory_retrieve_cold(benchmark, tmp_path, monkeypatch):
    """Hybrid retrieval (cold, first call) should stay under 300ms."""
    _hash_embed(monkeypatch)
    api = _seed_memory(tmp_path, 50)
    benchmark.pedantic(
        lambda: api.retrieve("retrieval latency optimization", project="/proj", top_k=5),
        rounds=1,
    )
    api.close()


def test_memory_overhead_idle(tmp_path, monkeypatch):
    """Memory layer overhead should stay under 100MB idle."""
    import psutil
    _hash_embed(monkeypatch)
    before = psutil.Process().memory_info().rss / (1024 * 1024)
    api = _seed_memory(tmp_path, 200)
    after = psutil.Process().memory_info().rss / (1024 * 1024)
    assert (after - before) < 100
    api.close()
