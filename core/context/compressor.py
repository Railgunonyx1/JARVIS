"""Deterministic context compression (Headroom).

``/compact`` behaviour for the agent loop: when the message history exceeds
its budget, fold the oldest turns into a single summary message instead of
dropping them silently. Recent turns and the original goal stay verbatim so
the agent always knows the task. Tool results from old turns are the first
candidates for compression because they are bulk and rarely re-read.
"""

from __future__ import annotations

import re
from typing import Any

from core.context.budget import estimate_messages_tokens
from core.context.summarizer import SummaryFn, default_summarizer

# ── Relevance scoring ────────────────────────────────────────────────────

_KEYWORDS_HIGH = re.compile(
    r"\b(important|critical|bug|error|fix|security|password|secret|key|token|"
    r"name|remember|always|never|constraint|requirement|must|deadline)\b",
    re.IGNORECASE,
)
_KEYWORDS_MED = re.compile(
    r"\b(should|prefer|design|architecture|pattern|approach|decision|"
    r"trade.?off|because|therefore|so that)\b",
    re.IGNORECASE,
)
_KEYWORDS_LOW = re.compile(
    r"\b(hello|hi|hey|thanks|ok|sure|yes|no|bye)\b",
    re.IGNORECASE,
)


def _score_message(msg: dict[str, Any], goal: str = "") -> float:
    """Score a message's relevance from 0.0 (noise) to 1.0 (critical)."""
    role = msg.get("role", "")
    content = msg.get("content") or ""
    if isinstance(content, list):
        content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not isinstance(content, str):
        content = str(content)
    text = content.strip()
    if not text:
        return 0.0

    score = 0.3  # base

    # Role-based adjustments
    if role == "system":
        score += 0.3
    elif role == "user":
        score += 0.1
    elif role == "tool":
        score += 0.05

    # Keyword matching
    if _KEYWORDS_HIGH.search(text):
        score += 0.3
    if _KEYWORDS_MED.search(text):
        score += 0.15
    if _KEYWORDS_LOW.search(text):
        score -= 0.15

    # Length — very short messages are usually noise
    if len(text) < 10:
        score -= 0.1
    elif len(text) > 200:
        score += 0.1

    # Goal relevance — if the message mentions words from the goal
    if goal:
        goal_words = set(goal.lower().split())
        msg_words = set(text.lower().split())
        overlap = len(goal_words & msg_words) / max(len(goal_words), 1)
        score += overlap * 0.2

    return max(0.0, min(1.0, score))


def adaptive_compress(
    messages: list[dict[str, Any]],
    budget_tokens: int,
    goal: str = "",
    summarizer: SummaryFn = default_summarizer,
    relevance_threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """Relevance-aware compression: scores each message and keeps the most
    important ones while folding low-relevance turns into a summary.

    Returns a new list; the input is never mutated.
    """
    if estimate_messages_tokens(messages) <= budget_tokens:
        return list(messages)

    system_msgs = [m for m in messages if m.get("role") == "system"]
    others = [m for m in messages if m.get("role") != "system"]

    # Always keep: first user turn (goal) and last user turn (current instruction)
    goal_idx = next((i for i, m in enumerate(others) if m.get("role") == "user"), None)
    goal_msg = others[goal_idx] if goal_idx is not None else None

    last_user = max(
        (i for i, m in enumerate(others) if m.get("role") == "user"), default=-1,
    )
    recent = others[last_user:] if last_user >= 0 else []

    # Score everything between goal and last user turn
    foldable = others[goal_idx + 1:last_user] if goal_msg is not None else others[:last_user]
    scored = [(_score_message(m, goal), i, m) for i, m in enumerate(foldable)]
    scored.sort(key=lambda x: x[0], reverse=True)

    # Split into keepers (high relevance) and foldable (low relevance)
    keepers = []
    foldable_low = []
    for score, _orig_i, m in scored:
        if score >= relevance_threshold:
            keepers.append(m)
        else:
            foldable_low.append(m)

    # Reconstruct: system + goal + high-relevance kept + recent
    kept = list(system_msgs)
    if goal_msg:
        kept.append(goal_msg)
    kept.extend(keepers)
    kept.extend(recent)

    # Trim tool outputs if still over budget
    for _ in range(4):
        if estimate_messages_tokens(kept) <= budget_tokens:
            break
        candidate_idx = next(
            (i for i, m in enumerate(kept) if m.get("role") == "tool" and i > 0),
            None,
        )
        if candidate_idx is None:
            break
        kept.pop(candidate_idx)

    # Fold low-relevance turns into summary if still over
    if foldable_low and estimate_messages_tokens(kept) > budget_tokens:
        summary = {"role": "system", "content": f"[Earlier context]: {summarizer(foldable_low)}"}
        kept = list(system_msgs) + [summary]
        if goal_msg:
            kept.append(goal_msg)
        kept.extend(keepers)
        kept.extend(recent)

    # Last resort: truncate tool outputs
    for _ in range(8):
        if estimate_messages_tokens(kept) <= budget_tokens:
            break
        idx = next(
            (i for i, m in enumerate(kept) if m.get("role") == "tool"), None,
        )
        if idx is None:
            break
        content = kept[idx].get("content") or ""
        if len(content) > 80:
            kept[idx] = {**kept[idx], "content": content[:80] + "…"}
        else:
            kept.pop(idx)

    return kept


def compress(
    messages: list[dict[str, Any]],
    budget_tokens: int,
    summarizer: SummaryFn = default_summarizer,
) -> list[dict[str, Any]]:
    """Shrink a message list so it fits ``budget_tokens``.

    Strategy:
      1. Always keep the system messages and the first user turn (the goal).
      2. Keep tool-result turns only if they are recent (later than the
         newest user request).
      3. If still over budget, fold the oldest compressible turns into one
         system-level summary message.

    Returns a new list; the input is never mutated.
    """
    if estimate_messages_tokens(messages) <= budget_tokens:
        return list(messages)

    system_msgs = [m for m in messages if m.get("role") == "system"]
    others = [m for m in messages if m.get("role") != "system"]

    # 1. First user turn is the goal — never fold it.
    goal_idx = next((i for i, m in enumerate(others) if m.get("role") == "user"), None)
    goal = others[goal_idx] if goal_idx is not None else None
    goal_msgs = [goal] if goal else []

    # 2. Keep the last user turn (current instruction) and everything after
    #    it verbatim.
    last_user = max(
        (i for i, m in enumerate(others) if m.get("role") == "user"), default=-1,
    )
    recent = others[last_user:] if last_user >= 0 else []

    # 3. Everything between the goal and the last user turn is foldable.
    foldable = others[goal_idx + 1:last_user] if goal is not None else others[:last_user]

    # 4. Tool results in the kept window are the first candidates for trimming.
    kept: list[dict[str, Any]] = list(system_msgs) + goal_msgs + recent
    for _ in range(4):  # bounded retries, deterministic
        if estimate_messages_tokens(kept) <= budget_tokens:
            break
        candidate_idx = next(
            (i for i, m in enumerate(kept) if m.get("role") == "tool" and i > 0),
            None,
        )
        if candidate_idx is None:
            break
        kept.pop(candidate_idx)

    # 5. If still over, fold foldable turns into a summary message.
    if foldable and estimate_messages_tokens(kept) > budget_tokens:
        summary = {"role": "system", "content": f"[Earlier context]: {summarizer(foldable)}"}
        kept = system_msgs + [summary] + goal_msgs + recent
        # Last resort: trim tool outputs one by one.
        for _ in range(8):
            if estimate_messages_tokens(kept) <= budget_tokens:
                break
            idx = next(
                (i for i, m in enumerate(kept) if m.get("role") == "tool"), None,
            )
            if idx is None:
                break
            content = kept[idx].get("content") or ""
            if len(content) > 80:
                kept[idx] = {**kept[idx], "content": content[:80] + "…"}
            else:
                kept.pop(idx)

    return kept


def trim_tool_outputs(messages: list[dict[str, Any]], max_content_chars: int = 800) -> list[dict[str, Any]]:
    """Truncate long tool-result contents in place (returns new list)."""
    out: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "tool":
            content = message.get("content") or ""
            if len(content) > max_content_chars:
                message = {**message, "content": content[:max_content_chars] + "…"}
        out.append(message)
    return out
