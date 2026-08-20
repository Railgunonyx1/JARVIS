"""Model Registry — automatic model selection based on task type.

Detects the user's intent from their prompt and routes to the best
available model for that task. Supports both auto-routing and manual
switching via /model command.

Architecture:
    User prompt → detect_task_type() → select_model() → router.preferred_model
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("jarvis.model_registry")


class TaskType(str, Enum):
    """Detected task types for model routing."""
    CODING = "coding"
    RESEARCH = "research"
    WRITING = "writing"
    REASONING = "reasoning"
    QUICK = "quick"           # Simple greetings, questions
    HEAVY = "heavy"           # Complex multi-step tasks
    CONVERSATIONAL = "conversational"


@dataclass
class ModelProfile:
    """A model's capabilities and metadata."""
    name: str                  # Ollama model tag (e.g., "qwen2.5:3b")
    size_gb: float             # Disk size in GB
    strengths: list[TaskType]  # What this model is best at
    speed: str = "medium"      # "fast", "medium", "slow"
    tools: bool = True         # Supports tool calling
    thinking: bool = False     # Has thinking/reasoning mode
    description: str = ""      # Human-readable description


# ── Model catalog ──────────────────────────────────────────────────────

MODEL_CATALOG: list[ModelProfile] = [
    # === 3-4B models (fast, fit on GPU) ===
    ModelProfile(
        name="qwen2.5:3b", size_gb=1.9,
        strengths=[TaskType.CODING, TaskType.QUICK, TaskType.CONVERSATIONAL],
        speed="fast", tools=True,
        description="Best all-rounder for coding at 3B. Proven tool calling.",
    ),
    ModelProfile(
        name="qwen2.5-coder:3b", size_gb=1.9,
        strengths=[TaskType.CODING],
        speed="fast", tools=True,
        description="Code-specialized Qwen. Best for pure coding tasks.",
    ),
    ModelProfile(
        name="qwen3:4b", size_gb=2.5,
        strengths=[TaskType.REASONING, TaskType.CODING, TaskType.HEAVY],
        speed="medium", tools=True, thinking=True,
        description="Latest Qwen with thinking mode. Best reasoning at this size.",
    ),
    ModelProfile(
        name="gemma3:4b", size_gb=3.3,
        strengths=[TaskType.RESEARCH, TaskType.WRITING, TaskType.REASONING],
        speed="medium", tools=True,
        description="Google's mid-range. Strong at research and writing.",
    ),
    ModelProfile(
        name="phi4-mini:3.8b", size_gb=2.5,
        strengths=[TaskType.REASONING, TaskType.WRITING],
        speed="fast", tools=True,
        description="Microsoft's efficient model. Good reasoning, fast.",
    ),
    ModelProfile(
        name="llama3.2:3b", size_gb=2.0,
        strengths=[TaskType.CONVERSATIONAL, TaskType.QUICK],
        speed="fast", tools=True,
        description="Meta's balanced 3B. Good for general conversation.",
    ),
    ModelProfile(
        name="nemotron-mini:4b", size_gb=2.7,
        strengths=[TaskType.CODING, TaskType.REASONING],
        speed="medium", tools=True,
        description="NVIDIA's efficient model. Strong at coding.",
    ),

    # === 7B models (heavy tasks, CPU offload) ===
    ModelProfile(
        name="qwen2.5:7b", size_gb=4.7,
        strengths=[TaskType.HEAVY, TaskType.CODING, TaskType.REASONING, TaskType.RESEARCH],
        speed="slow", tools=True,
        description="Best 7B for coding and complex tasks. Use for heavy work.",
    ),

    # === 1B models (ultra-fast fallback) ===
    ModelProfile(
        name="qwen2.5:1.5b", size_gb=0.9,
        strengths=[TaskType.QUICK, TaskType.CONVERSATIONAL],
        speed="fast", tools=True,
        description="Ultra-fast. Simple tasks only.",
    ),
    ModelProfile(
        name="gemma3:1b", size_gb=0.8,
        strengths=[TaskType.QUICK],
        speed="fast", tools=True,
        description="Smallest model. Emergency fallback only.",
    ),
]

# Build lookup by model name
_MODEL_BY_NAME: dict[str, ModelProfile] = {m.name: m for m in MODEL_CATALOG}


# ── Task type detection ────────────────────────────────────────────────

# Keywords/patterns for each task type
_CODING_PATTERNS = [
    r"\b(code|coding|program|debug|fix\s+bug|refactor|implement|function|class|module)\b",
    r"\b(python|javascript|typescript|rust|go|java|c\+\+|html|css|sql)\b",
    r"\b(file|read|write|edit|create|delete|move|rename)\s+(the\s+)?(file|script|module)",
    r"\b(test|tests|unit\s+test|integration|pytest|unittest|jest)\b",
    r"\b(git|commit|branch|merge|pull|push|diff|stash)\b",
    r"\b(deploy|build|compile|run|execute|install)\b",
    r"\b(api|endpoint|route|middleware|handler|controller)\b",
    r"\b(bug|error|exception|traceback|stack\s+trace|crash)\b",
    r"\b(refactor|optimize|improve|clean\s+up|simplify)\b",
    r"\b(breaking\s+change|regression|compatibility)\b",
]

_RESEARCH_PATTERNS = [
    r"\b(research|investigate|explore|analyze|study|compare|evaluate)\b",
    r"\b(find|search|look\s+up|discover|what\s+are|what\s+is)\b",
    r"\b(github|repository|repo|package|library|framework)\b",
    r"\b(documentation|docs|readme|tutorial|example)\b",
    r"\b(best\s+practice|architecture|design\s+pattern|approach)\b",
    r"\b(pros?\s+and\s+cons?|trade.?off|alternative|option)\b",
]

_WRITING_PATTERNS = [
    r"\b(write|draft|compose|author|create\s+(a\s+)?(document|doc|readme|changelog|blog))\b",
    r"\b(documentation|docs|comment|explain|describe|summarize)\b",
    r"\b(email|letter|proposal|report|essay|article)\b",
    r"\b(markdown|rst|latex|text)\b",
    r"\b(translate|localize|adapt)\b",
]

_REASONING_PATTERNS = [
    r"\b(why|how\s+does|explain\s+why|reason|logic|prove)\b",
    r"\b(solve|solution|approach|strategy|plan)\b",
    r"\b(trade.?off|pros?\s+and\s+cons?|analysis|evaluate)\b",
    r"\b(design|architecture|system\s+design|blueprint)\b",
    r"\b(think|reasoning|chain.of.thought|step.by.step)\b",
]

_QUICK_PATTERNS = [
    r"^(hi|hello|hey|yo|sup|bye|quit|exit|thanks|thank you|good\s+(morning|night))$",
    r"^(help|what\s+can\s+you\s+do|who\s+are\s+you)$",
    r"^(what\s+is\s+my\s+name|whats?\s+my\s+name|my\s+name\s+is|i\s+am|call\s+me)$",
]


def detect_task_type(prompt: str) -> TaskType:
    """Detect the task type from a user prompt.

    Uses keyword/pattern matching with scoring. Returns the highest-scoring
    task type, defaulting to CONVERSATIONAL for ambiguous prompts.
    """
    lower = prompt.lower().strip()

    # Quick check for simple inputs
    for pattern in _QUICK_PATTERNS:
        if re.match(pattern, lower):
            return TaskType.QUICK

    scores: dict[TaskType, int] = {t: 0 for t in TaskType}

    for pattern in _CODING_PATTERNS:
        if re.search(pattern, lower):
            scores[TaskType.CODING] += 2

    for pattern in _RESEARCH_PATTERNS:
        if re.search(pattern, lower):
            scores[TaskType.RESEARCH] += 2

    for pattern in _WRITING_PATTERNS:
        if re.search(pattern, lower):
            scores[TaskType.WRITING] += 2

    for pattern in _REASONING_PATTERNS:
        if re.search(pattern, lower):
            scores[TaskType.REASONING] += 2

    # Length-based heuristics
    word_count = len(lower.split())
    if word_count > 50:
        scores[TaskType.HEAVY] += 3
    elif word_count > 20:
        scores[TaskType.HEAVY] += 1

    # Tool-call-indicating patterns boost coding
    if any(kw in lower for kw in ("run ", "execute ", "deploy ", "build ", "compile ")):
        scores[TaskType.CODING] += 1

    # Find the winner
    best_type = max(scores, key=lambda t: scores[t])
    if scores[best_type] == 0:
        return TaskType.CONVERSATIONAL
    return best_type


# ── Model selection ────────────────────────────────────────────────────

def select_model(
    task_type: TaskType,
    available_models: list[str] | None = None,
    exclude: str | None = None,
) -> ModelProfile | None:
    """Select the best model for a given task type.

    Args:
        task_type: The detected task type.
        available_models: List of installed Ollama model names. If None,
            uses the full catalog.
        exclude: Model name to exclude (e.g., the currently active one).

    Returns:
        The best ModelProfile, or None if no suitable model found.
    """
    candidates = MODEL_CATALOG

    if available_models is not None:
        available_set = set(available_models)
        candidates = [m for m in candidates if m.name in available_set]

    if exclude:
        candidates = [m for m in candidates if m.name != exclude]

    # Score each candidate
    scored: list[tuple[int, ModelProfile]] = []
    for model in candidates:
        score = 0
        # Direct strength match
        if task_type in model.strengths:
            score += 10
        # Adjacent strengths (e.g., CODING model can do HEAVY)
        if task_type == TaskType.HEAVY and TaskType.CODING in model.strengths:
            score += 5
        if task_type == TaskType.HEAVY and TaskType.REASONING in model.strengths:
            score += 5
        if task_type == TaskType.CODING and TaskType.HEAVY in model.strengths:
            score += 3
        # Speed bonus for quick tasks
        if task_type == TaskType.QUICK and model.speed == "fast":
            score += 5
        # Size bonus for heavy tasks (bigger = better)
        if task_type == TaskType.HEAVY:
            score += int(model.size_gb * 2)
        # Penalty for slow models on quick tasks
        if task_type == TaskType.QUICK and model.speed == "slow":
            score -= 5

        if score > 0:
            scored.append((score, model))

    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


class ModelRegistry:
    """Singleton model registry with state tracking."""

    _instance = None

    def __init__(self):
        self._active_model: str | None = None
        self._auto_mode: bool = True  # Auto-select by default
        self._task_history: list[TaskType] = []
        self._model_usage: dict[str, int] = {}  # model -> use count

    @classmethod
    def instance(cls) -> ModelRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def active_model(self) -> str | None:
        return self._active_model

    @property
    def auto_mode(self) -> bool:
        return self._auto_mode

    def set_model(self, model_name: str | None) -> str:
        """Manually set the model. Pass None to reset to auto mode.

        Returns a human-readable status message.
        """
        if model_name is None or model_name.lower() == "auto":
            self._auto_mode = True
            self._active_model = None
            return "Switched to auto mode — JARVIS will pick the best model per task."

        # Normalize: add :latest tag if missing
        if ":" not in model_name:
            model_name = model_name  # Keep as-is, Ollama resolves

        # Validate against catalog
        profile = _MODEL_BY_NAME.get(model_name)
        if profile is None:
            # Try partial match
            for name, p in _MODEL_BY_NAME.items():
                if model_name.lower() in name.lower():
                    profile = p
                    model_name = name
                    break

        if profile is None:
            available = ", ".join(sorted(_MODEL_BY_NAME.keys()))
            return f"Unknown model '{model_name}'. Available: {available}"

        self._auto_mode = False
        self._active_model = model_name
        return f"Locked to {model_name} — {profile.description}"

    def resolve_model(self, prompt: str, available_models: list[str] | None = None) -> str | None:
        """Resolve which model to use for a prompt.

        Returns the model name to pass to the router, or None to use the
        router's default.
        """
        if not self._auto_mode and self._active_model:
            self._model_usage[self._active_model] = self._model_usage.get(self._active_model, 0) + 1
            return self._active_model

        task_type = detect_task_type(prompt)
        self._task_history.append(task_type)
        if len(self._task_history) > 100:
            self._task_history = self._task_history[-50:]

        model = select_model(task_type, available_models, exclude=self._active_model)
        if model is not None:
            self._model_usage[model.name] = self._model_usage.get(model.name, 0) + 1
            logger.info("Auto-selected %s for %s task", model.name, task_type.value)
            return model.name

        return None

    def get_status(self) -> dict[str, Any]:
        """Return registry status for the /model command."""
        return {
            "active_model": self._active_model,
            "auto_mode": self._auto_mode,
            "task_counts": {
                t.value: self._task_history.count(t)
                for t in TaskType
            },
            "model_usage": dict(sorted(
                self._model_usage.items(), key=lambda x: x[1], reverse=True
            )),
        }

    def list_models(self) -> list[dict[str, Any]]:
        """Return all catalog models with their metadata."""
        return [
            {
                "name": m.name,
                "size_gb": m.size_gb,
                "strengths": [s.value for s in m.strengths],
                "speed": m.speed,
                "tools": m.tools,
                "thinking": m.thinking,
                "description": m.description,
            }
            for m in MODEL_CATALOG
        ]
