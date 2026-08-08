"""Dynamic Temperature — Automatically select optimal temperature by task type.

Coding: 0.1 | Brainstorming: 0.8 | Math: 0 | Architecture: 0.3
"""
import logging
import threading
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger("ai_runtime.dynamic_temperature")


@dataclass
class TemperatureProfile:
    """Temperature settings for a task type."""
    name: str
    temperature: float
    top_p: float = 0.9
    top_k: int = 40
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0


# Task type → temperature profile mapping
TASK_PROFILES = {
    "coding": TemperatureProfile("coding", temperature=0.1, top_p=0.95, top_k=10),
    "math": TemperatureProfile("math", temperature=0.0, top_p=1.0, top_k=1),
    "architecture": TemperatureProfile("architecture", temperature=0.3, top_p=0.9, top_k=30),
    "brainstorming": TemperatureProfile("brainstorming", temperature=0.8, top_p=0.95, top_k=50),
    "creative": TemperatureProfile("creative", temperature=0.85, top_p=0.95, top_k=60),
    "factual": TemperatureProfile("factual", temperature=0.1, top_p=0.9, top_k=20),
    "conversation": TemperatureProfile("conversation", temperature=0.4, top_p=0.9, top_k=40),
    "translation": TemperatureProfile("translation", temperature=0.2, top_p=0.9, top_k=30),
    "summarization": TemperatureProfile("summarization", temperature=0.3, top_p=0.9, top_k=25),
    "default": TemperatureProfile("default", temperature=0.4, top_p=0.9, top_k=40),
}

# Keyword patterns for task detection
TASK_KEYWORDS = {
    "coding": ["code", "function", "class", "implement", "debug", "error", "fix", "python", "javascript", "api"],
    "math": ["calculate", "compute", "equation", "formula", "math", "sum", "average", "integral"],
    "architecture": ["design", "architect", "system", "infrastructure", "scale", "microservice"],
    "brainstorming": ["brainstorm", "ideas", "creative", "imagine", "innovative", "alternatives"],
    "creative": ["write", "story", "poem", "narrative", "fiction", "creative"],
    "factual": ["what is", "who is", "when did", "where is", "define", "explain"],
    "translation": ["translate", "translation", "in spanish", "in french", "in german"],
    "summarization": ["summarize", "summary", "tldr", "brief", "overview"],
}


class DynamicTemperatureSelector:
    """Automatically select optimal temperature based on task type."""

    def __init__(self):
        self._custom_profiles: Dict[str, TemperatureProfile] = {}
        self._selection_count = 0
        self._task_counts: Dict[str, int] = {}
        self._lock = threading.Lock()

    def detect_task_type(self, prompt: str) -> str:
        """Detect the task type from the prompt."""
        prompt_lower = prompt.lower()

        scores = {}
        for task_type, keywords in TASK_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in prompt_lower)
            if score > 0:
                scores[task_type] = score

        if scores:
            return max(scores, key=scores.get)
        return "default"

    def select(self, prompt: str, explicit_type: str = None) -> TemperatureProfile:
        """Select the optimal temperature profile for a prompt."""
        task_type = explicit_type or self.detect_task_type(prompt)

        with self._lock:
            self._selection_count += 1
            self._task_counts[task_type] = self._task_counts.get(task_type, 0) + 1

        profile = self._custom_profiles.get(task_type) or TASK_PROFILES.get(task_type, TASK_PROFILES["default"])
        logger.debug("Temperature: '%s...' → %s (temp=%.2f)", prompt[:30], task_type, profile.temperature)
        return profile

    def set_custom_profile(self, task_type: str, profile: TemperatureProfile) -> None:
        with self._lock:
            self._custom_profiles[task_type] = profile

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "selections": self._selection_count,
                "task_distribution": dict(self._task_counts),
                "custom_profiles": len(self._custom_profiles),
            }


_temp_selector_instance: Optional[DynamicTemperatureSelector] = None


def get_dynamic_temperature() -> DynamicTemperatureSelector:
    global _temp_selector_instance
    if _temp_selector_instance is None:
        _temp_selector_instance = DynamicTemperatureSelector()
    return _temp_selector_instance
