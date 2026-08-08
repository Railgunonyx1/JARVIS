"""Parallel LLM Reasoning — Run multiple hypotheses simultaneously.

For complex questions, generate multiple reasoning paths concurrently
and select the best result. Only used for complex tasks to save compute.
"""
import logging
import time
import asyncio
import threading
from typing import Optional, Dict, Any, List, Callable, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("reasoning_system.parallel_reasoning")


@dataclass
class Hypothesis:
    """A single reasoning hypothesis."""
    id: str
    prompt: str
    model: str = ""
    result: str = ""
    confidence: float = 0.0
    latency_ms: float = 0.0
    tokens: int = 0
    error: Optional[str] = None


@dataclass
class ReasoningResult:
    """Result of parallel reasoning."""
    question: str
    best_hypothesis: Optional[Hypothesis] = None
    all_hypotheses: List[Hypothesis] = field(default_factory=list)
    total_latency_ms: float = 0.0
    strategy: str = "parallel"
    consensus_score: float = 0.0


class ParallelReasoningEngine:
    """Run multiple LLM calls in parallel for complex reasoning.

    Strategies:
    - parallel: Run N hypotheses simultaneously, pick best
    - sequential: Try models in order until good enough
    - consensus: Run N hypotheses, combine if they agree

    Only activates for complex tasks to avoid wasting compute on greetings.
    """

    COMPLEXITY_THRESHOLD = 0.6  # Below this, use single-shot

    def __init__(self, llm_fn: Callable = None, max_parallel: int = 3):
        self._llm_fn = llm_fn
        self._max_parallel = max_parallel
        self._executor = ThreadPoolExecutor(max_workers=max_parallel, thread_name_prefix="reason")
        self._history: List[ReasoningResult] = []
        self._lock = threading.Lock()

    async def reason(self, question: str, complexity: float = 0.5,
                     strategy: str = "parallel") -> ReasoningResult:
        """Run parallel reasoning on a question.

        Args:
            question: The user's question
            complexity: 0-1 complexity score
            strategy: "parallel", "sequential", or "consensus"
        """
        start = time.time()

        if complexity < self.COMPLEXITY_THRESHOLD or strategy == "sequential":
            result = await self._sequential_reason(question)
        elif strategy == "consensus":
            result = await self._consensus_reason(question)
        else:
            result = await self._parallel_reason(question)

        result.total_latency_ms = (time.time() - start) * 1000
        result.question = question

        with self._lock:
            self._history.append(result)
            if len(self._history) > 100:
                self._history = self._history[-100:]

        return result

    async def _parallel_reason(self, question: str) -> ReasoningResult:
        """Run multiple hypotheses in parallel."""
        prompts = self._generate_hypotheses(question)
        hypotheses = []

        tasks = []
        for i, prompt in enumerate(prompts[:self._max_parallel]):
            hypothesis = Hypothesis(id=f"h{i}", prompt=prompt)
            hypotheses.append(hypothesis)
            tasks.append(self._evaluate_hypothesis(hypothesis))

        await asyncio.gather(*tasks, return_exceptions=True)

        # Select best by confidence
        valid = [h for h in hypotheses if h.error is None and h.result]
        best = max(valid, key=lambda h: h.confidence) if valid else None

        return ReasoningResult(
            question=question,
            best_hypothesis=best,
            all_hypotheses=hypotheses,
            strategy="parallel",
        )

    async def _sequential_reason(self, question: str) -> ReasoningResult:
        """Single-shot reasoning."""
        hypothesis = Hypothesis(id="s0", prompt=question)
        await self._evaluate_hypothesis(hypothesis)

        return ReasoningResult(
            question=question,
            best_hypothesis=hypothesis,
            all_hypotheses=[hypothesis],
            strategy="sequential",
        )

    async def _consensus_reason(self, question: str) -> ReasoningResult:
        """Run multiple hypotheses and check for consensus."""
        result = await self._parallel_reason(question)

        # Simple consensus: if top 2 have similar confidence, combine
        valid = sorted(
            [h for h in result.all_hypotheses if h.error is None],
            key=lambda h: h.confidence, reverse=True
        )
        if len(valid) >= 2:
            if abs(valid[0].confidence - valid[1].confidence) < 0.2:
                result.consensus_score = (valid[0].confidence + valid[1].confidence) / 2
                result.strategy = "consensus"

        return result

    async def _evaluate_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Evaluate a single hypothesis."""
        start = time.time()
        try:
            if self._llm_fn:
                result = await self._llm_fn(hypothesis.prompt)
                hypothesis.result = result
                hypothesis.confidence = self._estimate_confidence(result)
            else:
                hypothesis.result = f"Template response for: {hypothesis.prompt[:50]}"
                hypothesis.confidence = 0.5
        except Exception as e:
            hypothesis.error = str(e)
            hypothesis.confidence = 0.0

        hypothesis.latency_ms = (time.time() - start) * 1000

    def _generate_hypotheses(self, question: str) -> List[str]:
        """Generate different prompts for the same question."""
        return [
            question,
            f"Think step by step: {question}",
            f"Consider multiple angles: {question}",
        ]

    def _estimate_confidence(self, result: str) -> float:
        """Heuristic confidence based on response characteristics."""
        if not result:
            return 0.0
        confidence = 0.5
        if len(result) > 50:
            confidence += 0.1
        if len(result) > 200:
            confidence += 0.1
        if any(w in result.lower() for w in ["because", "therefore", "step", "first"]):
            confidence += 0.1
        if "?" not in result:
            confidence += 0.05
        return min(confidence, 1.0)

    def should_use_parallel(self, complexity: float) -> bool:
        """Decide if parallel reasoning is worth the compute cost."""
        return complexity >= self.COMPLEXITY_THRESHOLD

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._history)
            avg_latency = sum(r.total_latency_ms for r in self._history) / max(total, 1)
            parallel_count = sum(1 for r in self._history if r.strategy == "parallel")
            return {
                "total_reasonings": total,
                "parallel_reasonings": parallel_count,
                "avg_latency_ms": round(avg_latency, 1),
                "avg_consensus": round(
                    sum(r.consensus_score for r in self._history if r.consensus_score > 0) /
                    max(sum(1 for r in self._history if r.consensus_score > 0), 1), 2
                ),
            }


_reasoning_instance: Optional[ParallelReasoningEngine] = None


def get_parallel_reasoning_engine(llm_fn=None) -> ParallelReasoningEngine:
    global _reasoning_instance
    if _reasoning_instance is None:
        _reasoning_instance = ParallelReasoningEngine(llm_fn=llm_fn)
    return _reasoning_instance
