"""ModelManager - Unified LLM routing with health, cost, latency, and capability awareness.

Absorbs ProviderRouter (fallback), ModelRouter (heuristic classify),
and DynamicModelRouter (task-to-tier) into one service-oriented component.
"""

import re
import time
import logging
import random
from enum import Enum
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.core.model_manager")

# ──────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────

class TaskCategory(str, Enum):
    GREETING = "greeting"
    SIMPLE_QA = "simple_qa"
    CODING = "coding"
    REASONING = "reasoning"
    CREATIVE = "creative"
    VISION = "vision"
    OCR = "ocr"
    TRANSLATION = "translation"
    MATH = "math"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class ModelTier(int, Enum):
    TINY = 1
    SMALL = 2
    MEDIUM = 3
    LARGE = 4
    VISION = 5


@dataclass
class ModelEndpoint:
    provider: str
    model: str
    tier: ModelTier
    capabilities: List[str] = field(default_factory=list)
    cost_per_1k_tokens: float = 0.0
    avg_latency_ms: float = 0.0
    status: str = "active"
    last_used: float = 0.0
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    total_requests: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    last_error: Optional[str] = None


@dataclass
class ModelRequest:
    text: str
    system_prompt: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    category: Optional[TaskCategory] = None
    preferred_provider: Optional[str] = None
    max_latency_ms: Optional[float] = None
    max_cost: Optional[float] = None
    required_capabilities: Optional[List[str]] = None


@dataclass
class ModelDecision:
    endpoint: ModelEndpoint
    category: TaskCategory
    confidence: float
    reasoning: str
    alternatives: List[str] = field(default_factory=list)


@dataclass
class ModelResponse:
    text: str
    provider: str
    model: str
    tokens_used: int = 0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    cost: float = 0.0
    metadata: dict = field(default_factory=dict)


# ──────────────────────────────────────────────
# Classification patterns
# ──────────────────────────────────────────────

_TECHNICAL_TERMS = re.compile(
    r"\b(algorithm|function|class|variable|api|database|sql|regex|compile|debug|"
    r"refactor|implement|deploy|kubernetes|docker|nginx|ssh|git|ci/cd|pipeline|"
    r"encrypt|authenticate|payload|endpoint|middleware|binary|kernel|thread|"
    r"concurrency|mutex|semaphore|stack|heap|pointer|array|loop|recursion)\b",
    re.IGNORECASE,
)

_CREATIVE_TERMS = re.compile(
    r"\b(write|compose|draft|story|poem|creative|brainstorm|imagine|design|"
    r"narrative|dialogue|character|plot|metaphor|analogy|slogan|tagline|"
    r"advertising|copywriting|marketing|blog|article|essay|summary|tone|"
    r"rewrite|rephrase|paraphrase|synonym|fluent)\b",
    re.IGNORECASE,
)

_CODE_PATTERNS = re.compile(
    r"(def |class |import |from |return |if |for |while |try:|except|raise |"
    r"lambda |async |await |yield |{|}|=>|->|#include|#define)",
)

_SIMPLE_PATTERNS = re.compile(
    r"^(what|who|when|where|how much|how many|is|are|can you|define|"
    r"translate|convert|calculate|sum of|date|time|weather|time)\b",
    re.IGNORECASE,
)

_CATEGORY_KEYWORDS: Dict[TaskCategory, List[str]] = {
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

_CATEGORY_TIER_MAP: Dict[TaskCategory, ModelTier] = {
    TaskCategory.GREETING: ModelTier.TINY,
    TaskCategory.SIMPLE_QA: ModelTier.SMALL,
    TaskCategory.CODING: ModelTier.MEDIUM,
    TaskCategory.REASONING: ModelTier.MEDIUM,
    TaskCategory.CREATIVE: ModelTier.MEDIUM,
    TaskCategory.VISION: ModelTier.LARGE,
    TaskCategory.OCR: ModelTier.LARGE,
    TaskCategory.TRANSLATION: ModelTier.SMALL,
    TaskCategory.MATH: ModelTier.MEDIUM,
    TaskCategory.SYSTEM: ModelTier.MEDIUM,
    TaskCategory.UNKNOWN: ModelTier.SMALL,
}


# ──────────────────────────────────────────────
# ModelManager
# ──────────────────────────────────────────────

class ModelManager:
    def __init__(self):
        self._endpoints: Dict[str, ModelEndpoint] = {}
        self._providers: Dict[str, object] = {}
        self._preference: str = "balanced"
        self._stats_history: Dict[str, List[dict]] = {}
        self._health_callback: Optional[Callable] = None

    # ── Registration ──────────────────────────

    def register_endpoint(self, provider: str, model: str, tier: ModelTier,
                          capabilities: Optional[List[str]] = None,
                          cost_per_1k_tokens: float = 0.0,
                          avg_latency_ms: float = 0.0) -> str:
        key = f"{provider}/{model}"
        self._endpoints[key] = ModelEndpoint(
            provider=provider, model=model, tier=tier,
            capabilities=capabilities or [],
            cost_per_1k_tokens=cost_per_1k_tokens,
            avg_latency_ms=avg_latency_ms,
        )
        logger.info("Registered endpoint %s (tier=%s, caps=%s)", key, tier.value, capabilities)
        return key

    def register_provider(self, name: str, provider_instance: object):
        self._providers[name] = provider_instance

    def remove_endpoint(self, key: str):
        self._endpoints.pop(key, None)

    def set_health_callback(self, callback: Callable):
        self._health_callback = callback

    # ── Classification ────────────────────────

    def classify(self, query: str, context: Optional[dict] = None) -> Tuple[TaskCategory, float]:
        words = query.split()
        word_count = len(words)
        text_lower = query.lower().strip()

        keyword_category, keyword_score = self._keyword_classify(text_lower)

        code_hits = len(_CODE_PATTERNS.findall(query))
        tech_hits = len(_TECHNICAL_TERMS.findall(query))

        if code_hits >= 2 or tech_hits >= 3 or word_count > 40:
            return TaskCategory.CODING if code_hits >= tech_hits else TaskCategory.REASONING, 0.85

        if _CREATIVE_TERMS.search(query) and not code_hits and not tech_hits:
            return TaskCategory.CREATIVE, 0.85

        if keyword_score > 0:
            return keyword_category, keyword_score

        if word_count <= 6 and _SIMPLE_PATTERNS.match(query):
            return TaskCategory.SIMPLE_QA, 0.9

        if word_count > 15 or tech_hits >= 1:
            return TaskCategory.REASONING, 0.7

        if context and context.get("task_type") == "creative":
            return TaskCategory.CREATIVE, 0.6

        return TaskCategory.UNKNOWN, 0.3

    def _keyword_classify(self, text_lower: str) -> Tuple[TaskCategory, float]:
        best_cat = TaskCategory.UNKNOWN
        best_score = 0
        for category, keywords in _CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                best_cat = category
        if best_score > 0:
            words = text_lower.split()
            confidence = min(0.5 + best_score * 0.15, 1.0)
            if len(words) < 10:
                confidence = min(confidence + 0.1, 1.0)
            return best_cat, confidence
        return best_cat, 0.0

    # ── Selection ─────────────────────────────

    def _rank_endpoints(self, tier: ModelTier, required_caps: Optional[List[str]] = None,
                        max_cost: Optional[float] = None,
                        max_latency: Optional[float] = None) -> List[ModelEndpoint]:
        for attempt in range(tier.value, 0, -1):
            candidates = []
            for ep in self._endpoints.values():
                if ep.status != "active" or (ep.cooldown_until and time.time() < ep.cooldown_until):
                    continue
                # Skip providers that are unhealthy/unavailable (offline daemon, quota hit)
                prov = self._providers.get(ep.provider)
                if prov is not None and not prov.is_available:
                    continue
                if ep.tier.value < attempt:
                    continue
                if required_caps:
                    if not all(c in ep.capabilities for c in required_caps):
                        continue
                if max_cost is not None and ep.cost_per_1k_tokens > max_cost:
                    continue
                if max_latency is not None and ep.avg_latency_ms > max_latency:
                    continue
                candidates.append(ep)
            if candidates:
                candidates.sort(key=lambda e: (e.tier.value, e.avg_latency_ms))
                return candidates
        return []

    def select(self, request: ModelRequest) -> ModelDecision:
        category = request.category or self.classify(request.text)[0]
        tier = _CATEGORY_TIER_MAP.get(category, ModelTier.MEDIUM)

        candidates = self._rank_endpoints(
            tier,
            required_caps=request.required_capabilities,
            max_cost=request.max_cost,
            max_latency=request.max_latency_ms,
        )

        if not candidates:
            candidates = list(self._endpoints.values())
            if not candidates:
                raise RuntimeError("No model endpoints available")

        preferred = request.preferred_provider
        if preferred:
            preferred_eps = [e for e in candidates if e.provider == preferred]
            if preferred_eps:
                candidates = preferred_eps + [e for e in candidates if e.provider != preferred]

        selected = candidates[0]
        alts = [f"{e.provider}/{e.model}" for e in candidates[1:4]]

        reasons = [
            f"Category '{category.value}' → need tier ≥ {tier.value}",
            f"Selected {selected.provider}/{selected.model}",
        ]
        if request.required_capabilities:
            reasons.append(f"Requires: {request.required_capabilities}")
        if request.max_cost is not None:
            reasons.append(f"Cost cap: {request.max_cost}")
        if request.preferred_provider:
            reasons.append(f"Preferred: {request.preferred_provider}")

        decision = ModelDecision(
            endpoint=selected,
            category=category,
            confidence=1.0,
            reasoning=" | ".join(reasons),
            alternatives=alts,
        )
        return decision

    # ── Execute ───────────────────────────────

    async def complete(self, request: ModelRequest) -> ModelResponse:
        decision = self.select(request)
        ep = decision.endpoint
        return await self._execute(ep, request, decision)

    async def _execute(self, ep: ModelEndpoint, request: ModelRequest,
                       decision: ModelDecision) -> ModelResponse:
        provider = self._providers.get(ep.provider)
        if not provider:
            # Fallback: try alternatives
            for alt_key in decision.alternatives:
                alt_ep = self._endpoints.get(alt_key)
                if alt_ep:
                    alt_prov = self._providers.get(alt_ep.provider)
                    if alt_prov:
                        provider = alt_prov
                        ep = alt_ep
                        logger.info("Fell back to %s", alt_key)
                        break
            else:
                raise RuntimeError(f"Provider '{ep.provider}' not registered, no fallback available")

        try:
            start = time.perf_counter()
            # The provider's complete() returns LLMResponse-like object
            raw = await provider.complete(
                messages=[{"role": "user", "content": request.text}],
                system_prompt=request.system_prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
            latency_ms = (time.perf_counter() - start) * 1000

            ep.last_used = time.time()
            ep.total_requests += 1
            ep.avg_latency_ms = (ep.avg_latency_ms * (ep.total_requests - 1) + latency_ms) / ep.total_requests
            ep.consecutive_failures = 0
            ep.last_error = None

            tokens = getattr(raw, "tokens_used", 0)
            ep.total_tokens += tokens
            ep.total_cost += tokens / 1000 * ep.cost_per_1k_tokens

            return ModelResponse(
                text=raw.text,
                provider=ep.provider,
                model=raw.model,
                tokens_used=tokens,
                tokens_prompt=getattr(raw, "tokens_prompt", 0),
                tokens_completion=getattr(raw, "tokens_completion", 0),
                latency_ms=latency_ms,
                finish_reason=getattr(raw, "finish_reason", "stop"),
                cost=tokens / 1000 * ep.cost_per_1k_tokens,
                metadata={**getattr(raw, "metadata", {}), "tier": ep.tier.value},
            )

        except Exception as e:
            ep.consecutive_failures += 1
            ep.last_error = str(e)
            if ep.consecutive_failures >= 3:
                cooldown = min(300, 30 * (2 ** (ep.consecutive_failures - 3)))
                ep.cooldown_until = time.time() + cooldown
                logger.warning("%s/%s: cooldown %ds after %d failures",
                               ep.provider, ep.model, cooldown, ep.consecutive_failures)
            if ep.consecutive_failures >= 5:
                ep.status = "inactive"

            if self._health_callback:
                self._health_callback(ep.provider, ep.model, str(e))

            if decision.alternatives:
                next_key = decision.alternatives.pop(0)
                next_ep = self._endpoints.get(next_key)
                if next_ep:
                    logger.info("Failing over from %s/%s to %s", ep.provider, ep.model, next_key)
                    next_prov = self._providers.get(next_ep.provider)
                    if next_prov:
                        return await self._execute(next_ep, request, decision)
            raise

    async def complete_stream(self, request: ModelRequest) -> AsyncIterator[str]:
        decision = self.select(request)
        ep = decision.endpoint
        provider = self._providers.get(ep.provider)
        if not provider:
            raise RuntimeError(f"Provider '{ep.provider}' not registered")

        start = time.perf_counter()
        failures = 0
        async for chunk in provider.complete_stream(
            messages=[{"role": "user", "content": request.text}],
            system_prompt=request.system_prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        ):
            yield chunk

        latency_ms = (time.perf_counter() - start) * 1000
        ep.last_used = time.time()
        ep.total_requests += 1
        ep.avg_latency_ms = (ep.avg_latency_ms * (ep.total_requests - 1) + latency_ms) / ep.total_requests
        ep.consecutive_failures = 0

    # ── Health ─────────────────────────────────

    def record_success(self, provider: str, model: str, latency_ms: float, tokens: int = 0):
        key = f"{provider}/{model}"
        ep = self._endpoints.get(key)
        if ep:
            ep.last_used = time.time()
            ep.total_requests += 1
            ep.avg_latency_ms = (ep.avg_latency_ms * (ep.total_requests - 1) + latency_ms) / ep.total_requests
            ep.total_tokens += tokens
            ep.consecutive_failures = 0
            ep.last_error = None
            ep.status = "active"

    def record_failure(self, provider: str, model: str, error: str):
        key = f"{provider}/{model}"
        ep = self._endpoints.get(key)
        if ep:
            ep.consecutive_failures += 1
            ep.last_error = error
            if ep.consecutive_failures >= 3:
                cooldown = min(300, 30 * (2 ** (ep.consecutive_failures - 3)))
                ep.cooldown_until = time.time() + cooldown
            if ep.consecutive_failures >= 5:
                ep.status = "inactive"

    # ── Stats / Status ─────────────────────────

    def get_status(self) -> dict:
        return {
            key: {
                "provider": ep.provider,
                "model": ep.model,
                "tier": ep.tier.value,
                "status": ep.status,
                "capabilities": ep.capabilities,
                "avg_latency_ms": round(ep.avg_latency_ms, 1),
                "cost_per_1k": ep.cost_per_1k_tokens,
                "total_requests": ep.total_requests,
                "total_tokens": ep.total_tokens,
                "total_cost": round(ep.total_cost, 4),
                "consecutive_failures": ep.consecutive_failures,
                "cooldown_until": ep.cooldown_until,
                "last_error": ep.last_error,
            }
            for key, ep in self._endpoints.items()
        }

    def get_stats(self) -> dict:
        total_requests = sum(ep.total_requests for ep in self._endpoints.values())
        total_tokens = sum(ep.total_tokens for ep in self._endpoints.values())
        total_cost = sum(ep.total_cost for ep in self._endpoints.values())
        return {
            "total_endpoints": len(self._endpoints),
            "active_endpoints": sum(1 for ep in self._endpoints.values() if ep.status == "active"),
            "inactive_endpoints": sum(1 for ep in self._endpoints.values() if ep.status == "inactive"),
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 4),
            "preference": self._preference,
        }

    def set_preference(self, preference: str):
        if preference not in ("speed", "quality", "balanced"):
            raise ValueError(f"Invalid preference: {preference!r}")
        self._preference = preference
        logger.info("Model preference set to %s", preference)

    def get_endpoint(self, key: str) -> Optional[ModelEndpoint]:
        return self._endpoints.get(key)

    def warmup(self, key: str) -> bool:
        """Mark an endpoint for warmup (stub)."""
        ep = self._endpoints.get(key)
        if ep:
            logger.info("Warmup requested for %s", key)
            return True
        return False
