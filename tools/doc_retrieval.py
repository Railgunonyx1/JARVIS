"""Local document retrieval — private search over the workspace's own files.

Derived from AnythingLLM's core bet (local-first document RAG): the assistant
should answer "what do MY documents say about X" without uploading anything.
This is the zero-dependency slice: a TF-IDF index built with the stdlib, no
embeddings, no model download, no network. Accuracy scales with the corpus;
for a personal workspace (tens to hundreds of docs) exact-term TF-IDF is
precisely the right tool — it never hallucinates a match that isn't literal.

Design:

* **Ingest** — walk the workspace for .md/.txt/.pdf/.csv/.json (bounded count
  and size), extract text (pypdf for PDFs), chunk by paragraph.
* **Index** — TF-IDF over chunk tokens, built on demand; corpus sizes here are
  small enough that rebuilding per query beats maintaining state.
* **Answer with receipts** — every hit returns the file, chunk number, score,
  and a short snippet. Retrieval shows its work; the model only summarizes
  what's quoted back.
* **Root-safe** — never leaves the project root; skips node_modules/.git and
  friends.
"""

from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path
from typing import Any

from tools.schema import ToolResult

logger = logging.getLogger(__name__)

# ── Bounds (fail closed, stay fast) ─────────────────────────────────────────
_MAX_FILES = 400
_MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB per file
_MAX_CHUNK_CHARS = 1200
_SNIPPET_CHARS = 220
_SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".next", "coverage",
}

_TEXT_EXTS = {".md", ".markdown", ".txt", ".rst", ".csv", ".json", ".py", ".ts",
              ".js", ".html", ".yaml", ".yml", ".toml", ".ics", ".log"}

_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")
_STOPWORDS = frozenset(
    "a an and are as at be but by for from has have if in into is it its of on "
    "or that the their there these they this to was were will with what when "
    "where which who you your our i we he she them then than so not no do does "
    "did can could should would about after all also am any because been before "
    "being between both during each few more most other over same some such "
    "through under until up very while".split()
)


# ── Corpus collection ────────────────────────────────────────────────────────

def _workspace_root() -> Path:
    from core.project import ProjectContext

    return ProjectContext.discover().root_path


def _iter_docs(root: Path) -> list[Path]:
    docs: list[Path] = []
    for path in root.rglob("*"):
        if len(docs) >= _MAX_FILES:
            break
        if path.is_dir():
            continue
        rel = path.relative_to(root)
        if any(part in _SKIP_DIRS or part.startswith(".") and part != "." for part in rel.parts[:-1]):
            continue
        if path.suffix.lower() not in _TEXT_EXTS and path.suffix.lower() != ".pdf":
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        docs.append(path)
    return docs


def _extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join((page.extract_text() or "") for page in reader.pages[:50])
        except Exception as exc:  # corrupted pdf etc — skip, don't fail the scan
            logger.debug("doc_retrieval: skipping %s: %s", path, exc)
            return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _chunk(text: str) -> list[str]:
    """Split into paragraph chunks under the size cap."""
    chunks: list[str] = []
    current = ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= _MAX_CHUNK_CHARS:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            while len(para) > _MAX_CHUNK_CHARS:  # monster paragraph — hard split
                chunks.append(para[:_MAX_CHUNK_CHARS])
                para = para[_MAX_CHUNK_CHARS:]
            current = para
    if current:
        chunks.append(current)
    return chunks


# ── TF-IDF ───────────────────────────────────────────────────────────────────

def _tokens(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text) if len(w) > 1 and w.lower() not in _STOPWORDS]


# ── Index cache (TF-IDF rebuilds only when the corpus actually changes) ──────
# Keyed by root path and validated with a cheap (path, mtime_ns, size)
# signature, so repeated doc.search calls — and now every knowledge-y chat
# turn via the bridge's RAG layer — skip re-reading and re-tokenizing the
# whole corpus. Without this, per-turn retrieval would tax chat TTFT.
_INDEX_CACHE: dict[str, tuple[tuple, list[tuple[Path, int, str]], list[dict[str, float]]]] = {}

# Candidate document list, cached between walk epochs. A full rglob over this
# repo costs ~1.7 s (node_modules/.git are skipped for INDEXING but still
# TRAVERSED), so steady-state RAG lookups must never re-walk: within the
# epoch window the cached list is trusted with ZERO filesystem calls. Edits
# and deletions are still caught per-call by _corpus_signature's per-file
# stat (content change or vanished file → signature mismatch → rebuild).
# Only brand-new files need the periodic re-walk — fine for chat RAG.
_WALK_EPOCH_SECS = 30.0
_CORPUS_CACHE: dict[str, tuple[float, tuple[Path, ...]]] = {}


def _candidate_docs(root: Path) -> list[Path]:
    """Candidate document list with time-bounded re-walks."""
    import time as _time

    key = str(root)
    now = _time.monotonic()
    cached = _CORPUS_CACHE.get(key)
    if cached is not None and (now - cached[0]) <= _WALK_EPOCH_SECS:
        return list(cached[1])
    docs = tuple(_iter_docs(root))
    _CORPUS_CACHE[key] = (now, docs)
    return docs


def _corpus_signature(docs: list[Path]) -> tuple:
    """Cheap change detector: (path, mtime_ns, size) per candidate doc."""
    sig: list[tuple[str, int, int]] = []
    for p in docs:
        try:
            st = p.stat()
        except OSError:
            continue
        sig.append((str(p), st.st_mtime_ns, st.st_size))
    return tuple(sig)


def _build_index(root: Path) -> tuple[list[tuple[Path, int, str]], list[dict[str, float]]]:
    """Return (chunk_refs, chunk_vectors). Vector = term -> weight. Cached."""
    docs = _candidate_docs(root)
    sig = _corpus_signature(docs)
    key = str(root)
    cached = _INDEX_CACHE.get(key)
    if cached is not None and cached[0] == sig:
        return cached[1], cached[2]
    refs: list[tuple[Path, int, str]] = []
    raw: list[list[str]] = []
    for path in docs:
        text = _extract_text(path)
        if not text.strip():
            continue
        for i, chunk in enumerate(_chunk(text)):
            toks = _tokens(chunk)
            if not toks:
                continue
            refs.append((path, i, chunk))
            raw.append(toks)
    n = len(raw)
    if n == 0:
        _INDEX_CACHE[key] = (sig, [], [])
        return [], []
    df: dict[str, int] = {}
    for toks in raw:
        for term in set(toks):
            df[term] = df.get(term, 0) + 1
    vectors: list[dict[str, float]] = []
    for toks in raw:
        tf: dict[str, float] = {}
        for term in toks:
            tf[term] = tf.get(term, 0.0) + 1.0
        vectors.append({t: (c / len(toks)) * math.log((n + 1) / (df[t] + 0.5)) for t, c in tf.items()})
    _INDEX_CACHE[key] = (sig, refs, vectors)
    return refs, vectors


def _query_vector(query: str) -> dict[str, float]:
    toks = _tokens(query)
    if not toks:
        return {}
    return {t: 1.0 for t in toks}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(w * b.get(t, 0.0) for t, w in a.items())
    na = math.sqrt(sum(w * w for w in a.values()))
    nb = math.sqrt(sum(w * w for w in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── Tool actions ─────────────────────────────────────────────────────────────

def _snippet(chunk: str, query_terms: list[str]) -> str:
    """Best window into the chunk: first paragraph containing a query term."""
    lowered = chunk.lower()
    start = 0
    for term in query_terms:
        idx = lowered.find(term)
        if idx > 0:
            start = max(0, idx - 60)
            break
    window = chunk[start:start + _SNIPPET_CHARS].replace("\n", " ").strip()
    return ("…" if start > 0 else "") + window + ("…" if start + _SNIPPET_CHARS < len(chunk) else "")


def doc_search(args: dict[str, Any]) -> ToolResult:
    """TF-IDF search over the workspace's own documents — private, no upload."""
    query = str(args.get("query") or "").strip()
    if not query:
        return ToolResult(success=False, error="query is required — what should I look for in your documents?")
    limit = min(int(args.get("limit") or 5), 15)

    root = _workspace_root()
    try:
        refs, vectors = _build_index(root)
    except Exception as exc:
        return ToolResult(success=False, error=f"index failed: {exc}")
    if not refs:
        return ToolResult(success=True, output="No indexable documents found in the workspace (.md/.txt/.pdf/.csv/.json).")

    qvec = _query_vector(query)
    qterms = list(qvec)
    scored: list[tuple[float, int]] = []
    for i, dvec in enumerate(vectors):
        score = _cosine(qvec, dvec)
        if score > 0:
            scored.append((score, i))
    if not scored:
        return ToolResult(success=True, output=f"No documents match {query!r}. ({len(refs)} chunks were searched.)")
    scored.sort(reverse=True)

    lines = [f"Top matches for {query!r} across {len(refs)} indexed chunks:"]
    for rank, (score, i) in enumerate(scored[:limit], 1):
        path, chunk_no, chunk = refs[i]
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        lines.append(f"{rank}. [{score:.3f}] {rel} (chunk {chunk_no + 1})")
        lines.append(f"   {_snippet(chunk, qterms)}")
    if len(scored) > limit:
        lines.append(f"… and {len(scored) - limit} more.")
    return ToolResult(success=True, output="\n".join(lines))


def doc_stats(args: dict[str, Any]) -> ToolResult:
    """Inventory what is retrievable: file count, chunk count, top terms."""
    root = _workspace_root()
    refs, vectors = _build_index(root)
    if not refs:
        return ToolResult(success=True, output="No indexable documents found in the workspace.")
    by_ext: dict[str, int] = {}
    for path, _, _ in refs:
        by_ext[path.suffix.lower() or "?"] = by_ext.get(path.suffix.lower() or "?", 0) + 1
    df: dict[str, int] = {}
    for vec in vectors:
        for term in vec:
            df[term] = df.get(term, 0) + 1
    top = sorted(df.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
    lines = [
        f"Retrieval index: {len(refs)} chunks from {len({str(p) for p, _, _ in refs})} files.",
        "Chunks by type: " + ", ".join(f"{ext} {n}" for ext, n in sorted(by_ext.items(), key=lambda kv: -kv[1])),
        "Most frequent terms: " + ", ".join(t for t, _ in top),
    ]
    return ToolResult(success=True, output="\n".join(lines))
