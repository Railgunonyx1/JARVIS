"""Local cross-encoder reranking for memory retrieval.

Replaces the generative 1B LLM rerank lane (``memory/llm/rerank.py``) with a
local ONNX cross-encoder: one in-process forward pass, no network call, no
timeout, no JSON parsing, deterministic. ``onnxruntime`` is already shipped for
the Kokoro TTS lane (``jbrowser-bridge/voice.py``), so this adds a model file
rather than a new runtime.

Graceful degradation follows the ``memory/vector_store.py`` pattern: a missing
dependency, a missing model file or a failed forward pass disables the lane,
returns ``None``, and the caller falls back to the previous ordering.

Gate with ``JARVIS_RERANKER=off`` to hard-disable, or ``JARVIS_RERANKER_DIR``
to relocate the model.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import unicodedata
from collections import OrderedDict
from typing import Any

logger = logging.getLogger("jarvis.memory.cross_encoder")

MAX_SEQUENCE = 256
MAX_BATCH = 32
MAX_WORD_CHARS = 100
VOCAB_FILE = "vocab.txt"
MODEL_CANDIDATES = ("model_quantized.onnx", "model.onnx")
CACHE_MAX = 256

_lock = threading.Lock()
_state: dict[str, Any] = {"tried": False, "ok": False, "session": None, "vocab": None}


def _enabled() -> bool:
    flag = os.environ.get("JARVIS_RERANKER", "auto").strip().lower()
    return flag not in ("off", "0", "false", "no", "disabled")


def _model_dir() -> str:
    override = os.environ.get("JARVIS_RERANKER_DIR", "").strip()
    if override:
        return override
    base = os.environ.get("JARVIS_DATA_DIR", "").strip()
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".jarvis")
    return os.path.join(base, "reranker")


def _session_options():
    import onnxruntime as rt

    opts = rt.SessionOptions()
    opts.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
    opts.inter_op_num_threads = 1
    opts.execution_mode = rt.ExecutionMode.ORT_SEQUENTIAL
    opts.graph_optimization_level = rt.GraphOptimizationLevel.ORT_ENABLE_ALL
    return opts


def _load() -> bool:
    if not _enabled():
        return False
    if _state["tried"]:
        return bool(_state["ok"])
    _state["tried"] = True

    model_dir = _model_dir()
    model_path = next(
        (os.path.join(model_dir, name) for name in MODEL_CANDIDATES
         if os.path.exists(os.path.join(model_dir, name))),
        None,
    )
    vocab_path = os.path.join(model_dir, VOCAB_FILE)
    if model_path is None or not os.path.exists(vocab_path):
        logger.debug("cross-encoder unavailable: no model in %s", model_dir)
        return False

    try:
        import onnxruntime as rt

        vocab: dict[str, int] = {}
        with open(vocab_path, encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                vocab[line.rstrip("\n")] = index
        session = rt.InferenceSession(
            model_path,
            sess_options=_session_options(),
            providers=["CPUExecutionProvider"],
        )
    except Exception as exc:
        logger.warning("cross-encoder load failed (%s); falling back to default order", exc)
        return False

    _state["session"] = session
    _state["vocab"] = vocab
    _state["ok"] = True
    logger.info("cross-encoder rerank lane active (%s)", model_dir)
    return True


def available() -> bool:
    """Whether the local cross-encoder lane can be used this process."""
    return _load()


def _is_whitespace(char: str) -> bool:
    return char in (" ", "\t", "\n", "\r") or unicodedata.category(char) == "Zs"


def _is_control(char: str) -> bool:
    if char in ("\t", "\n", "\r"):
        return False
    return unicodedata.category(char).startswith("C")


def _is_punctuation(char: str) -> bool:
    code = ord(char)
    if (33 <= code <= 47) or (58 <= code <= 64) or (91 <= code <= 96) or (123 <= code <= 126):
        return True
    return unicodedata.category(char).startswith("P")


def _is_cjk(code: int) -> bool:
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0x20000 <= code <= 0x2A6DF
        or 0x2A700 <= code <= 0x2B73F
        or 0x2B740 <= code <= 0x2B81F
        or 0x2B820 <= code <= 0x2CEAF
        or 0xF900 <= code <= 0xFAFF
        or 0x2F800 <= code <= 0x2FA1F
    )


def _clean(text: str) -> str:
    out = []
    for char in text:
        code = ord(char)
        if code == 0 or code == 0xFFFD or _is_control(char):
            continue
        out.append(" " if _is_whitespace(char) else char)
    return "".join(out)


def _split_punctuation(text: str) -> list[str]:
    chunks = []
    start = 0
    for index, char in enumerate(text):
        if _is_punctuation(char):
            if start != index:
                chunks.append(text[start:index])
            chunks.append(char)
            start = index + 1
    if start != len(text):
        chunks.append(text[start:])
    return chunks


def _pad_cjk(text: str) -> str:
    out = []
    for char in text:
        if _is_cjk(ord(char)):
            out.append(" ")
            out.append(char)
            out.append(" ")
        else:
            out.append(char)
    return "".join(out)


def _basic_tokens(text: str) -> list[str]:
    spaced = _pad_cjk(_clean(text))
    words: list[str] = []
    for chunk in _split_punctuation(spaced):
        words.extend(chunk.split())
    return [word.lower() for word in words]


def _wordpiece(token: str, vocab: dict[str, int], unk: int) -> list[int]:
    if len(token) > MAX_WORD_CHARS:
        return [unk]
    pieces: list[int] = []
    start = 0
    while start < len(token):
        end = len(token)
        current = None
        while start < end:
            piece = token[start:end]
            if start > 0:
                piece = "##" + piece
            if piece in vocab:
                current = vocab[piece]
                break
            end -= 1
        if current is None:
            return [unk]
        pieces.append(current)
        start = end
    return pieces


def _segment(text: str, vocab: dict[str, int], unk: int, budget: int) -> list[int]:
    tokens: list[int] = []
    for word in _basic_tokens(text):
        if len(tokens) >= budget:
            break
        tokens.extend(_wordpiece(word, vocab, unk))
    return tokens[:budget]


def _build_pair(
    query: str,
    text: str,
    vocab: dict[str, int],
    max_length: int,
) -> tuple[list[int], list[int], list[int]]:
    """Cross-encoder input is one sequence: [CLS] query [SEP] text [SEP]."""
    cls = vocab["[CLS]"]
    sep = vocab["[SEP]"]
    pad = vocab.get("[PAD]", 0)
    unk = vocab.get("[UNK]", 100)

    budget = max(1, (max_length - 3) // 2)
    left = _segment(query, vocab, unk, budget)
    right = _segment(text, vocab, unk, max_length - 3 - len(left))

    ids = [cls] + left + [sep] + right + [sep]
    types = [0] * (len(left) + 2) + [1] * (len(right) + 1)
    mask = [1] * len(ids)
    filler = max_length - len(ids)
    if filler > 0:
        ids += [pad] * filler
        types += [0] * filler
        mask += [0] * filler
    return ids[:max_length], types[:max_length], mask[:max_length]


def _forward(pairs: list[tuple[str, str]], max_length: int) -> list[float] | None:
    if not _load() or not pairs:
        return None
    session = _state["session"]
    vocab = _state["vocab"]

    import numpy as np

    names = {spec.name for spec in session.get_inputs()}
    encoded = [_build_pair(query, text, vocab, max_length) for query, text in pairs]
    width = min(max(len(ids) for ids, _, _ in encoded), max_length)

    feed: dict[str, Any] = {
        "input_ids": np.array([ids[:width] for ids, _, _ in encoded], dtype=np.int64),
        "attention_mask": np.array([m[:width] for _, _, m in encoded], dtype=np.int64),
    }
    if "token_type_ids" in names:
        feed["token_type_ids"] = np.array([t[:width] for _, t, _ in encoded], dtype=np.int64)

    with _lock:
        output = session.run(None, feed)
    values = np.asarray(output[0], dtype=np.float32)
    if values.ndim == 1:
        values = values.reshape(len(pairs), -1)
    column = values[:, 0] if values.shape[1] == 1 else values[:, -1]
    return [float(v) for v in column]


_cache: OrderedDict[tuple[str, str], float] = OrderedDict()


def score(query: str, texts: list[str], max_length: int = MAX_SEQUENCE) -> list[float] | None:
    """Relevance score per text on a shared 0..1 scale, or None if unavailable."""
    if not _enabled() or not query.strip() or not texts:
        return None

    results: list[float | None] = [None] * len(texts)
    pending: list[tuple[str, str]] = []
    with _lock:
        for index, text in enumerate(texts):
            key = (query, text)
            if key in _cache:
                results[index] = _cache[key]
                continue
            pending.append((str(index), text))

    for start in range(0, len(pending), MAX_BATCH):
        chunk = pending[start : start + MAX_BATCH]
        raw = _forward([(query, text) for _, text in chunk], max_length)
        if raw is None:
            return None
        with _lock:
            for (index, text), value in zip(chunk, raw, strict=True):
                bounded = 1.0 / (1.0 + math.exp(-value))
                _cache[(query, text)] = bounded
                _cache.move_to_end((query, text))
                results[int(index)] = bounded
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)

    return [0.0 if value is None else value for value in results]


def rerank(
    query: str,
    memories: list[dict[str, Any]],
    max_results: int = 3,
) -> list[dict[str, Any]] | None:
    """Reorder memories by cross-encoder relevance, or None if unavailable."""
    if not available() or len(memories) <= 1:
        return None
    texts = [str(m.get("content", m.get("value", ""))) for m in memories]
    scores = score(query, texts)
    if scores is None:
        return None
    order = sorted(range(len(memories)), key=lambda i: scores[i], reverse=True)
    return [memories[i] for i in order[:max_results]]


def status() -> dict[str, Any]:
    """Diagnostic view of the lane, for CLI and health output."""
    active = available()
    return {
        "enabled": _enabled(),
        "active": active,
        "model_dir": _model_dir(),
        "backend": "onnx-cross-encoder" if active else "default-order",
        "cached": len(_cache),
    }
