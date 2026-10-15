"""Tests for pass-13: local RAG wired into the bridge chat pipeline.

Hermetic: the workspace corpus lives in tmp_path with ProjectContext
monkeypatched, the bridge runs in-process on an ephemeral port with the echo
backend, and no test touches the network or the real user workspace.

Covers: the knowledge-query gate, doc.search output parsing, context-block
building (score floor, one passage per source, char budgets), the index cache
(only one TF-IDF build per corpus state), fail-open behavior on retrieval
errors, and end-to-end injection through POST /v1/chat including
trim_messages preservation and page-context composition.
"""

from __future__ import annotations

import json
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BRIDGE_DIR = ROOT / "jbrowser-bridge"
sys.path.insert(0, str(BRIDGE_DIR))

from server import serve  # noqa: E402
import rag  # noqa: E402
from tools import doc_retrieval as dr  # noqa: E402

PROJECT = __import__("core.project", fromlist=["ProjectContext"]).ProjectContext


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """Tiny corpus: one on-topic doc, one unrelated."""
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "research.md").write_text(
        "# Quantum Computing Notes\n\n"
        "Quantum computing uses qubits instead of classical bits.\n\n"
        "Error correction remains the central engineering challenge for "
        "quantum computing hardware. Surface codes protect the qubit state "
        "by spreading one logical qubit across many physical qubits.\n",
        encoding="utf-8",
    )
    (tmp_path / "notes" / "shopping.txt").write_text(
        "Grocery list for the week: milk, eggs, coffee beans.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        PROJECT, "discover",
        staticmethod(lambda cwd=None: type("C", (), {"root_path": tmp_path})()),
    )
    dr._INDEX_CACHE.clear()
    yield tmp_path
    dr._INDEX_CACHE.clear()


KNOW_Q = "how does error correction work in quantum computing?"
GREETING = "hi"


# ────────────────────────────────────────────────────────────── gate

def test_gate_fires_on_knowledge_queries():
    assert rag.looks_like_knowledge_query(KNOW_Q)
    assert rag.looks_like_knowledge_query("summarize my sourdough notes")
    assert rag.looks_like_knowledge_query("what is a surface code?")


def test_gate_skips_smalltalk():
    for text in ("hi", "ok thanks", "thanks!", "fix it", "ok", "help"):
        assert not rag.looks_like_knowledge_query(text), text
    assert not rag.looks_like_knowledge_query("")


def test_gate_skips_imperatives_and_generic_phrases():
    """No knowledge cue → no retrieval, even with plenty of content tokens.
    ("plain text prompt" once slipped through and timed out a bridge test
    by triggering a full real-corpus index build.)"""
    for text in ("plain text prompt", "fix the login bug", "follow-up question",
                 "restart the server now"):
        assert not rag.looks_like_knowledge_query(text), text


# ──────────────────────────────────────────────── doc.search parsing

def test_parse_hits_extracts_ranked_passages():
    output = (
        "Top matches for 'surface code' across 12 indexed chunks:\n"
        "1. [0.412] notes/research.md (chunk 2)\n"
        "   Error correction remains the central engineering challenge…\n"
        "2. [0.118] notes/research.md (chunk 1)\n"
        "   Quantum computing uses qubits instead of classical bits.\n"
    )
    hits = rag._parse_hits(output, limit=5)
    assert len(hits) == 2
    assert hits[0]["source"] == "notes/research.md"
    assert hits[0]["chunk"] == 2
    assert hits[0]["score"] == pytest.approx(0.412)
    assert "engineering challenge" in hits[0]["snippet"]


def test_parse_hits_empty():
    assert rag._parse_hits("No documents match 'xyz'. (9 chunks were searched.)", 5) == []


# ──────────────────────────────────────────────────── context block

def test_context_block_cites_workspace_doc(workspace):
    block = rag.build_context_block(KNOW_Q)
    assert block is not None
    assert block["role"] == "system"
    assert "Relevant passages" in block["content"]
    assert "notes/research.md" in block["content"]
    assert "error correction" in block["content"].lower()


def test_context_block_returns_none_for_smalltalk(workspace):
    assert rag.build_context_block(GREETING) is None


def test_context_block_returns_none_when_corpus_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(
        PROJECT, "discover",
        staticmethod(lambda cwd=None: type("C", (), {"root_path": tmp_path})()),
    )
    dr._INDEX_CACHE.clear()
    try:
        assert rag.build_context_block(KNOW_Q) is None
    finally:
        dr._INDEX_CACHE.clear()


def test_context_block_fail_open_on_retrieval_error(workspace, monkeypatch):
    def boom(args):
        raise RuntimeError("index exploded")

    monkeypatch.setattr(dr, "doc_search", boom)
    assert rag.build_context_block(KNOW_Q) is None


def test_context_block_fail_open_on_missing_module(monkeypatch):
    # Simulate the tools package being unavailable (broken install): the
    # import inside build_context_block raises, and the gate must swallow it.
    monkeypatch.setitem(sys.modules, "tools.doc_retrieval", None)
    try:
        assert rag.build_context_block(KNOW_Q) is None
    finally:
        sys.modules.pop("tools.doc_retrieval", None)


def test_context_block_budgets(workspace):
    block = rag.build_context_block(KNOW_Q)
    assert block is not None
    assert len(block["content"]) <= rag._MAX_CONTEXT_CHARS + 400  # header slack


# ─────────────────────────────────────────────────────── index cache

def test_index_cache_rebuilds_only_when_corpus_changes(workspace):
    rag.build_context_block(KNOW_Q)
    entries = list(dr._INDEX_CACHE.values())
    assert len(entries) == 1
    refs_first, _ = entries[0][1], entries[0][2]
    # Second query, same corpus → same cached object (no rebuild).
    rag.build_context_block("what is a surface code?")
    assert dr._INDEX_CACHE[str(workspace)][1] is refs_first
    # Rewrite a doc → signature changes → fresh index.
    (workspace / "notes" / "research.md").write_text(
        "# Rewritten\n\nCompletely different content about volcanoes.\n",
        encoding="utf-8",
    )
    rag.build_context_block("what do my notes say about volcanoes?")
    assert dr._INDEX_CACHE[str(workspace)][1] is not refs_first


# ────────────────────────────────────────────────────────── inject()

def test_warm_gate_only_the_starter_turn_waits(workspace, monkeypatch):
    """Big-corpus semantics: the turn that starts the warm waits up to the
    budget and then answers unburdened; turns arriving while the build is
    in flight pay ~0; after completion every turn gets the index fast."""
    import time as _time

    rag._WARM_STARTED = False
    rag._WARM_DONE.clear()

    real_search = dr.doc_search  # capture BEFORE patching (avoid self-recursion)

    def slow_search(args):
        _time.sleep(1.0)  # exceeds _WARM_MAX_WAIT_S (0.75s) — a "big corpus"
        return real_search(args)

    monkeypatch.setattr(dr, "doc_search", slow_search)
    try:
        t0 = _time.perf_counter()
        assert rag._ensure_warm() is False  # starter: waited, gave up
        starter_wait = _time.perf_counter() - t0
        assert starter_wait >= 0.2

        t0 = _time.perf_counter()
        assert rag._ensure_warm() is False  # in-flight: no wait
        assert _time.perf_counter() - t0 < 0.05

        assert rag._WARM_DONE.wait(5.0)  # build finishes
        t0 = _time.perf_counter()
        assert rag._ensure_warm() is True  # ready: instant
        assert _time.perf_counter() - t0 < 0.05
    finally:
        rag._WARM_STARTED = False
        rag._WARM_DONE.clear()


def test_inject_prepends_block_without_mutating_input(workspace):
    original = [{"role": "user", "content": KNOW_Q}]
    out = rag.inject(original)
    assert out is not original
    assert out[0]["role"] == "system"
    assert original == [{"role": "user", "content": KNOW_Q}]


def test_inject_noop_for_smalltalk(workspace):
    original = [{"role": "user", "content": GREETING}]
    assert rag.inject(original) is original


# ───────────────────────────────────────────────── engine composition

def test_trim_messages_pins_leading_rag_block():
    from engine import Budget, trim_messages  # noqa: E402

    block = {"role": "system", "content": "Relevant passages:\n[x] y"}
    msgs = [block] + [{"role": "user", "content": f"turn {i}"} for i in range(8)]
    out = trim_messages(msgs, Budget(max_messages=3))
    assert out[0] is block
    assert len(out) == 3


def test_model_gateway_prompt_keeps_rag_head_and_page_tail(workspace):
    from engine import Budget, ModelGatewayEngine  # noqa: E402

    async def fake_streamer(messages, system_prompt, max_tokens):
        yield "ok"

    eng = ModelGatewayEngine(streamer=fake_streamer, budget=Budget(max_messages=6))
    # Injection happens in the bridge funnel before the engine sees messages;
    # compose through rag.inject exactly as server._chat does.
    prompt = eng._build_prompt(
        rag.inject([{"role": "user", "content": KNOW_Q}]),
        {"title": "Example Page", "url": "https://example.com"},
    )
    assert prompt[0]["role"] == "system"
    assert "Relevant passages" in prompt[0]["content"]
    assert prompt[-1]["role"] == "system"
    assert "Example Page" in prompt[-1]["content"]


# ───────────────────────────────────────────── end-to-end over HTTP

@pytest.fixture()
def bridge(workspace):
    httpd = serve(host="127.0.0.1", port=0, backend_kind="echo")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield base
    finally:
        httpd.shutdown()
        httpd.server_close()


def _chat_events(base, payload):
    req = urllib.request.Request(
        base + "/v1/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    deltas = []
    with urllib.request.urlopen(req, timeout=10) as r:
        for raw_line in r:
            line = raw_line.decode().strip()
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            if event["type"] == "delta":
                deltas.append(event["text"])
            if event["type"] in ("done", "error"):
                break
    return "".join(deltas)


def test_chat_injects_workspace_context(bridge):
    joined = _chat_events(bridge, {"session_id": "rag1", "text": KNOW_Q})
    assert KNOW_Q in joined  # echo integrity: the turn still went through
    assert "Relevant passages" in joined  # system message reached the backend


def test_chat_skips_context_for_smalltalk(bridge):
    joined = _chat_events(bridge, {"session_id": "rag2", "text": GREETING})
    assert "Relevant passages" not in joined


def test_chat_respects_jarvis_rag_disable(bridge, monkeypatch):
    monkeypatch.setenv("JARVIS_RAG", "0")
    joined = _chat_events(bridge, {"session_id": "rag3", "text": KNOW_Q})
    assert "Relevant passages" not in joined


def test_chat_rag_failure_does_not_break_stream(bridge, monkeypatch):
    monkeypatch.setattr(
        dr, "doc_search",
        lambda args: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    joined = _chat_events(bridge, {"session_id": "rag4", "text": KNOW_Q})
    assert KNOW_Q in joined
    assert "Relevant passages" not in joined
