"""Intent Classifier — zero-LLM fast path + semantic tool selection.

Two core jobs:
  1. Route simple commands directly to tools without any LLM round-trip.
  2. For commands that DO need an LLM, select only the relevant tools to
     reduce prompt tokens, model confusion, and inference time.

Latency budget: <1ms for classification, <0.5ms for tool selection.
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
    suggested_tools: tuple[str, ...] = ()


_RESPONSES: dict[str, str] = {
    "hello": "Hello! How can I help you today?",
    "hi": "Hi there! What would you like me to work on?",
    "hey": "Hey! What are we building?",
    "yo": "Yo! What do you need?",
    "help": "I can help with coding, debugging, file operations, and more.",
    "who are you": "I am JARVIS MK-X, an autonomous engineering agent.",
    "thanks": "You're welcome!",
    "thank you": "You're welcome!",
    "bye": "Goodbye! Come back anytime.",
    "good morning": "Good morning! Ready to code?",
    "good night": "Good night! Sleep well.",
    "what can you do": (
        "I can read, write, edit files, run commands, search code, "
        "manage git, browse the web, and more."
    ),
    "stop": "Stopped.",
    "cancel": "Cancelled.",
    "never mind": "No problem!",
    "nevermind": "No problem!",
    "quit": "Goodbye!",
    "exit": "Goodbye!",
}

_MODE_COMMANDS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"^(turbo|speed|fast)\s*(mode)?$", re.IGNORECASE),
     "turbo", "Turbo mode: fastest model, minimal context."),
    (re.compile(r"^(quality|deep|slow)\s*(mode)?$", re.IGNORECASE),
     "quality", "Quality mode: strongest model, full context."),
    (re.compile(r"^(normal|default)\s*(mode)?$", re.IGNORECASE),
     "normal", "Normal mode restored."),
    (re.compile(r"^(compact|minimal)\s*(mode)?$", re.IGNORECASE),
     "compact", "Compact mode: minimal context, fast responses."),
    (re.compile(r"^(use|switch to|set)\s+(1\.?5b|1b|3b|4b|7b)\s*$", re.IGNORECASE),
     "model_switch", ""),
    (re.compile(r"^(optimize|enable) (latency|speed)$", re.IGNORECASE),
     "turbo", "Latency optimization enabled."),
    (re.compile(r"^(show|display) (performance|stats|metrics|latency)$", re.IGNORECASE),
     "show_perf", ""),
    (re.compile(r"^(preload|prewarm|warm ?up) (models?|ollama)$", re.IGNORECASE),
     "prewarm", "Warming up local models..."),
    (re.compile(r"^(clear|flush) (cache|memory|context)$", re.IGNORECASE),
     "clear_cache", "Cache cleared."),
    (re.compile(r"^(enable|disable) (predictive|speculative|escalat)", re.IGNORECASE),
     "toggle_feature", ""),
    (re.compile(r"^(enable|disable) (adaptive|routing|compression)", re.IGNORECASE),
     "toggle_feature", ""),
]

_COMMANDS: list[tuple[re.Pattern, str, dict[str, Any] | None]] = [
    (re.compile(r"^(what time|what('s| is) the time|current time|time is it|tell me the time|what('s| is) the date)",
                re.IGNORECASE), "system.status", None),
    (re.compile(r"^(system status|how('s| is) (my |the )?(computer|pc|system|machine)|cpu|ram|memory usage)$",
                re.IGNORECASE), "system.status", None),
    (re.compile(r"^(git status|show (me )?status|working tree status)$", re.IGNORECASE),
     "git.status", None),
    (re.compile(r"^(git diff|show (me )?(the )?diff|what('s| is) changed)$", re.IGNORECASE),
     "git.diff", None),
    (re.compile(r"^(git log|show (me )?(the )?(recent )?commits?|commit history)$", re.IGNORECASE),
     "git.log", None),
    (re.compile(r"^(git branch|what branch|current branch|which branch)$", re.IGNORECASE),
     "git.branch", None),
    (re.compile(r"^(read|show|open|cat|view) (?:the )?(?:file )?(.+)$", re.IGNORECASE),
     "filesystem.read", None),
    (re.compile(r"^(list|ls|dir|show) (?:the )?(?:files? in )?(.+)$", re.IGNORECASE),
     "filesystem.list", None),
    (re.compile(r"^(search|find|grep|look for|where is) (.+)$", re.IGNORECASE),
     "search.code", None),
    (re.compile(r"^(search (?:the )?web|google|look up|tell me about) (.+)$",
                re.IGNORECASE), "web.search", None),
    (re.compile(r"^(what is|who is|how (?:do|to))\s+(?!my\b|the\s+time|your\b)(.+)$",
                re.IGNORECASE), "web.search", None),
    (re.compile(r"^(open|go to|navigate to|browse) (https?://.+)$", re.IGNORECASE),
     "browser.open", None),
]

_TOOL_SELECTION: list[tuple[re.Pattern, tuple[str, ...]]] = [
    (re.compile(
        r"\b(edit|modify|change|update|rewrite|refactor|fix|patch)\b"
        r".*\b(file|function|class|method|code)\b", re.I),
     ("filesystem.read", "filesystem.write", "patch.replace", "search.code")),
    (re.compile(r"\b(create|write|make|add)\b.*\b(file|script|module|class)\b", re.I),
     ("filesystem.write", "filesystem.read", "filesystem.list")),
    (re.compile(r"\b(read|show|open|cat|view)\b.*\b(file|code|source)\b", re.I),
     ("filesystem.read", "filesystem.list")),
    (re.compile(r"\b(delete|remove|drop)\b.*\b(file|line|code)\b", re.I),
     ("filesystem.read", "patch.delete")),
    (re.compile(r"\b(commit|stage|branch|merge|rebase|push|pull|checkout)\b", re.I),
     ("git.status", "git.diff", "git.log", "git.branch", "git.add", "git.commit")),
    (re.compile(r"\b(git)\b", re.I),
     ("git.status", "git.diff", "git.log", "git.branch")),
    (re.compile(r"\b(search|find|grep|where|locate|look for)\b", re.I),
     ("search.code", "search.find")),
    (re.compile(r"\b(search|find)\b.*\b(web|internet|online|google)\b", re.I),
     ("web.search",)),
    (re.compile(r"\b(run|execute|build|test|deploy|install|start|stop)\b", re.I),
     ("shell.execute", "system.status")),
    (re.compile(r"\b(status|health|cpu|ram|memory|disk|uptime)\b", re.I),
     ("system.status",)),
    (re.compile(r"\b(browse|open url|website|page|scrape|screenshot)\b", re.I),
     ("browser.open", "browser.extract", "browser.screenshot")),
    # Memory tools — always include when memory-related intent detected
    (re.compile(r"\b(remember|recall|retrieve|memory|memorize|forget|forget about)\b", re.I),
     ("memory.retrieve", "memory.remember", "memory.forget")),
    (re.compile(r"\b(what|who|how|when|where)\s+(do you|does|is|are|was|were)\s+(know|remember)\b", re.I),
     ("memory.retrieve",)),
    (re.compile(r"\b(remember|store|save)\s+(that|this|my|your|our)\b", re.I),
     ("memory.remember",)),
    (re.compile(r"\b(decision|decided|chose|agreed|plan|strategy)\b", re.I),
     ("memory.retrieve",)),
]


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


def _extract_model_name(text: str) -> str | None:
    m = re.search(r"(1\.?5b|1b|3b|4b|7b)", text, re.IGNORECASE)
    return m.group(1).lower().replace(".", "") if m else None


class IntentClassifier:
    """Two-job classifier:
      1. Route simple commands to tools with zero LLM calls.
      2. For LLM-bound requests, select only relevant tools.
    """

    def __init__(self, registry=None):
        self._registry = registry

    def classify(self, text: str) -> ClassifiedIntent:
        t = text.strip()
        if not t:
            return ClassifiedIntent(Intent.COMPLEX, 0.0)

        tl = t.lower()

        if tl in _RESPONSES:
            return ClassifiedIntent(
                Intent.INSTANT, 1.0,
                response=_RESPONSES[tl],
                context_level="instant",
            )

        for pattern, cmd_type, response in _MODE_COMMANDS:
            m = pattern.match(tl)
            if m:
                if cmd_type == "model_switch":
                    model = _extract_model_name(t)
                    resp = f"Switching to {model}..." if model else "Which model?"
                    return ClassifiedIntent(
                        Intent.INSTANT, 1.0, response=resp, context_level="instant"
                    )
                if cmd_type in ("show_perf", "prewarm", "clear_cache", "toggle_feature"):
                    sym = f"__{cmd_type.upper()}__"
                    return ClassifiedIntent(
                        Intent.INSTANT, 1.0, response=sym, context_level="instant"
                    )
                return ClassifiedIntent(
                    Intent.INSTANT, 1.0, response=response, context_level="instant"
                )

        # Identity/memory questions — route to LLM where memory is in the system prompt.
        # These MUST come BEFORE _COMMANDS to avoid matching 'what is' → web.search.
        _IDENTITY_RE = re.compile(
            r"^(what(s|'?s|\s+is|\s+are|\s+s)\s+(my|the|your|\w+)'?s?\s+(name|role|project|preference|preferences|priorities?)"
            r"|what\s+is\s+(my|your)\s+"
            r"|who\s+(am\s+I|are\s+you|is\s+this)"
            r"|my\s+name\s+(is|was)\s+"
            r"|i('m|\s+am)\s+"
            r"|call\s+me\s+"
            r"|remember\s+(my\s+name\s+is|that)\s+"
            r"|do\s+you\s+know\s+(who\s+)?(I|my))",
            re.IGNORECASE,
        )
        if _IDENTITY_RE.match(tl):
            return ClassifiedIntent(Intent.SIMPLE, 0.9, context_level="session")

        for pattern, tool_name, fixed_args in _COMMANDS:
            m = pattern.match(tl)
            if m:
                args = dict(fixed_args) if fixed_args else {}
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

                if self._registry and self._registry.get(tool_name) is None:
                    continue

                return ClassifiedIntent(
                    Intent.INSTANT, 1.0,
                    tool_name=tool_name,
                    tool_args=args or None,
                    response=None,
                    context_level="instant",
                )

        word_count = len(t.split())
        if word_count <= 6 and tl.startswith((
            "open", "run", "start", "stop", "create", "delete",
            "install", "build", "test", "deploy", "check", "show",
            "read", "write", "edit", "fix", "update", "add", "remove",
            "list", "find", "search", "git", "npm", "pip",
        )):
            return ClassifiedIntent(Intent.SIMPLE, 0.6, context_level="session")

        return ClassifiedIntent(Intent.COMPLEX, 0.0, context_level="deep")

    def select_tools(self, text: str, all_tools: list[dict]) -> list[dict]:
        tl = text.lower()
        selected_names: set[str] = set()
        for pattern, tool_names in _TOOL_SELECTION:
            if pattern.search(tl):
                selected_names.update(tool_names)
        if not selected_names:
            return all_tools
        tool_map = {t.get("function", {}).get("name", ""): t for t in all_tools}
        result = [tool_map[n] for n in selected_names if n in tool_map]
        if not result:
            return all_tools
        return result
