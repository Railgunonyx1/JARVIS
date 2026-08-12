"""Dynamic Model Router — Route tasks to optimal model by complexity.

| Task         | Model        |
| ------------ | ------------ |
| Greeting     | Tiny (1B)    |
| Coding       | Medium (7B)  |
| Architecture | Large (14B+) |
| Vision       | Vision model |
| OCR          | OCR model    |
"""
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("optimization_system.dynamic_model_router")


class TaskCategory(Enum):
    GREETING = "greeting"
    SIMPLE_QA = "simple_qa"
    CODING = "coding"
    REASONING = "reasoning"
    CREATIVE = "creative"
    VISION = "vision"
    OCR = "ocr"
    TRANSLATION = "translation"
    MATH = "math"
    UNKNOWN = "unknown"


@dataclass
class ModelConfig:
    """Configuration for a model."""
    name: str
    provider: str
    model_id: str
    max_tokens: int = 4096
    cost_per_1k_tokens: float = 0.0
    avg_latency_ms: float = 0.0
    capabilities: list[str] = field(default_factory=list)
    tier: int = 1  # 1=tiny, 2=small, 3=medium, 4=large


@dataclass
class RoutingDecision:
    """Decision from the model router."""
    task_category: str
    selected_model: str
    provider: str
    confidence: float
    reasoning: str
    alternatives: list[str] = field(default_factory=list)


# Keyword patterns for task classification
CATEGORY_KEYWORDS = {
    TaskCategory.GREETING: ["hello", "hi", "hey", "good morning", "good evening", "how are you", "thanks", "thank you"],
    TaskCategory.CODING: ["code", "function", "class", "debug", "error", "bug", "implement", "write a", "program", "script", "api", "python", "javascript"],
    TaskCategory.REASONING: ["why", "explain", "how does", "analyze", "compare", "evaluate", "reason", "think", "strategy"],
    TaskCategory.CREATIVE: ["write", "story", "poem", "creative", "imagine", "brainstorm", "idea"],
    TaskCategory.VISION: ["screen", "see", "look at", "image", "picture", "photo", "screenshot"],
    TaskCategory.OCR: ["read text", "extract text", "ocr", "text from image"],
    TaskCategory.TRANSLATION: ["translate", "translation", "in spanish", "in french", "in german"],
    TaskCategory.MATH: ["calculate", "compute", "math", "equation", "formula", "sum", "average"],
    TaskCategory.SIMPLE_QA: ["what is", "who is", "where is", "when", "define", "meaning"],
}


class DynamicModelRouter:
    """Route tasks to the optimal model based on task complexity.

    Tiny models (1B) for greetings → Huge latency savings.
    Large models only for complex reasoning → Better quality where it matters.
    """

    def __init__(self):
        self._models: dict[str, ModelConfig] = {}
        self._category_history: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._routing_count = 0
        self._category_counts: dict[str, int] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register_model("tiny", ModelConfig(
            name="tiny", provider="ollama", model_id="gemma3:1b",
            tier=1, cost_per_1k_tokens=0.0, avg_latency_ms=100,
            capabilities=["greeting", "simple_qa"],
        ))
        self.register_model("small", ModelConfig(
            name="small", provider="ollama", model_id="qwen2.5:1.5b",
            tier=2, cost_per_1k_tokens=0.0, avg_latency_ms=200,
            capabilities=["greeting", "simple_qa", "coding"],
        ))
        self.register_model("medium", ModelConfig(
            name="medium", provider="groq", model_id="llama-3.3-70b-versatile",
            tier=3, cost_per_1k_tokens=0.0, avg_latency_ms=800,
            capabilities=["coding", "reasoning", "creative", "math"],
        ))
        self.register_model("large", ModelConfig(
            name="large", provider="gemini", model_id="gemini-2.5-flash",
            tier=4, cost_per_1k_tokens=0.0, avg_latency_ms=1500,
            capabilities=["coding", "reasoning", "creative", "vision", "math"],
        ))

    def register_model(self, name: str, config: ModelConfig) -> None:
        with self._lock:
            self._models[name] = config

    def classify_task(self, text: str) -> tuple[TaskCategory, float]:
        """Classify a task into a category with confidence."""
        text_lower = text.lower().strip()

        best_category = TaskCategory.UNKNOWN
        best_score = 0.0

        for category, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                best_category = category

        # Confidence based on keyword matches and text length
        text_len = len(text_lower.split())
        if best_score > 0:
            confidence = min(0.5 + best_score * 0.15 + (1.0 if text_len < 10 else 0.0), 1.0)
        else:
            confidence = 0.3

        return best_category, confidence

    def route(self, text: str) -> RoutingDecision:
        """Route a task to the optimal model."""
        category, confidence = self.classify_task(text)
        self._routing_count += 1
        self._category_counts[category.value] = self._category_counts.get(category.value, 0) + 1

        # Select model based on category
        model_name = self._select_model_for_category(category)
        model = self._models.get(model_name)

        alternatives = [m for m in self._models if m != model_name]

        decision = RoutingDecision(
            task_category=category.value,
            selected_model=model_name,
            provider=model.provider if model else "unknown",
            confidence=confidence,
            reasoning=f"Category '{category.value}' → model '{model_name}' (confidence: {confidence:.0%})",
            alternatives=alternatives[:3],
        )

        logger.debug("Route: '%s...' → %s (%s)", text[:30], model_name, category.value)
        return decision

    def _select_model_for_category(self, category: TaskCategory) -> str:
        """Select the best model for a task category."""
        category_model_map = {
            TaskCategory.GREETING: "tiny",
            TaskCategory.SIMPLE_QA: "small",
            TaskCategory.CODING: "medium",
            TaskCategory.REASONING: "medium",
            TaskCategory.CREATIVE: "medium",
            TaskCategory.VISION: "large",
            TaskCategory.OCR: "large",
            TaskCategory.TRANSLATION: "small",
            TaskCategory.MATH: "medium",
            TaskCategory.UNKNOWN: "medium",
        }
        return category_model_map.get(category, "medium")

    def record_latency(self, model_name: str, latency_ms: float) -> None:
        """Record observed latency for adaptive routing."""
        with self._lock:
            if model_name not in self._category_history:
                self._category_history[model_name] = []
            self._category_history[model_name].append(latency_ms)
            if len(self._category_history[model_name]) > 100:
                self._category_history[model_name] = self._category_history[model_name][-100:]

    def get_model_for_latency(self, target_ms: float) -> str | None:
        """Find the best model that can meet a latency target."""
        for name, config in sorted(self._models.items(), key=lambda x: x[1].tier):
            if config.avg_latency_ms <= target_ms:
                return name
        return None

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "routing_count": self._routing_count,
                "category_distribution": dict(self._category_counts),
                "models_registered": len(self._models),
                "model_list": {
                    name: {
                        "provider": m.provider,
                        "model_id": m.model_id,
                        "tier": m.tier,
                        "avg_latency_ms": m.avg_latency_ms,
                    }
                    for name, m in self._models.items()
                },
            }


_router_instance: DynamicModelRouter | None = None


def get_dynamic_model_router() -> DynamicModelRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = DynamicModelRouter()
    return _router_instance
