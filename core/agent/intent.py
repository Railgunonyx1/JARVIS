"""Intent Classifier — fast-path rule engine that dispatches simple commands
without hitting the LLM. Eliminates an entire round-trip for common voice commands.

Architecture:
    User utterance → IntentClassifier.classify()
        → INSTANT (confidence=1.0): rule-matched, dispatch tool directly
        → SIMPLE  (confidence=0.8): likely simple, route to smallest model
        → COMPLEX (confidence=0.0): needs full LLM reasoning
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Intent(Enum):
    INSTANT = "instant"
    SIMPLE = "simple"
    COMPLEX = "complex"


@dataclass(frozen=True)
class ClassifiedIntent:
    intent: Intent
    confidence: float
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    response: str | None = None
    context_level: str = "instant"


# ── Rule definitions ─────────────────────────────────────────────────────

_COMMANDS: list[tuple[re.Pattern, str, dict[str, Any] | None, str | None]] = [
    # System queries — instant, no tool needed
    (
        re.compile(r"^(what time|what's the time|current time|time is it|tell me the time)",
                   re.IGNORECASE),
        "system.status", None, None,
    ),
    (
        re.compile(r"^(system status|how('s| is) (my |the )?(computer|pc|system|machine)|cpu|ram|memory usage)",
                   re.IGNORECASE),
        "system.status", None, None,
    ),
    # Git operations
    (
        re.compile(r"^(git status|show (me )?status|working tree status)",
                   re.IGNORECASE),
        "git.status", None, None,
    ),
    (
        re.compile(r"^(git diff|show (me )?(the )?diff|what('s| is) changed)",
                   re.IGNORECASE),
        "git.diff", None, None,
    ),
    (
        re.compile(r"^(git log|show (me )?(the )?(recent )?commits?|commit history)",
                   re.IGNORECASE),
        "git.log", None, None,
    ),
    (
        re.compile(r"^(git branch|what branch|current branch|which branch)",
                   re.IGNORECASE),
        "git.branch", None, None,
    ),
    # File operations — read
    (
        re.compile(r"^(read|show|open|cat|view) (?:the )?(?:file )?(.+)",
                   re.IGNORECASE),
        "filesystem.read", None, None,
    ),
    # Directory listing
    (
        re.compile(r"^(list|ls|dir|show) (?:the )?(?:files? in )?(.+)",
                   re.IGNORECASE),
        "filesystem.list", None, None,
    ),
    # Code search
    (
        re.compile(r"^(search|find|grep|look for|where is) (.+)",
                   re.IGNORECASE),
        "search.code", None, None,
    ),
    # Web search
    (
        re.compile(r"^(search (?:the )?web|google|look up|what is|who is|how (?:do|to)|tell me about) (.+)",
                   re.IGNORECASE),
        "web.search", None, None,
    ),
    # Browser
    (
        re.compile(r"^(open|go to|navigate to|browse) (https?://.+)",
                   re.IGNORECASE),
        "browser.open", None, None,
    ),
]


# ── Pattern-based tool arg extractors ────────────────────────────────────

def _extract_file_path(text: str) -> str | None:
    m = re.search(
        r"(?:read|show|open|cat|view|write|edit|file)\s+(?:the\s+)?(?:file\s+)?[`\"']?([^\s`\"']+)[`\"']?",
        text, re.IGNORECASE,
    )
    return m.group(1) if m else None


def _extract_search_pattern(text: str) -> str | None:
    m = re.search(
        r"(?:search|find|grep|look for|where is)\s+(?:for\s+)?(?:the\s+)?[`\"']?(.+?)[`\"']?\s*$",
        text, re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def _extract_web_query(text: str) -> str | None:
    m = re.search(
        r"(?:search (?:the )?web|google|look up|what is|who is|how (?:do|to)|tell me about)\s+(.+)",
        text, re.IGNORECASE,
    )
    return m.group(1).strip() if m else None


def _extract_url(text: str) -> str | None:
    m = re.search(r"(https?://[^\s]+)", text)
    return m.group(1) if m else None


def _extract_dir_path(text: str) -> str | None:
    m = re.search(
        r"(?:list|ls|dir|show)\s+(?:the\s+)?(?:files? in\s+)?[`\"']?([^\s`\"']+)[`\"']?",
        text, re.IGNORECASE,
    )
    return m.group(1) if m else None


# ── Classifier ───────────────────────────────────────────────────────────

class IntentClassifier:
    """Lightweight intent classifier that routes simple commands directly
    to tools without an LLM round-trip.

    Designed for <1ms classification latency. No model loading, no I/O.
    """

    def __init__(self, registry=None):
        self._registry = registry

    def classify(self, text: str) -> ClassifiedIntent:
        t = text.strip()
        if not t:
            return ClassifiedIntent(Intent.COMPLEX, 0.0)

        tl = t.lower()

        # ── Exact-match greetings / simple queries (response, no tool) ───
        _GREETINGS = {
            "hello": "Hello! How can I help you today?",
            "hi": "Hi there! What would you like me to work on?",
            "hey": "Hey! What are we building?",
            "yo": "Yo! What do you need?",
            "help": "I can help with coding, debugging, file operations, and more. Just describe what you need.",
            "who are you": "I am JARVIS MK-X, an autonomous engineering agent.",
            "thanks": "You're welcome!",
            "thank you": "You're welcome!",
            "bye": "Goodbye! Come back anytime.",
        }
        if tl in _GREETINGS:
            return ClassifiedIntent(
                Intent.INSTANT, 1.0,
                response=_GREETINGS[tl],
                context_level="instant",
            )

        # ── Pattern-matched tool dispatch ─────────────────────────────────
        for pattern, tool_name, fixed_args, fixed_response in _COMMANDS:
            m = pattern.match(tl)
            if m:
                args = dict(fixed_args) if fixed_args else {}
                # Extract dynamic args from capture groups
                if tool_name == "filesystem.read" and not args.get("path"):
                    path = _extract_file_path(t)
                    if path:
                        args["path"] = path
                elif tool_name == "search.code" and not args.get("pattern"):
                    pat = _extract_search_pattern(t)
                    if pat:
                        args["pattern"] = pat
                elif tool_name == "web.search" and not args.get("query"):
                    q = _extract_web_query(t)
                    if q:
                        args["query"] = q
                elif tool_name == "browser.open" and not args.get("url"):
                    url = _extract_url(t)
                    if url:
                        args["url"] = url
                elif tool_name == "filesystem.list" and not args.get("path"):
                    d = _extract_dir_path(t)
                    if d:
                        args["path"] = d

                # If tool registry is available, verify the tool exists
                if self._registry and self._registry.get(tool_name) is None:
                    continue

                return ClassifiedIntent(
                    Intent.INSTANT, 1.0,
                    tool_name=tool_name,
                    tool_args=args or None,
                    response=fixed_response,
                    context_level="instant",
                )

        # ── Heuristic: short, imperative → SIMPLE ─────────────────────────
        word_count = len(t.split())
        if word_count <= 6 and tl.startswith((
            "open", "run", "start", "stop", "create", "delete",
            "install", "build", "test", "deploy", "check", "show",
            "read", "write", "edit", "fix", "update", "add", "remove",
            "list", "find", "search", "git", "npm", "pip",
        )):
            return ClassifiedIntent(Intent.SIMPLE, 0.6, context_level="session")

        # ── Everything else → COMPLEX ─────────────────────────────────────
        return ClassifiedIntent(Intent.COMPLEX, 0.0, context_level="deep")
