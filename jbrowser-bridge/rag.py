"""Local-RAG chat context — AnythingLLM's core bet, wired into the bridge.

The workspace already has a private TF-IDF retriever (``tools.doc_retrieval``)
that indexes the user's own documents — notes, saved articles
(``memory/reading/``), archived pages (``memory/archive/``). This module puts
that corpus behind the browser chat: knowledge-seeking turns get their most
relevant document passages injected as a system message, so the model answers
"what do MY documents say" instead of guessing — with zero uploads, zero
network, zero embeddings.

Injection happens in the bridge's ``_chat`` funnel (server.py) as a LEADING
system message, which composes with every backend for free:

* ``engine.trim_messages`` treats a leading system message as pinned head —
  it survives the message-window trim that would otherwise drop it.
* ``ModelGatewayEngine._build_prompt`` appends page context as a TRAILING
  system message, so workspace context and page context never collide.
* The agent engine folds it into the goal like any other user content.

Design rules (all learned the hard way in the passes so far):

* **Fail open.** Retrieval is a bonus, never a dependency: any exception or
  empty result returns ``None`` and the turn proceeds exactly as before.
* **Cheap gate.** Non-knowledge turns ("hi", "thanks", page questions) pay
  zero retrieval cost — see ``looks_like_knowledge_query``.
* **Bounded.** Hard caps on sources, snippet length, and total context size
  so a big corpus can never blow the input budget.
"""

from __future__ import annotations

import logging
import re
import threading
import time

logger = logging.getLogger("jbrowser-bridge.rag")

# ── Tuning knobs ─────────────────────────────────────────────────────────────
_MAX_SOURCES = 3          # distinct documents to cite per turn
_MAX_SNIPPET_CHARS = 700  # per-passage budget
_MAX_CONTEXT_CHARS = 3200  # total injected context ceiling (~800 tokens)
_MIN_QUERY_TOKENS = 2     # "what is" alone is not worth an index build
# Above single-term TF-IDF overlap (~0.08 max) and below real multi-term
# matches (~0.2+): one shared keyword must not inject 800 tokens of noise.
_MIN_SCORE = 0.15

# Stopwords mirror tools.doc_retrieval's tokenizer; keep the gate's own list
# tiny and focused on chat filler so greeting turns are filtered before any
# corpus work happens.
_FILLER = frozenset(
    "hi hello hey thanks thank please me my i you it the a an is are do does "
    "did can could would should what where when who how why ok okay yeah yep "
    "no yes and or but so to of in on for with about as at by from that this "
    "these those there here tell say said give show find get got make made "
    "just also very really more most some any all".split()
)

_WORD_RE = re.compile(r"[a-zA-Z0-9_]{2,}")

# Explicit knowledge cues: a question word, a knowledge verb, or a reference
# to the user's own documents. The gate requires BOTH ≥2 content tokens AND
# one of these cues — precision over recall, because RAG is additive: a
# keyword-only or imperative query ("fix the login bug", "plain text
# prompt") skips retrieval rather than risk a pointless index walk.
_KNOWLEDGE_CUE_RE = re.compile(
    r"\b(how|what|why|when|where|which|who|explain|summarize|summarise|compare|"
    r"difference|define|definition|meaning|notes?|documents?|docs?|files?|"
    r"archives?|according)\b",
    re.IGNORECASE,
)

_SCORE_LINE_RE = re.compile(r"^\s*\d+\.\s+\[([\d.]+)\]\s+(.+?)\s+\(chunk (\d+)\)$")

# ── Background index warm ────────────────────────────────────────────────────
# A cold TF-IDF build over a big workspace costs seconds (measured ~4.6 s on
# this repo) — far too much to bolt onto a chat turn's TTFT. So the FIRST
# knowledge-y turn kicks off a daemon warm thread and waits only
# _WARM_MAX_WAIT_S: small corpora (tests, small workspaces) finish inside
# the budget and get full context immediately; big corpora answer that one
# turn unburdened while the build continues, and every later turn is a
# sub-millisecond cache hit. Fail-open either way.
_WARM_LOCK = threading.Lock()
_WARM_DONE = threading.Event()
_WARM_STARTED = False
_WARM_MAX_WAIT_S = 0.75


def _warm_index() -> None:
    try:
        from tools.doc_retrieval import doc_search

        doc_search({"query": "warm the retrieval index", "limit": 1})  # build + cache
        logger.info("rag: index warm complete (queries=%d limit=%d)", _MAX_SOURCES, _WARM_MAX_WAIT_S)
    except Exception:  # noqa: BLE001 — warm is best-effort
        logger.warning("rag: warm failed (degraded to cold retrieval)")
        pass
    finally:
        _WARM_DONE.set()


def _ensure_warm(wait: bool = True) -> bool:
    """Start the background warm once; True if the index is ready to use.

    Only the turn that STARTS the warm waits (bounded by _WARM_MAX_WAIT_S);
    turns arriving while the build is still in flight pay ~0 and answer
    unburdened, so the process's total added latency is capped at one
    ≤750ms stall on its very first knowledge-y turn.

    ``wait=False`` is for BOOT warmup: kick the build off and return
    immediately — startup must never stall on it, and by the time a real
    knowledge turn arrives the index is usually ready (0ms added).
    """
    global _WARM_STARTED
    if _WARM_DONE.is_set():
        return True
    start_warm = False
    with _WARM_LOCK:
        if not _WARM_STARTED:
            _WARM_STARTED = True
            start_warm = True
    if start_warm:
        threading.Thread(target=_warm_index, daemon=True, name="rag-warm").start()
        if wait:
            # Wait OUTSIDE the lock: a turn arriving mid-build must never
            # queue behind this turn's wait — it should fail open instantly.
            return _WARM_DONE.wait(_WARM_MAX_WAIT_S)
        return False
    return False  # warm already in flight from an earlier turn — don't wait


def looks_like_knowledge_query(text: str) -> bool:
    """Cheap heuristic: does this turn deserve a corpus lookup?

    Fires when the turn carries ≥2 content tokens AND an explicit knowledge
    cue (question word, knowledge verb, or document reference). Greetings,
    acknowledgments, imperative commands, and generic phrases never trigger
    retrieval — the gate errs toward skipping, since context injection is a
    bonus and a bad guess costs a corpus walk plus noisy context.
    """
    text = (text or "").strip()
    if len(text) < 6:
        return False
    words = _WORD_RE.findall(text.lower())
    content = [w for w in words if w not in _FILLER]
    if len(content) < _MIN_QUERY_TOKENS:
        return False
    return bool(_KNOWLEDGE_CUE_RE.search(text))


def _query_from_messages(messages: list[dict]) -> str:
    """The retrieval query is the latest user turn's text."""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):  # content-parts shape
                parts = " ".join(
                    str(p.get("text") or "") for p in content if isinstance(p, dict)
                )
                if parts.strip():
                    return parts.strip()
    return ""


def _parse_hits(output: str, limit: int) -> list[dict]:
    """Parse doc.search's receipt-style output into structured hits.

    Line shape (from tools.doc_retrieval.doc_search):
        ``1. [0.412] notes/research.md (chunk 2)``
        ``   <snippet…>``
    """
    hits: list[dict] = []
    current: dict | None = None
    for line in output.splitlines():
        m = _SCORE_LINE_RE.match(line)
        if m:
            if current is not None:  # a new rank header ends the previous hit
                hits.append(current)
            current = {
                "score": float(m.group(1)),
                # Normalize Windows backslashes so citations are portable
                # (doc_search emits native OS separators via path.relative_to).
                "source": m.group(2).strip().replace("\\", "/"),
                "chunk": int(m.group(3)),
                "snippet": "",
            }
            continue
        if current is not None and line.startswith("   ") and line.strip():
            snippet = line.strip()
            current["snippet"] = (
                (current["snippet"] + " " + snippet) if current["snippet"] else snippet
            )[:_MAX_SNIPPET_CHARS]
        elif current is not None and line.strip() and not line.startswith("   "):
            hits.append(current)  # next rank header ends this passage
            current = None
    if current is not None:
        hits.append(current)
    return hits[:limit]


def build_context_block(query: str) -> dict | None:
    """Retrieve relevant workspace passages for ``query``.

    Returns a leading system message dict, or ``None`` when nothing relevant
    exists. Never raises — retrieval failure degrades to plain chat.
    """
    query = (query or "").strip()
    if not looks_like_knowledge_query(query):
        return None
    if not _ensure_warm():
        return None  # index still building — answer unburdened this turn
    try:
        from tools.doc_retrieval import doc_search

        t0 = time.monotonic()
        try:
            res = doc_search({"query": query, "limit": _MAX_SOURCES + 2})
        finally:
            duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info("rag: retrieval %s in %.1fms (query_tokens=%d)",
                    "success" if getattr(res, "success", False) else "failed",
                    duration_ms, len(_WORD_RE.findall(query)))
        if not getattr(res, "success", False) or not getattr(res, "output", ""):
            return None

        hits = [
            h for h in _parse_hits(res.output, _MAX_SOURCES)
            if h["score"] >= _MIN_SCORE and h["snippet"]
        ]
        if not hits:
            return None

        sections: list[str] = []
        used = 0
        seen_sources: set[str] = set()
        for h in hits:
            if len(sections) >= _MAX_SOURCES or used >= _MAX_CONTEXT_CHARS:
                break
            if h["source"] in seen_sources:
                continue  # one passage per document, best-ranked wins
            seen_sources.add(h["source"])
            passage = h["snippet"][: min(_MAX_SNIPPET_CHARS, _MAX_CONTEXT_CHARS - used)]
            sections.append(f"[{h['source']} · chunk {h['chunk']} · score {h['score']:.3f}]\n{passage}")
            used += len(sections[-1]) + 2

        if not sections:
            return None
        return {
            "role": "system",
            "content": (
                "Relevant passages from the user's local documents (private, "
                "TF-IDF matched — cite the file when you use one; if nothing "
                "here helps, just answer normally):\n\n"
                + "\n\n".join(sections)
            ),
        }
    except Exception:  # noqa: BLE001 — context must never break chat
        return None


def inject(messages: list[dict]) -> list[dict]:
    """Wrap a chat turn: prepend workspace context when it adds signal.

    The returned list is always a NEW list — the caller's thread history is
    never mutated in place.
    """
    try:
        query = _query_from_messages(messages)
        if not query:
            return messages
        block = build_context_block(query)
        if block is None:
            return messages
        return [block] + list(messages)
    except Exception as exc:  # noqa: BLE001 — context must never break chat
        logger.debug("rag: injection skipped: %s", exc)
        return messages
