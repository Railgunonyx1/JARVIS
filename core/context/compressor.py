"""Deterministic context compression (Headroom).

``/compact`` behaviour for the agent loop: when the message history exceeds
its budget, fold the oldest turns into a single summary message instead of
dropping them silently. Recent turns and the original goal stay verbatim so
the agent always knows the task. Tool results from old turns are the first
candidates for compression because they are bulk and rarely re-read.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from core.context.budget import estimate_messages_tokens
from core.context.summarizer import SummaryFn, default_summarizer


def compress(
    messages: List[Dict[str, Any]],
    budget_tokens: int,
    summarizer: SummaryFn = default_summarizer,
) -> List[Dict[str, Any]]:
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
    kept: List[Dict[str, Any]] = list(system_msgs) + goal_msgs + recent
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


def trim_tool_outputs(messages: List[Dict[str, Any]], max_content_chars: int = 2000) -> List[Dict[str, Any]]:
    """Truncate long tool-result contents in place (returns new list)."""
    out: List[Dict[str, Any]] = []
    for message in messages:
        if message.get("role") == "tool":
            content = message.get("content") or ""
            if len(content) > max_content_chars:
                message = {**message, "content": content[:max_content_chars] + "…"}
        out.append(message)
    return out
