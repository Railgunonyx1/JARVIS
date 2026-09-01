"""Two-stage context compression (Headroom).

Stage 1 — cheap heuristic score (<0.01 ms per message):
  Keyword matching, role, length, goal overlap. Classifies messages as
  CLEAR_KEEP (score ≥ 0.6), CLEAR_DISCARD (score ≤ 0.2), or AMBIGUOUS.

Stage 2 — tiny feature-based classifier for AMBIGUOUS messages only (<0.1 ms):
  Information density, specificity (file paths, function names, code),
  structural complexity, instruction patterns. Produces a refined score.

The two-stage design preserves the latency advantage of heuristics while
making compression considerably safer for edge cases.
"""

from __future__ import annotations

import re
from typing import Any

from core.context.budget import estimate_messages_tokens
from core.context.summarizer import SummaryFn, default_summarizer

# ── Stage 1: Keyword patterns ────────────────────────────────────────────

_KEYWORDS_HIGH = re.compile(
    r"\b(important|critical|bug|error|fix|security|password|secret|key|token|"
    r"name|remember|always|never|constraint|requirement|must|deadline|"
    r"todo|hack|workaround|deprecated|breaking|urgent|blocker|regression)\b",
    re.IGNORECASE,
)
_KEYWORDS_MED = re.compile(
    r"\b(should|prefer|design|architecture|pattern|approach|decision|"
    r"trade.?off|because|therefore|so that|ensure|verify|confirm|"
    r"note|warning|caution|warning|careful)\b",
    re.IGNORECASE,
)
_KEYWORDS_LOW = re.compile(
    r"\b(hello|hi|hey|thanks|ok|sure|yes|no|bye|cool|nice|great|"
    r"lol|haha|wow|oh|um|hmm|ah)\b",
    re.IGNORECASE,
)

# ── Stage 2: Feature patterns for ambiguous messages ─────────────────────

_CODE_PATH = re.compile(r"[/\\]|[a-zA-Z]:\\|\.\w{1,4}$|__\w+__")
_FUNC_NAME = re.compile(r"\b[a-z_]+\(|[A-Z][a-zA-Z]+\.|def |class |import ")
_FILE_REF = re.compile(r"\b\w+\.(py|js|ts|rs|go|java|c|cpp|h|yaml|toml|json|md)\b")
_NUMBERS = re.compile(r"\b\d+(\.\d+)?\b")
_STRUCTURE = re.compile(r"[{}\[\]()]|=>|->|::|\.\.\.")
_INSTRUCTION = re.compile(
    r"\b(please|make sure|do not|don't|never|always|must|shall|"
    r"need to|have to|should|required|mandatory|optional)\b",
    re.IGNORECASE,
)


def _information_density(text: str) -> float:
    """Ratio of content-carrying words to total words. Higher = more info."""
    words = text.split()
    if not words:
        return 0.0
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                  "being", "have", "has", "had", "do", "does", "did", "will",
                  "would", "could", "should", "may", "might", "shall", "can",
                  "it", "its", "this", "that", "these", "those", "i", "you",
                  "he", "she", "we", "they", "me", "him", "her", "us", "them",
                  "my", "your", "his", "our", "their", "to", "of", "in", "for",
                  "on", "with", "at", "by", "from", "as", "into", "about"}
    content_words = [w for w in words if w.lower().strip(".,!?;:") not in stop_words]
    return len(content_words) / len(words)


def _specificity_score(text: str) -> float:
    """Score based on concrete references (paths, functions, code). Higher = more specific."""
    score = 0.0
    if _CODE_PATH.search(text):
        score += 0.25
    if _FUNC_NAME.search(text):
        score += 0.3
    if _FILE_REF.search(text):
        score += 0.3
    if _NUMBERS.search(text):
        score += 0.1
    if _STRUCTURE.search(text):
        score += 0.2
    return min(1.0, score)


def _classifier_score(msg: dict[str, Any], goal: str = "") -> float:
    """Tiny feature-based classifier for ambiguous messages. Returns 0.0-1.0."""
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

    # Role signal
    if role == "system":
        score += 0.2
    elif role == "user":
        score += 0.1
    elif role == "tool":
        # Tool results: short = probably unimportant, long = probably useful
        if len(text) > 300:
            score += 0.15
        elif len(text) < 30:
            score -= 0.1

    # Information density
    density = _information_density(text)
    score += density * 0.2  # max +0.2

    # Specificity — concrete references are almost always worth keeping
    spec = _specificity_score(text)
    score += spec * 0.3  # max +0.3

    # Instruction patterns
    if _INSTRUCTION.search(text):
        score += 0.15

    # Length signal (refined from stage 1)
    if len(text) < 5:
        score -= 0.2
    elif 5 <= len(text) < 20:
        score -= 0.05
    elif len(text) > 500:
        score += 0.1

    # Goal overlap (same as stage 1 but finer-grained)
    if goal:
        goal_words = set(goal.lower().split())
        msg_words = set(text.lower().split())
        overlap = len(goal_words & msg_words) / max(len(goal_words), 1)
        score += overlap * 0.25

    # Code-like content is almost always relevant
    code_indicators = sum(1 for pat in [_CODE_PATH, _FUNC_NAME, _FILE_REF, _STRUCTURE]
                          if pat.search(text))
    if code_indicators >= 2:
        score += 0.2
    elif code_indicators == 1:
        score += 0.1

    return max(0.0, min(1.0, score))


# ── Stage 1: Heuristic scorer ────────────────────────────────────────────

_AMBIGUOUS_LOW = 0.2   # below this = CLEAR_DISCARD
_AMBIGUOUS_HIGH = 0.6   # above this = CLEAR_KEEP


def _heuristic_score(msg: dict[str, Any], goal: str = "") -> tuple[float, str]:
    """Stage 1 heuristic. Returns (score, classification)."""
    role = msg.get("role", "")
    content = msg.get("content") or ""
    if isinstance(content, list):
        content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not isinstance(content, str):
        content = str(content)
    text = content.strip()
    if not text:
        return 0.0, "discard"

    score = 0.3  # base

    if role == "system":
        score += 0.3
    elif role == "user":
        score += 0.1
    elif role == "tool":
        score += 0.05

    if _KEYWORDS_HIGH.search(text):
        score += 0.3
    if _KEYWORDS_MED.search(text):
        score += 0.15
    if _KEYWORDS_LOW.search(text):
        score -= 0.15

    if len(text) < 10:
        score -= 0.1
    elif len(text) > 200:
        score += 0.1

    if goal:
        goal_words = set(goal.lower().split())
        msg_words = set(text.lower().split())
        overlap = len(goal_words & msg_words) / max(len(goal_words), 1)
        score += overlap * 0.2

    score = max(0.0, min(1.0, score))

    if score >= _AMBIGUOUS_HIGH:
        return score, "keep"
    elif score <= _AMBIGUOUS_LOW:
        return score, "discard"
    else:
        return score, "ambiguous"


# ── Public API ───────────────────────────────────────────────────────────

def score_message(msg: dict[str, Any], goal: str = "") -> float:
    """Two-stage relevance score. Stage 1 for clear cases, stage 2 for ambiguous."""
    h_score, classification = _heuristic_score(msg, goal)
    if classification == "ambiguous":
        return _classifier_score(msg, goal)
    return h_score


def adaptive_compress(
    messages: list[dict[str, Any]],
    budget_tokens: int,
    goal: str = "",
    summarizer: SummaryFn = default_summarizer,
    relevance_threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """Two-stage relevance-aware compression.

    Stage 1 (heuristic) classifies each message as keep/discard/ambiguous.
    Stage 2 (feature classifier) refines ambiguous messages only.
    High-relevance messages kept verbatim. Low-relevance folded into summary.

    Returns a new list; the input is never mutated.
    """
    if estimate_messages_tokens(messages) <= budget_tokens:
        return list(messages)

    system_msgs = [m for m in messages if m.get("role") == "system"]
    others = [m for m in messages if m.get("role") != "system"]

    goal_idx = next((i for i, m in enumerate(others) if m.get("role") == "user"), None)
    goal_msg = others[goal_idx] if goal_idx is not None else None

    last_user = max(
        (i for i, m in enumerate(others) if m.get("role") == "user"), default=-1,
    )
    recent = others[last_user:] if last_user >= 0 else []

    foldable = others[goal_idx + 1:last_user] if goal_msg is not None else others[:last_user]

    # Two-stage scoring
    scored = [(score_message(m, goal), i, m) for i, m in enumerate(foldable)]
    scored.sort(key=lambda x: x[0], reverse=True)

    keepers = []
    foldable_low = []
    for s, _orig_i, m in scored:
        if s >= relevance_threshold:
            keepers.append(m)
        else:
            foldable_low.append(m)

    kept = list(system_msgs)
    if goal_msg:
        kept.append(goal_msg)
    kept.extend(keepers)
    kept.extend(recent)

    for _ in range(4):
        if estimate_messages_tokens(kept) <= budget_tokens:
            break
        candidate_idx = next(
            (i for i, m in enumerate(kept) if m.get("role") == "tool" and i > 0),
            None,
        )
        if candidate_idx is None:
            break
        kept = _pair_aware_remove(kept, candidate_idx)

    if foldable_low and estimate_messages_tokens(kept) > budget_tokens:
        summary = {"role": "system", "content": f"[Earlier context]: {summarizer(foldable_low)}"}
        kept = list(system_msgs) + [summary]
        if goal_msg:
            kept.append(goal_msg)
        kept.extend(keepers)
        kept.extend(recent)

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
            kept = _pair_aware_remove(kept, idx)

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
    #    Tool-call pairs (assistant + tool results) are removed atomically
    #    to maintain structurally valid conversation history.
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
        kept = _pair_aware_remove(kept, candidate_idx)

    # 5. If still over, fold foldable turns into a summary message.
    if foldable and estimate_messages_tokens(kept) > budget_tokens:
        summary = {"role": "system", "content": f"[Earlier context]: {summarizer(foldable)}"}
        kept = system_msgs + [summary] + goal_msgs + recent
        # Last resort: trim tool outputs one by one (pair-aware).
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
                kept = _pair_aware_remove(kept, idx)

    return kept


def _find_tool_call_ids(assistant_msg: dict[str, Any]) -> set[str]:
    """Extract tool_call IDs from an assistant message."""
    tool_calls = assistant_msg.get("tool_calls") or []
    ids = set()
    for tc in tool_calls:
        if isinstance(tc, dict):
            tc_id = tc.get("id")
            if tc_id:
                ids.add(tc_id)
    return ids


def _pair_aware_remove(messages: list[dict[str, Any]], target_idx: int) -> list[dict[str, Any]]:
    """Remove a tool message and its parent assistant message if orphaned.

    When removing a tool result, check if the preceding assistant message
    has tool_calls. If so, remove the assistant message too to avoid
    structurally invalid conversation history.
    """
    target = messages[target_idx]
    if target.get("role") != "tool":
        return messages[:target_idx] + messages[target_idx + 1:]

    # Scan backwards to find the parent assistant message
    parent_idx = None
    for i in range(target_idx - 1, -1, -1):
        if messages[i].get("role") == "assistant" and messages[i].get("tool_calls"):
            parent_idx = i
            break

    if parent_idx is None:
        # No parent found — just remove the tool message
        return messages[:target_idx] + messages[target_idx + 1:]

    # Check if the parent has OTHER tool results still present
    parent_ids = _find_tool_call_ids(messages[parent_idx])
    remaining_tool_ids = set()
    for i, m in enumerate(messages):
        if i == target_idx:
            continue
        if m.get("role") == "tool":
            tc_id = m.get("tool_call_id") or m.get("name")
            if tc_id and tc_id in parent_ids:
                remaining_tool_ids.add(tc_id)

    # If parent still has other tool results, only remove the target tool
    if remaining_tool_ids:
        return messages[:target_idx] + messages[target_idx + 1:]

    # Parent has no remaining tool results — remove both parent and target
    return messages[:parent_idx] + messages[parent_idx + 1:target_idx] + messages[target_idx + 1:]


def trim_tool_outputs(messages: list[dict[str, Any]], max_content_chars: int = 800) -> list[dict[str, Any]]:
    """Truncate long tool-result contents (returns new list).

    Tool-call pairs (assistant with tool_calls + tool results) are treated
    as atomic units to maintain structurally valid conversation history.
    """
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "tool":
            content = msg.get("content") or ""
            if len(content) > max_content_chars:
                msg = {**msg, "content": content[:max_content_chars] + "…"}
        out.append(msg)
    return out
