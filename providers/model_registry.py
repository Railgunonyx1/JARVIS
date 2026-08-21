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


# Commands that NEVER need an LLM — handled deterministically by the CLI.
_DETERMINISTIC_COMMANDS = frozenset({
    "/help", "/exit", "/quit", "/clear", "/cockpit", "/notifications",
    "/verbose", "/plan", "/tokens", "/compact", "/tree", "/resume",
    "/memory", "/history", "/model", "/palette", "/perf", "/audit",
})


def _is_deterministic_command(prompt: str) -> bool:
    """Check if a prompt is a deterministic command that bypasses the LLM."""
    lower = prompt.strip().lower()
    # /commands are always deterministic
    if lower.startswith("/"):
        cmd = lower.split()[0]
        return cmd in _DETERMINISTIC_COMMANDS
    return False


def detect_task_type(prompt: str) -> TaskType:
    """Detect the task type from a user prompt.

    Uses keyword/pattern matching with scoring. Returns the highest-scoring
    task type, defaulting to CONVERSATIONAL for ambiguous prompts.
    """
    task_type, _confidence = detect_task_type_with_confidence(prompt)
    return task_type


def detect_task_type_with_confidence(prompt: str) -> tuple[TaskType, float]:
    """Detect the task type AND confidence (0.0–1.0) from a user prompt.

    Confidence is derived from:
    - Score gap between best and second-best type
    - Number of pattern matches (more matches = more certain)
    - Input length (very short = harder to classify)

    Returns:
        (TaskType, confidence) where confidence is 0.0–1.0.
    """
    lower = prompt.lower().strip()

    # Quick check for simple inputs — very high confidence
    for pattern in _QUICK_PATTERNS:
        if re.match(pattern, lower):
            return TaskType.QUICK, 0.95

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
    best_score = scores[best_type]

    if best_score == 0:
        return TaskType.CONVERSATIONAL, 0.3

    # Compute confidence from score gap and total matches
    sorted_scores = sorted(scores.values(), reverse=True)
    second_best = sorted_scores[1] if len(sorted_scores) > 1 else 0
    gap = best_score - second_best
    total_matches = best_score // 2  # each pattern gives +2

    # Confidence formula:
    #   - gap contributes 0–0.5 (big gap = more certain)
    #   - match count contributes 0–0.3 (more patterns = more certain)
    #   - base confidence 0.2
    gap_confidence = min(0.5, gap * 0.1)
    match_confidence = min(0.3, total_matches * 0.1)
    confidence = 0.2 + gap_confidence + match_confidence

    return best_type, min(0.95, confidence)


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


@dataclass
class _TierPerf:
    """Per-model-tier performance tracking for adaptive routing."""
    name: str
    requests: int = 0
    successes: int = 0
    failures: int = 0
    total_ms: float = 0.0
    ttft_sum_ms: float = 0.0      # time-to-first-token sum
    ttft_count: int = 0

    @property
    def success_rate(self) -> float:
        if self.requests == 0:
            return 1.0  # Assume success until we have data
        return self.successes / self.requests

    @property
    def avg_ttft_ms(self) -> float:
        if self.ttft_count == 0:
            return 0.0
        return self.ttft_sum_ms / self.ttft_count

    @property
    def avg_ms(self) -> float:
        if self.requests == 0:
            return 0.0
        return self.total_ms / self.requests

    def record(self, success: bool, latency_ms: float, ttft_ms: float = 0.0) -> None:
        self.requests += 1
        if success:
            self.successes += 1
        else:
            self.failures += 1
        self.total_ms += latency_ms
        if ttft_ms > 0:
            self.ttft_sum_ms += ttft_ms
            self.ttft_count += 1

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "requests": self.requests,
            "success_rate": round(self.success_rate, 3),
            "avg_ttft_ms": round(self.avg_ttft_ms, 1),
            "avg_ms": round(self.avg_ms, 1),
        }


class ModelRegistry:
    """Singleton model registry with state tracking and cascade routing.

    Three-tier cascade:
      Tier 1 (router):  qwen2.5:1.5b — ultra-fast, handles greetings/simple tasks
      Tier 2 (worker):  qwen2.5:3b  — fast, handles coding/tools/reasoning
      Tier 3 (heavy):   qwen3:4b    — smart, handles complex multi-step tasks
    """

    _instance = None

    # Default cascade configuration
    CASCADE_ROUTER = "qwen2.5:1.5b"  # Tier 1: always first, ultra-fast
    CASCADE_WORKER = "qwen2.5:3b"    # Tier 2: default worker for most tasks
    CASCADE_HEAVY  = "qwen3:4b"      # Tier 3: only for genuinely complex tasks

    def __init__(self):
        self._active_model: str | None = None
        self._auto_mode: bool = True  # Auto-select by default
        self._cascade_mode: bool = True  # Use three-tier cascade by default
        self._task_history: list[TaskType] = []
        self._model_usage: dict[str, int] = {}  # model -> use count
        self._escalation_count: int = 0
        self._direct_handle_count: int = 0
        self._draft_verify_count: int = 0
        self._deterministic_count: int = 0
        # Adaptive performance tracking per tier
        self._perf: dict[str, _TierPerf] = {
            tier: _TierPerf(name=tier)
            for tier in (self.CASCADE_ROUTER, self.CASCADE_WORKER, self.CASCADE_HEAVY)
        }

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

    @property
    def cascade_mode(self) -> bool:
        return self._cascade_mode

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

    def set_cascade(self, enabled: bool) -> str:
        """Enable or disable three-tier cascade routing."""
        self._cascade_mode = enabled
        if enabled:
            return ("Cascade enabled: 1B router → 3B worker → 4B heavy. "
                    "1B handles simple tasks instantly, escalates as needed.")
        return "Cascade disabled. Using single-model auto-routing."

    def record_performance(self, model: str, success: bool,
                           latency_ms: float = 0.0, ttft_ms: float = 0.0) -> None:
        """Record performance data for a model tier. Used for adaptive routing.

        Called by the agent loop after each request completes.
        """
        tier = self._perf.get(model)
        if tier is None:
            # Create a tracking entry for models not in the default tiers
            tier = _TierPerf(name=model)
            self._perf[model] = tier
        tier.record(success, latency_ms, ttft_ms)
        logger.info("Perf recorded: %s success=%s latency=%.0fms ttft=%.0fms",
                     model, success, latency_ms, ttft_ms)

    def _get_adaptive_threshold(self) -> dict[str, Any]:
        """Compute adaptive routing thresholds from actual performance data.

        Returns settings that modify resolve_cascade() behavior:
        - draft_enabled: whether draft-then-verify is worth the extra latency
        - escalate_threshold: confidence below which we jump to 4B
        """
        router_perf = self._perf.get(self.CASCADE_ROUTER)
        worker_perf = self._perf.get(self.CASCADE_WORKER)

        # Default: draft-verify enabled, escalate at confidence < 0.45
        result = {
            "draft_enabled": True,
            "escalate_threshold": 0.45,
        }

        # If 1.5B has < 70% success rate after 5+ requests, disable draft
        if router_perf and router_perf.requests >= 5 and router_perf.success_rate < 0.70:
            result["draft_enabled"] = False
            logger.info("Adaptive: disabling draft-verify (1.5B success rate: %.0f%%)",
                        router_perf.success_rate * 100)

        # If 3B has < 80% success rate after 5+ requests, escalate earlier
        if worker_perf and worker_perf.requests >= 5 and worker_perf.success_rate < 0.80:
            result["escalate_threshold"] = 0.65  # More aggressively use 4B
            logger.info("Adaptive: raising escalate threshold (3B success rate: %.0f%%)",
                        worker_perf.success_rate * 100)

        # If 1.5B avg latency > 3s, it's not worth using even for simple tasks
        if router_perf and router_perf.requests >= 3 and router_perf.avg_ttft_ms > 3000:
            result["draft_enabled"] = False
            logger.info("Adaptive: disabling draft-verify (1.5B TTFT: %.0fms)",
                        router_perf.avg_ttft_ms)

        return result

    def get_perf_stats(self) -> dict[str, dict]:
        """Return performance stats for all tracked tiers."""
        return {name: tier.to_dict() for name, tier in self._perf.items() if tier.requests > 0}

    def resolve_cascade(self, prompt: str) -> dict[str, str | None]:
        """Resolve model routing using confidence + adaptive performance data.

        Strategy (updated — 1.5B is NOT the first stop for tool tasks):
          1. Deterministic commands → skip LLM entirely.
          2. QUICK/CONVERSATIONAL with high confidence → 1.5B handles directly.
          3. CODING/RESEARCH/WRITING/REASONING → go straight to 3B worker.
          4. Low confidence or ambiguous → 4B heavy model.
          5. Adapt escalation threshold based on actual performance metrics.

        Returns:
            {
                "router": "qwen2.5:1.5b",          # Always set (for reference)
                "worker": "qwen2.5:3b"|None,       # Set if escalated
                "heavy":  "qwen3:4b"|None,          # Set only for complex tasks
                "task_type": "coding",
                "confidence": 0.85,                  # 0.0–1.0
                "needs_tools": True,
                "draft_first": False,                 # 1.5B drafts, then 3B verifies
                "deterministic": False,               # Bypass LLM entirely
                "selected_model": "qwen2.5:3b",      # The actual model to use
            }
        """
        task_type, confidence = detect_task_type_with_confidence(prompt)
        self._task_history.append(task_type)
        if len(self._task_history) > 100:
            self._task_history = self._task_history[-50:]

        lower = prompt.strip()
        needs_tools = task_type not in (TaskType.QUICK, TaskType.CONVERSATIONAL)

        # ── Deterministic command bypass ──
        deterministic = lower.startswith("/") or _is_deterministic_command(lower)
        if deterministic:
            self._deterministic_count += 1
            return {
                "router": self.CASCADE_ROUTER,
                "worker": None,
                "heavy": None,
                "task_type": task_type.value,
                "confidence": 1.0,
                "needs_tools": False,
                "draft_first": False,
                "deterministic": True,
                "selected_model": self.CASCADE_ROUTER,
            }

        # Manual lock: skip cascade, use locked model for everything
        if not self._auto_mode and self._active_model:
            self._model_usage[self._active_model] = self._model_usage.get(self._active_model, 0) + 1
            return {
                "router": self._active_model,
                "worker": None,
                "heavy": None,
                "task_type": task_type.value,
                "confidence": confidence,
                "needs_tools": needs_tools,
                "draft_first": False,
                "deterministic": False,
                "selected_model": self._active_model,
            }

        # ── Adaptive performance threshold ──
        # If 1.5B has poor success rate on tool tasks, skip it entirely.
        _adaptive_threshold = self._get_adaptive_threshold()

        # ── Confidence-based routing ──

        # QUICK/CONVERSATIONAL → 1.5B handles directly (no tools needed)
        if task_type in (TaskType.QUICK, TaskType.CONVERSATIONAL):
            self._direct_handle_count += 1
            self._model_usage[self.CASCADE_ROUTER] = self._model_usage.get(self.CASCADE_ROUTER, 0) + 1
            return {
                "router": self.CASCADE_ROUTER,
                "worker": None,
                "heavy": None,
                "task_type": task_type.value,
                "confidence": confidence,
                "needs_tools": False,
                "draft_first": False,
                "deterministic": False,
                "selected_model": self.CASCADE_ROUTER,
            }

        # HEAVY task → 4B directly (don't waste time on smaller models)
        if task_type == TaskType.HEAVY or confidence < 0.45:
            self._escalation_count += 1
            self._model_usage[self.CASCADE_HEAVY] = self._model_usage.get(self.CASCADE_HEAVY, 0) + 1
            return {
                "router": self.CASCADE_ROUTER,
                "worker": self.CASCADE_HEAVY,
                "heavy": self.CASCADE_HEAVY,
                "task_type": task_type.value,
                "confidence": confidence,
                "needs_tools": True,
                "draft_first": False,
                "deterministic": False,
                "selected_model": self.CASCADE_HEAVY,
            }

        # CODING/RESEARCH/WRITING/REASONING → go straight to 3B worker
        # 1.5B does NOT get a chance to attempt tool tasks — it adds latency
        # for no benefit. The 3B model is the minimum viable model for tools.
        self._escalation_count += 1
        self._model_usage[self.CASCADE_WORKER] = self._model_usage.get(self.CASCADE_WORKER, 0) + 1

        # Adaptive: if 1.5B success rate is poor AND confidence is low,
        # skip draft-verify and go straight to 3B.
        use_draft = (
            _adaptive_threshold.get("draft_enabled", True)
            and 0.5 <= confidence < 0.8
        )

        if use_draft:
            self._draft_verify_count += 1

        return {
            "router": self.CASCADE_ROUTER,
            "worker": self.CASCADE_WORKER,
            "heavy": None,
            "task_type": task_type.value,
            "confidence": confidence,
            "needs_tools": True,
            "draft_first": use_draft,
            "deterministic": False,
            "selected_model": self.CASCADE_WORKER,
        }

    def resolve_model(self, prompt: str, available_models: list[str] | None = None) -> str | None:
        """Resolve which model to use for a prompt (single-model mode).

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
            "cascade_mode": self._cascade_mode,
            "cascade_router": self.CASCADE_ROUTER if self._cascade_mode else None,
            "cascade_worker": self.CASCADE_WORKER if self._cascade_mode else None,
            "cascade_heavy": self.CASCADE_HEAVY if self._cascade_mode else None,
            "direct_handle_count": self._direct_handle_count,
            "escalation_count": self._escalation_count,
            "draft_verify_count": self._draft_verify_count,
            "deterministic_count": self._deterministic_count,
            "task_counts": {
                t.value: self._task_history.count(t)
                for t in TaskType
            },
            "model_usage": dict(sorted(
                self._model_usage.items(), key=lambda x: x[1], reverse=True
            )),
            "perf_stats": self.get_perf_stats(),
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
