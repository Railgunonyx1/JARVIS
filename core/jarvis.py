"""JARVIS MK-X — Main Orchestrator (LEGACY).

Ties all subsystems together.

**DEPRECATION NOTICE:** This class is in legacy mode. New code should use
`core.agent.loop.AgentLoop` with `core.agent.permissions.PermissionEngine`
and `core.agent.tools.AgentToolExecutor` for deterministic, audit-driven
execution. This class is preserved for backward compatibility only.

The dual-agent-path risk (legacy jarvis.py coexisting with active
core/agent/loop.py) is addressed by redirecting all new execution through
the active path.
"""

import asyncio
import datetime
import logging
import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from core.cache import SemanticCache
from core.config import Config
from core.context_engine import ContextEngine
from core.diagnostics_engine import DiagnosticsEngine
from core.dialogue import DialogueStateMachine
from core.health import format_health_report, run_all_checks
from core.intent_router import IntentRouter
from core.lazy_imports import LazyModule
from core.log_queue import log_conversation_async
from core.personality import PersonalityEngine
from core.personality_responses import generate_deterministic_response
from core.telemetry import get_tracker
from memory.store import MemoryStore
from python.tracing import trace_span

# Heavy imports deferred to reduce startup time
_Mod_providers = LazyModule("providers.router")
_Mod_stt = LazyModule("pipeline.stt")
_Mod_tts = LazyModule("pipeline.tts")
_Mod_vad = LazyModule("pipeline.vad")
_Mod_wake_word = LazyModule("pipeline.wake_word")
_Mod_kg_graph = LazyModule("knowledge_graph.graph")
_Mod_kg_query = LazyModule("knowledge_graph.query")
_Mod_security = LazyModule("security.engine")

logger = logging.getLogger("jarvis")


def _provider_caps(name: str) -> list:
    """Capabilities advertised per provider for ModelManager routing."""
    if name == "ollama":
        return ["local", "offline", "text"]
    if name == "gemini":
        return ["text", "vision", "reasoning", "large"]
    if name == "openrouter":
        return ["text", "reasoning", "medium"]
    if name == "opencode_zen":
        return ["text", "coding", "medium"]
    return ["text"]


# ── New subsystem imports (lazy, try/except for resilience) ──────────────────
def _safe_import(import_fn, label: str):
    """Import a subsystem safely, returning None on failure."""
    try:
        return import_fn()
    except Exception as e:
        logger.debug("%s init skipped: %s", label, e)
        return None


def _strip_md(s: str) -> str:
    """Strip markdown formatting from response text for clean TTS and display."""
    s = re.sub(r'<thinking>[\s\S]*?</thinking>', '', s)
    s = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', s)
    s = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', s)
    s = re.sub(r'`([^`]+)`', r'\1', s)
    s = re.sub(r'```[\s\S]*?```', '', s)
    s = re.sub(r'^#+\s+', '', s, flags=re.MULTILINE)
    s = re.sub(r'^[-*]\s+', '• ', s, flags=re.MULTILINE)
    return s.strip()


PROMPT_PATH = Path(__file__).resolve().parent.parent / "core" / "prompt.txt"


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS (MARK L), an advanced AI voice assistant created by Aayan. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )


# ── Phrase-level TTS chunking ─────────────────────────────────────────────────
# Splits text into small chunks (5 words or natural pauses) so TTS starts sooner.

_MIN_PHRASE_WORDS = 5
_MIN_PHRASE_CHARS = 20
# Natural pause characters that justify a TTS break
_PAUSE_CHARS = set(',;—–:')


def _split_phrases(text: str) -> list[str]:
    """Split text into phrase-level chunks for fast TTS streaming.
    Yields chunks of ~5 words or at natural pause points."""
    phrases = []
    words = text.split()
    buf = []
    for word in words:
        buf.append(word)
        # Flush on: 5+ words, or pause char, or buffer > 20 chars
        joined = " ".join(buf)
        if (len(buf) >= _MIN_PHRASE_WORDS
                or (len(joined) >= _MIN_PHRASE_CHARS and any(c in _PAUSE_CHARS for c in joined[-3:]))
                or any(c in _PAUSE_CHARS for c in word)):
            phrases.append(joined)
            buf = []
    if buf:
        phrases.append(" ".join(buf))
    return phrases


def _flush_phrases(phrase_buf: str, tts_queue: asyncio.Queue) -> str:
    """Flush complete phrases from the buffer into the TTS queue.
    Returns the remaining (incomplete) buffer."""
    phrases = _split_phrases(phrase_buf)
    if len(phrases) <= 1:
        return phrase_buf
    # Emit all but the last (which may be incomplete)
    for p in phrases[:-1]:
        tts_queue.put_nowait(p)
    return phrases[-1]


class JarvisMKX:
    def __init__(self, on_status_change: Callable | None = None):
        self.session_id = str(uuid.uuid4())[:8]
        self.config = Config.instance()
        api_keys = self.config.api_keys
        models_cfg = self.config.get_section("models")
        voice_cfg = self.config.get_section("voice")

        self.router = _mod_providers.ProviderRouter(models_cfg, api_keys)

        # Unified ModelManager: task classification → best provider/model selection,
        # with per-endpoint health, latency, cost, and cooldown tracking.
        # Falls back to ProviderRouter (fallback chain) for execution.
        from core.model_manager import ModelManager, ModelTier
        self.model_manager = ModelManager()
        try:
            _provider_tiers = {
                "groq": ModelTier.SMALL,
                "gemini": ModelTier.LARGE,
                "openrouter": ModelTier.MEDIUM,
                "opencode_zen": ModelTier.MEDIUM,
                "ollama": ModelTier.TINY,
            }
            for name, prov in self.router._providers.items():
                tier = _provider_tiers.get(name, ModelTier.MEDIUM)
                try:
                    self.model_manager.register_endpoint(
                        provider=name,
                        model=prov.model,
                        tier=tier,
                        capabilities=_provider_caps(name),
                    )
                    self.model_manager.register_provider(name, prov)
                except Exception:
                    logger.debug("Failed to register endpoint %s/%s", name, getattr(prov, "model", "?"))
        except Exception:
            logger.debug("ModelManager wiring failed; using ProviderRouter only", exc_info=True)

        # Outcome statistics router (record_outcome / get_model_stats)
        from inference_engine.model_router import get_model_router
        self.model_router = get_model_router()

        # Auditability: decision logger bridges EventStore + AuditLog.
        from core.decision_logger import get_decision_logger
        self.decision_logger = get_decision_logger()

        # Voice services: lazy-loaded on first use (saves ~400MB idle RAM)
        self.stt = None
        self.tts = None
        self.vad = None
        self.wake_word = None
        self._voice_loaded = False
        self._startup_done = False
        self._startup_lock = None
        self.intent_router = IntentRouter()
        self.context = ContextEngine(self.config.get_section("jarvis"))
        self.dialogue = DialogueStateMachine()
        self.memory = MemoryStore()
        self._log_queue = None  # Initialized in start()
        self.personality = PersonalityEngine()
        self.diagnostics = DiagnosticsEngine()
        self.semantic_cache = SemanticCache()

        # Action Registry — replaces _handle_action if/elif chain
        from core.action_init import register_all_actions
        from core.action_registry import ActionRegistry
        self.action_registry = ActionRegistry()
        register_all_actions(self.action_registry)

        self._base_prompt = _load_system_prompt()
        self._system_prompt_cache: str | None = None
        self._system_prompt_hour: int = -1
        self._memory_cache: str | None = None
        self._kg_cache: str | None = None
        self._kg_cache_time: float = 0.0

        # Optional subsystems: lazy-loaded on first use
        self.plugin_loader = None
        self.vector_memory = None
        self.knowledge_graph = None
        self.graph_query = None
        self.security = None

        # Health monitor and circuit breaker (wired on demand)
        self.health_monitor = None
        self.circuit_breaker = None
        self.auto_optimizer = None
        self.regression_guard = None
        self.circuit_breaker = None
        self.health_monitor = None
        self.graceful_degradation = None
        self.trust_scorer = None
        self.anomaly_detector = None
        self.adaptive_policy = None
        self.intent_predictor = None
        self.context_enhancer = None
        self.conversation_flow = None
        self.knowledge_optimizer = None
        self.semantic_search = None
        self.knowledge_distiller = None
        self.hyp_opt_manager = None
        self.hyp_profiler = None
        self.hyp_pipeline = None
        self.hyp_branch_pred = None
        self.hyp_scheduler = None
        self.hyp_speculative = None
        self.hyp_prefetch = None
        self.hyp_cache_pred = None
        self.hyp_zcm = None
        self.hyp_obj_pool = None
        self.hyp_mem_alloc = None
        self.hyp_cpu_affinity = None
        self.hyp_lock_opt = None
        self.hyp_gpu = None
        self.hyp_io_opt = None
        self.hyp_startup_opt = None
        self.hyp_hot_reload = None
        self.hyp_resource_pred = None
        self.hyp_dashboard = None
        self.digital_twin = None
        self.self_perf_monitor = None
        self.self_optimizer = None
        self.event_bus = None
        self.perf_governor = None
        self.adaptive_scheduler = None
        self.adaptive_degradation = None
        self.multi_level_cache = None
        self.embedding_cache = None
        self.profiler = None
        self.perf_cache = None
        self.power_manager = None
        self.process_optimizer = None
        self.prefetch_engine = None
        self.perf_analyzer_engine = None
        self.compilation_cache = None
        self.parallel_reasoning = None
        self.hierarchical_planner = None
        self.incremental_planner = None
        self.streaming_tools = None
        self.dyn_model_router = None
        self.predictive_context = None
        self.aot_warmup = None
        self.incremental_indexer = None
        self.benchmark = None
        self.weather = None
        self.news = None
        self.email_client = None
        self.calendar = None
        self.web_scraper = None
        self.rss_reader = None
        self.code_generator = None
        self.code_analyzer = None
        self.test_generator = None
        self.refactor_engine = None
        self.token_stream = None
        self.token_pred_cache = None
        self.spec_decoder = None
        self.kv_cache = None
        self.context_pruner = None
        self.prompt_compressor = None
        self.context_delta = None
        self.dyn_temp = None
        self.multi_stage = None
        self.tool_first = None
        self.dyn_precision = None
        self.gpu_residency = None
        self.vram_defrag = None
        self.gpu_scheduler_p92 = None
        self.batch_proc = None
        self.kernel_fusion = None
        self.worker_scaler = None
        self.dep_resolver = None
        self.micro_profiler = None
        self.runtime_dashboard = None
        self.os_priority = None
        self.thread_affinity = None
        self.mem_locker = None
        self.net_pool = None
        self.os_power = None

        logger.info("JARVIS MK-X initialized (session: %s)", self.session_id)

    async def _ensure_voice_loaded(self):
        """Lazy-load voice services on first use. Saves ~400MB idle RAM."""
        if self._voice_loaded:
            return
        voice_cfg = self.config.get_section("voice")
        api_keys = self.config.api_keys
        self.tts = _mod_tts.TextToSpeech(voice_cfg)
        self.stt = _mod_stt.SpeechToText(voice_cfg, api_keys)
        self.vad = _mod_vad.VoiceActivityDetector(voice_cfg)
        self.wake_word = _mod_wake_word.WakeWordDetector(voice_cfg, on_wake=self._on_wake_word)
        self._voice_loaded = True
        logger.info("Voice services loaded")

    async def _ensure_started(self):
        """Run startup warmup lazily, on the first request (not at boot)."""
        if self._startup_done:
            return
        if self._startup_lock is None:
            self._startup_lock = asyncio.Lock()
        async with self._startup_lock:
            if not self._startup_done:
                await self.startup()
                self._startup_done = True

    async def startup(self):
        """Warm-start: only what's needed for the first response.
        TTS precache is deferred to background. Voice is lazy-loaded."""
        import time as _time
        start = _time.time()

        # 1. Concurrent provider init (saves wall-clock by parallelizing client construction)
        async def _provider_warm():
            try:
                _ = self.router.status
                loop = asyncio.get_running_loop()
                tasks = []
                for provider in self.router._providers.values():
                    if hasattr(provider, '_get_client'):
                        tasks.append(
                            loop.run_in_executor(None, provider._get_client)
                        )
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                logger.warning("Provider warmup failed: %s", e)

        await _provider_warm()

        # 2. Build system prompt (instant, just string ops)
        try:
            self._build_system_prompt()
        except Exception as e:
            logger.warning("Prompt cache failed: %s", e)

        # 3. Pre-warm SQLite connection (fast)
        try:
            self.memory.get_stats()
        except Exception as e:
            logger.warning("Memory warmup failed: %s", e)

        # 4. TTS precache deferred to first TTS use (not at startup)
        self._precache_done = False

        elapsed = (_time.time() - start) * 1000
        logger.info("Warm-start complete in %.0fms", elapsed)

    def startup_check(self) -> str:
        return format_health_report(run_all_checks())

    async def process_text(self, text: str) -> str:
        if not text.strip():
            return ""

        await self._ensure_started()

        trace_id = self.decision_logger.begin_task(text, source="process_text")

        tracker = get_tracker()
        tracker.start_request()
        tracker.mark("intent_start")

        # Start profiling for this request
        _prof_name = f"request_{uuid.uuid4().hex[:6]}"
        if self.profiler:
            self.profiler.record_metric("request_start", 1)

        # Check trust for this input
        if self.trust_scorer:
            try:
                trust = self.trust_scorer.score_action("user_input", {"text_length": len(text)})
                if trust.get("risk_level") == "critical":
                    logger.warning("Critical trust level for input: %s", text[:50])
            except Exception:
                pass

        _t0 = time.time()
        timeline = [("start", 0)]

        self.dialogue.transition("speech_input", {"text": text})
        self.context.add_turn("user", text)

        intent = self.intent_router.classify(text)
        tracker.mark("intent_end")
        tracker.mark("memory_start")
        timeline.append(("intent", (time.time() - _t0) * 1000))
        logger.info("Intent: %s (%.0f%%) via %s", intent.name, intent.confidence * 100, intent.source)
        await self.decision_logger.record_async(trace_id, "intent.classified", {"intent": intent.name, "confidence": intent.confidence, "source": intent.source})

        # Analyze complexity for model routing hints
        complexity_analyzer = getattr(self, "complexity_analyzer", None)
        if complexity_analyzer:
            try:
                complexity = self.complexity_analyzer.analyze(text)
                logger.debug("Complexity: %.2f (%s)", complexity.get("score", 0), complexity.get("category", "unknown"))
            except Exception:
                pass

        response = generate_deterministic_response(intent, text, self.personality, self.context.user.facts)

        if intent.name == "memory.store" and intent.entities.get("fact"):
            fact_text = intent.entities["fact"]
            self.context.add_fact(fact_text)
            if hasattr(self, "vector_memory") and self.vector_memory:
                self.vector_memory.store_vector(fact_text, category="fact")
            self.invalidate_memory_cache()

        if intent.name == "system.clear":
            self.context.clear_history()

        if response is None:
            tracker.mark("action_start")
            try:
                response = await self._handle_action(intent, text, trace_id)
                await self.decision_logger.record_async(trace_id, "path.decided", {"path": "action"})
            except Exception as exc:
                logger.error("Action handler failed: %s", exc, exc_info=True)
                await self.decision_logger.record_async(trace_id, "task.failed", {"error": str(exc), "stage": "action"})
                response = f"Sorry, something went wrong while handling that ({type(exc).__name__})."
            tracker.mark("action_end")
            timeline.append(("action", (time.time() - _t0) * 1000))
        if response is None:
            tracker.mark("llm_start")
            start = time.time()
            await self.decision_logger.record_async(trace_id, "path.decided", {"path": "llm"})
            response = await self._query_llm(text)
            llm_ms = (time.time() - start) * 1000
            tracker.mark("llm_end")
            timeline.append(("llm", (time.time() - _t0) * 1000))
            await self.decision_logger.record_async(trace_id, "llm.completed", {"latency_ms": llm_ms, "tokens_out": len(response.split())})
            self.diagnostics.record_request(
                provider=self.router._last_provider or "unknown",
                model=self.router._last_model or "unknown",
                success=True, latency_ms=llm_ms,
                tokens_in=len(text.split()), tokens_out=len(response.split()),
            )
        else:
            timeline.append(("deterministic", (time.time() - _t0) * 1000))
            await self.decision_logger.record_async(trace_id, "path.decided", {"path": "deterministic"})

        response = _strip_md(response)
        response = self.personality.style_response(response, intent.name)
        self.context.add_turn("assistant", response, intent=intent.name, confidence=intent.confidence)
        await log_conversation_async(self.session_id, "user", text)
        await log_conversation_async(self.session_id, "assistant", response)

        # Ingest into knowledge graph
        if self.graph_query:
            try:
                self.graph_query.ingest_conversation(text, response, intent.name, intent.entities)
            except Exception as e:
                logger.debug("Knowledge graph ingestion failed: %s", e)

        self.dialogue.transition("processing_done")
        self.dialogue.transition("reset")
        self.personality.on_interaction_complete(success=True)

        total_ms = (time.time() - _t0) * 1000
        tracker.mark("tts_start")
        # TTS is handled by streaming endpoint
        tracker.mark("tts_end")
        timeline.append(("done", total_ms))
        tracker.end_request()

        # Record performance metrics
        if self.perf_analyzer_engine:
            try:
                self.perf_analyzer_engine.record_metric("total_latency_ms", total_ms)
            except Exception:
                pass
        if self.perf_cache:
            try:
                self.perf_cache.put(f"response_{hash(text) % 10000}", response, ttl_seconds=600)
            except Exception:
                pass
        # Check for regression
        if self.regression_guard:
            try:
                check = self.regression_guard.check_regression("total_latency_ms", total_ms)
                if check.get("regressed"):
                    logger.warning("Regression detected: latency %.0fms vs baseline %.0fms",
                                   total_ms, check.get("baseline", 0))
            except Exception:
                pass

        logger.info("Timeline: %s", " → ".join(f"{s}={v:.0f}ms" for s, v in timeline))

        await self.decision_logger.record_async(trace_id, "task.completed", {"latency_ms": total_ms, "intent": intent.name})

        return response

    async def _handle_action(self, intent, text: str, trace_id: str | None = None) -> str | None:
        # Delegate to ActionRegistry (replaces 30+ if/elif chain)
        _t0 = time.time()
        result = await self.action_registry.execute(
            intent, text, api_keys=self.config.api_keys,
        )
        if result is not None:
            if trace_id:
                await self.decision_logger.record_async(trace_id, "action.executed", {
                    "handler": "action_registry", "intent": intent.name,
                    "success": True, "latency_ms": (time.time() - _t0) * 1000,
                })
            return result

        # Plugin fallback
        if self.plugin_loader and self.plugin_loader.loaded_plugins:
            for p_name, p_info in self.plugin_loader.loaded_plugins.items():
                if p_name == intent.name or any(pattern in text.lower() for pattern in p_info.patterns):
                    try:
                        handled = await asyncio.to_thread(p_info.handler, text)
                        if trace_id:
                            await self.decision_logger.record_async(trace_id, "action.executed", {
                                "handler": f"plugin:{p_name}", "intent": intent.name,
                                "success": True, "latency_ms": (time.time() - _t0) * 1000,
                            })
                        return handled
                    except Exception as e:
                        logger.error("Plugin %s failed: %s", p_name, e)
                        if trace_id:
                            await self.decision_logger.record_async(trace_id, "action.executed", {
                                "handler": f"plugin:{p_name}", "intent": intent.name,
                                "success": False, "error": str(e),
                                "latency_ms": (time.time() - _t0) * 1000,
                            })

        return None

    def _build_system_prompt(self) -> str:
        now = datetime.datetime.now()

        # Check if cache is still valid (same hour)
        if (self._system_prompt_cache and
                self._system_prompt_hour == now.hour and
                self._memory_cache is not None):
            return self._system_prompt_cache

        # Build time section (changes hourly)
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        parts = [f"[CURRENT DATE & TIME]\nRight now it is: {time_str}\n"]

        # Build memory section (cached, only rebuild when memory changes)
        if self._memory_cache is None:
            try:
                from memory.memory_manager import format_memory_for_prompt, load_memory
                mem = format_memory_for_prompt(load_memory())
                self._memory_cache = mem if mem else ""
            except Exception:
                self._memory_cache = ""

        if self._memory_cache:
            parts.append(self._memory_cache)

        # Add knowledge graph context (cached for 60s)
        if self.graph_query:
            try:
                now_ts = time.time()
                if self._kg_cache is None or (now_ts - self._kg_cache_time) > 60.0:
                    self._kg_cache = self.graph_query.summarize_for_context(max_entities=20)
                    self._kg_cache_time = now_ts
                if self._kg_cache:
                    parts.append(self._kg_cache)
            except Exception:
                pass

        # Add base prompt (never changes)
        parts.append(self._base_prompt)

        self._system_prompt_cache = "\n".join(parts)
        self._system_prompt_hour = now.hour
        return self._system_prompt_cache

    def invalidate_memory_cache(self):
        """Call this when memory changes to rebuild prompt on next request."""
        self._memory_cache = None
        self._system_prompt_cache = None

    async def _query_llm(self, text: str) -> str:
        if self.semantic_cache.enabled:
            cached = self.semantic_cache.get(text)
            if cached:
                return cached
        try:
            response = await self.router.complete(
                messages=self.context.get_messages(),
                system_prompt=self._build_system_prompt(),
            )
            if self.semantic_cache.enabled and response.text.strip():
                self.semantic_cache.set(text, response.text)
            return response.text
        except Exception as e:
            logger.error("LLM query failed: %s", e)
            return "I'm sorry, I'm having trouble processing that right now."

    def _on_wake_word(self):
        self.dialogue.transition("wake_detected")

    async def process_text_streaming(self, text: str):
        """Streaming pipeline: yields (type, data) tuples for real-time delivery.

        Architecture:
          LLM tokens -> phrase buffer (5 words) -> asyncio.Queue -> TTS worker (background)
          LLM keeps generating while TTS synthesizes previous phrases.
          Uses phrase-level chunking (not full sentences) for faster first audio.

        Yields:
            ("intent", Intent) -- classified intent
            ("text", str) -- incremental text token
            ("tts_chunk", bytes) -- phrase-level WAV audio
            ("done", str) -- final response text
            ("error", str) -- error message
            ("timing", dict) -- latency metrics

        Voice services are lazy-loaded on first use.
        """
        await self._ensure_started()
        await self._ensure_voice_loaded()
        try:
            from pipeline.tts import split_sentences
        except ImportError:
            split_sentences = None

        if not text.strip():
            return

        trace_id = self.decision_logger.begin_task(text, source="process_text_streaming")

        with trace_span("process_text_streaming", text_length=len(text)) as root_span:
            _t_start = time.time()
            self.dialogue.transition("speech_input", {"text": text})
            self.context.add_turn("user", text)

            _t_intent = time.time()
            with trace_span("intent_classify"):
                intent = self.intent_router.classify(text)
            _intent_ms = (time.time() - _t_intent) * 1000
            yield ("intent", intent)
            await self.decision_logger.record_async(trace_id, "intent.classified", {"intent": intent.name, "confidence": intent.confidence, "source": intent.source})

            if root_span:
                root_span.set_attribute("intent.name", intent.name)
                root_span.set_attribute("intent.confidence", round(intent.confidence, 2))
                root_span.set_attribute("intent_ms", round(_intent_ms, 1))

        # Handle memory.store side effects
        if intent.name == "memory.store" and intent.entities.get("fact"):
            fact_text = intent.entities["fact"]
            self.context.add_fact(fact_text)
            if hasattr(self, "vector_memory") and self.vector_memory:
                self.vector_memory.store_vector(fact_text, category="fact")
            self.invalidate_memory_cache()

        if intent.name == "system.clear":
            self.context.clear_history()

        # Fast path: deterministic response
        response = generate_deterministic_response(intent, text, self.personality, self.context.user.facts)

        if response is None:
            # Try action handler -- immediate acknowledgement for actions
            with trace_span("action_or_deterministic", intent=intent.name):
                if intent.name.startswith("action.") and intent.confidence >= 0.9:
                    ack = self._get_acknowledgement(intent, text)
                    if ack:
                        yield ("text", ack)
                        await self.decision_logger.record_async(trace_id, "path.decided", {"path": "action", "streaming": True})
                        with trace_span("action_execute", intent=intent.name):
                            action_result = await self._handle_action(intent, text, trace_id)
                        if action_result:
                            response = ack + "\n" + action_result
                        else:
                            response = ack
                else:
                    await self.decision_logger.record_async(trace_id, "path.decided", {"path": "action", "streaming": True})
                    with trace_span("action_execute", intent=intent.name):
                        response = await self._handle_action(intent, text, trace_id)

        if response is not None:
            # Deterministic or action -- send full response, stream TTS in phrase chunks
            response = _strip_md(response)
            response = self.personality.style_response(response, intent.name)
            self.context.add_turn("assistant", response, intent=intent.name, confidence=intent.confidence)
            await log_conversation_async(self.session_id, "user", text)
            await log_conversation_async(self.session_id, "assistant", response)

            # Ingest into knowledge graph
            if self.graph_query:
                try:
                    self.graph_query.ingest_conversation(text, response, intent.name, intent.entities)
                except Exception as e:
                    logger.debug("Knowledge graph ingestion failed: %s", e)

            self.dialogue.transition("processing_done")
            self.dialogue.transition("reset")
            self.personality.on_interaction_complete(success=True)

            yield ("text", response)

            # Stream TTS in phrase-level chunks
            phrases = _split_phrases(response)
            tts_queue = asyncio.Queue()
            for p in phrases:
                tts_queue.put_nowait(p)
            tts_queue.put_nowait(None)  # sentinel

            tts_result_queue = asyncio.Queue()

            async def _tts_worker():
                while True:
                    phrase = await tts_queue.get()
                    if phrase is None:
                        break
                    try:
                        wav = await self.tts.synthesize(phrase)
                        if wav:
                            tts_result_queue.put_nowait(("tts_chunk", wav))
                    except Exception:
                        pass

            tts_task = asyncio.ensure_future(_tts_worker())
            try:
                while not tts_task.done() or not tts_result_queue.empty():
                    try:
                        item = await asyncio.wait_for(tts_result_queue.get(), timeout=0.1)
                        yield item
                    except TimeoutError:
                        if tts_task.done():
                            break
            finally:
                if not tts_task.done():
                    tts_task.cancel()
                    try:
                        await tts_task
                    except (asyncio.CancelledError, Exception):
                        pass

            total_ms = (time.time() - _t_start) * 1000
            yield ("timing", {"total_ms": round(total_ms, 1), "intent_ms": round(_intent_ms, 1), "tokens": len(response.split()), "source": "deterministic"})
            await self.decision_logger.record_async(trace_id, "task.completed", {"latency_ms": total_ms, "intent": intent.name, "streaming": True, "source": "deterministic"})
            yield ("done", response)
            return

        # Slow path: LLM streaming with decoupled phrase-level TTS
        _t0 = time.time()
        _t_first_token = None
        full_response = ""
        phrase_buf = ""
        token_count = 0

        # Use circuit breaker for LLM calls
        if self.circuit_breaker:
            if not self.circuit_breaker.is_available("llm_query"):
                logger.warning("LLM circuit breaker is open, using fallback")
                full_response = "I'm temporarily unable to process that request. Please try again shortly."
                await self.decision_logger.record_async(trace_id, "task.completed", {"intent": intent.name, "streaming": True, "source": "circuit_breaker_fallback", "status": "fallback"})
                yield ("text", full_response)
                yield ("timing", {"total_ms": 0, "intent_ms": round(_intent_ms, 1), "tokens": 0, "source": "circuit_breaker_fallback"})
                yield ("done", full_response)
                return

        # Semantic cache fast path: skip the LLM for repeated/paraphrased queries.
        if self.semantic_cache.enabled:
            cached_response = self.semantic_cache.get(text)
            if cached_response:
                await self.decision_logger.record_async(trace_id, "path.decided", {"path": "semantic_cache", "streaming": True})
                cached_response = self.personality.style_response(cached_response, intent.name)
                self.context.add_turn("assistant", cached_response, intent=intent.name, confidence=intent.confidence)
                await log_conversation_async(self.session_id, "user", text)
                await log_conversation_async(self.session_id, "assistant", cached_response)
                phrases = _split_phrases(cached_response)
                for p in phrases:
                    yield ("tts_chunk", await self.tts.synthesize(p))
                total_ms = (time.time() - _t_start) * 1000
                await self.decision_logger.record_async(trace_id, "task.completed", {"latency_ms": total_ms, "intent": intent.name, "streaming": True, "source": "semantic_cache"})
                yield ("timing", {"total_ms": round(total_ms, 1), "intent_ms": round(_intent_ms, 1), "tokens": len(cached_response.split()), "source": "semantic_cache"})
                yield ("done", cached_response)
                return

        with trace_span("llm_stream",
                        provider=self.router._last_provider or "unknown",
                        model=self.router._last_model or "unknown") as llm_span:

            await self.decision_logger.record_async(trace_id, "path.decided", {"path": "llm", "streaming": True})

            # ModelManager routing: classify the task and select the best endpoint.
            # Falls back to the ProviderRouter chain if selection is unavailable.
            preferred_provider = None
            if self.model_manager:
                try:
                    from core.model_manager import ModelRequest
                    decision = self.model_manager.select(ModelRequest(text=text))
                    preferred_provider = decision.endpoint.provider
                    if llm_span:
                        llm_span.set_attribute("routed_provider", preferred_provider)
                        llm_span.set_attribute("task_category", decision.category.value)
                except Exception:
                    preferred_provider = None

            # TTS runs in background via asyncio.Queue
            tts_queue = asyncio.Queue()
            tts_done = asyncio.Event()
            tts_result_queue = asyncio.Queue()

            async def _tts_worker():
                """Background TTS: pulls phrases from queue, synthesizes, puts results in side channel."""
                while True:
                    try:
                        phrase = await asyncio.wait_for(tts_queue.get(), timeout=2.0)
                    except TimeoutError:
                        continue
                    if phrase is None:
                        tts_done.set()
                        break
                    try:
                        wav = await self.tts.synthesize(phrase)
                        if wav:
                            tts_result_queue.put_nowait(("tts_chunk", wav))
                    except Exception:
                        pass

            tts_task = asyncio.ensure_future(_tts_worker())

            try:
                async for token in self.router.complete_stream(
                    messages=self.context.get_messages(),
                    system_prompt=self._build_system_prompt(),
                    preferred_provider=preferred_provider,
                ):
                    if _t_first_token is None:
                        _t_first_token = time.time()

                    full_response += token
                    token_count += 1
                    yield ("text", token)

                    while not tts_result_queue.empty():
                        yield tts_result_queue.get_nowait()

                    phrase_buf += token
                    phrase_buf = _flush_phrases(phrase_buf, tts_queue)

                # Flush remaining text
                remaining = phrase_buf.strip()
                if remaining:
                    tts_queue.put_nowait(remaining)

                tts_queue.put_nowait(None)

                try:
                    await asyncio.wait_for(tts_done.wait(), timeout=10.0)
                except TimeoutError:
                    pass

                while not tts_result_queue.empty():
                    yield tts_result_queue.get_nowait()

                # Record success for the winning provider in ModelManager
                if self.model_manager:
                    try:
                        self.model_manager.record_success(
                            self.router._last_provider or preferred_provider or "unknown",
                            self.router._last_model or "unknown",
                            (time.time() - _t0) * 1000,
                            token_count,
                        )
                    except Exception:
                        pass

            except Exception as e:
                logger.error("LLM streaming failed: %s", e)
                full_response = full_response or "I'm having trouble processing that right now."
                tts_queue.put_nowait(None)
                await self.decision_logger.record_async(trace_id, "task.failed", {"error": str(e), "stage": "llm_stream", "streaming": True})
                if self.model_manager:
                    try:
                        self.model_manager.record_failure(
                            self.router._last_provider or preferred_provider or "unknown",
                            self.router._last_model or "unknown",
                            str(e),
                        )
                    except Exception:
                        pass
                yield ("error", str(e))

            finally:
                if not tts_task.done():
                    tts_task.cancel()
                    try:
                        await tts_task
                    except (asyncio.CancelledError, Exception):
                        pass

            llm_ms = (time.time() - _t0) * 1000
            ttft_ms = ((_t_first_token or time.time()) - _t_start) * 1000

            if llm_span:
                llm_span.set_attribute("ttft_ms", round(ttft_ms, 1))
                llm_span.set_attribute("llm_ms", round(llm_ms, 1))
                llm_span.set_attribute("token_count", token_count)
                if llm_ms > 0:
                    llm_span.set_attribute("tokens_per_sec", round(token_count / (llm_ms / 1000), 1))

            self.diagnostics.record_request(
                provider=self.router._last_provider or "unknown",
                model=self.router._last_model or "unknown",
                success=True, latency_ms=llm_ms,
                tokens_in=len(text.split()), tokens_out=token_count,
            )

            full_response = _strip_md(full_response)
            full_response = self.personality.style_response(full_response, intent.name)
            self.context.add_turn("assistant", full_response, intent=intent.name, confidence=intent.confidence)
            if self.semantic_cache.enabled and full_response.strip():
                self.semantic_cache.set(text, full_response)
            await log_conversation_async(self.session_id, "user", text)
            await log_conversation_async(self.session_id, "assistant", full_response)

            # Ingest into knowledge graph
            if self.graph_query:
                try:
                    self.graph_query.ingest_conversation(text, full_response, intent.name, intent.entities)
                except Exception as e:
                    logger.debug("Knowledge graph ingestion failed: %s", e)

            self.dialogue.transition("processing_done")
            self.dialogue.transition("reset")
            self.personality.on_interaction_complete(success=True)

            total_ms = (time.time() - _t_start) * 1000
            timing = {
                "ttft_ms": round(ttft_ms, 1),
                "llm_ms": round(llm_ms, 1),
                "intent_ms": round(_intent_ms, 1),
                "total_ms": round(total_ms, 1),
                "tokens": token_count,
                "tokens_per_sec": round(token_count / (llm_ms / 1000), 1) if llm_ms > 0 else 0,
                "provider": self.router._last_provider or "unknown",
                "model": self.router._last_model or "unknown",
            }
            logger.info("Streaming done: %d tokens, TTFT=%.0fms, total=%.0fms", token_count, ttft_ms, total_ms)

            # Record streaming metrics
            if self.perf_analyzer_engine:
                try:
                    self.perf_analyzer_engine.record_metric("streaming_total_ms", total_ms)
                    self.perf_analyzer_engine.record_metric("streaming_ttft_ms", ttft_ms)
                    self.perf_analyzer_engine.record_metric("streaming_tokens", token_count)
                except Exception:
                    pass
            if self.perf_cache:
                try:
                    self.perf_cache.put(f"response_{hash(text) % 10000}", full_response, ttl_seconds=600)
                except Exception:
                    pass
            # Record model outcome
            if self.model_router:
                try:
                    self.model_router.record_outcome(
                        self.router._last_provider or "unknown",
                        self.router._last_model or "unknown",
                        llm_ms, True, token_count
                    )
                except Exception:
                    pass

            if root_span:
                root_span.set_attribute("total_ms", round(total_ms, 1))
                root_span.set_attribute("provider", timing["provider"])
                root_span.set_attribute("model", timing["model"])

            await self.decision_logger.record_async(trace_id, "llm.completed", {
                "latency_ms": llm_ms, "tokens_out": token_count,
                "provider": timing["provider"], "model": timing["model"],
                "ttft_ms": ttft_ms,
            })
            await self.decision_logger.record_async(trace_id, "task.completed", {
                "latency_ms": total_ms, "intent": intent.name, "streaming": True,
                "source": "llm", "tokens": token_count,
            })
            yield ("timing", timing)
            yield ("done", full_response)

    def _get_acknowledgement(self, intent, text: str) -> str | None:
        """Immediate acknowledgement for high-confidence action intents."""
        n = intent.name
        if n == "action.open":
            app = intent.entities.get("app", "that")
            return f"Opening {app}, sir."
        if n == "action.search":
            return "Searching now, sir."
        if n == "action.desktop_control":
            return "Adjusting settings, sir."
        return None

    async def speak(self, text: str):
        if text:
            await self._ensure_voice_loaded()
            await self.tts.synthesize(text)
            # Trigger precache after first successful TTS (one-time)
            if not self._precache_done:
                self._precache_done = True
                async def _bg_precache():
                    try:
                        await self.tts.precache_deterministic()
                    except Exception:
                        pass
                asyncio.ensure_future(_bg_precache())

    def get_status(self) -> dict:
        status = {
            "session_id": self.session_id,
            "state": self.dialogue.state.name,
            "providers": self.router.status,
            "memory_stats": self.memory.get_stats(),
            "history_length": len(self.context.history),
            "personality_mood": self.personality.state.mood.value,
            "interaction_count": self.personality.state.interaction_count,
            "diagnostics": self.diagnostics.get_provider_summary(),
            "uptime_s": self.diagnostics.get_uptime(),
        }
        if self.knowledge_graph:
            try:
                status["knowledge_graph"] = self.knowledge_graph.get_graph_stats()
            except Exception:
                pass
        if self.security:
            try:
                status["security"] = self.security.get_status()
            except Exception:
                pass
        # ── New subsystem status ──────────────────────────────────────────
        if self.profiler:
            try:
                status["profiler"] = self.profiler.get_all_profiles()
            except Exception:
                pass
        if self.perf_cache:
            try:
                status["cache"] = self.perf_cache.get_stats()
            except Exception:
                pass
        if self.model_router:
            try:
                status["model_router"] = self.model_router.get_model_stats()
            except Exception:
                pass
        if self.circuit_breaker:
            try:
                status["circuit_breakers"] = self.circuit_breaker.get_all_states()
            except Exception:
                pass
        if self.health_monitor:
            try:
                status["health"] = self.health_monitor.get_health()
            except Exception:
                pass
        if self.trust_scorer:
            try:
                status["trust_score"] = self.trust_scorer.get_overall_trust()
            except Exception:
                pass
        if self.process_optimizer:
            try:
                status["process"] = self.process_optimizer.get_process_info()
            except Exception:
                pass
        if self.power_manager:
            try:
                status["power"] = self.power_manager.get_power_state()
            except Exception:
                pass
        # ── Part 90: Hyper-Optimization status ───────────────────────────
        if self.hyp_opt_manager:
            try:
                status["hyper_opt"] = self.hyp_opt_manager.get_optimization_report()
            except Exception:
                pass
        if self.hyp_dashboard:
            try:
                status["opt_dashboard"] = self.hyp_dashboard.get_status_summary()
            except Exception:
                pass
        # ── Part 91: Systems status ─────────────────────────────────────
        if self.event_bus:
            try:
                status["event_bus"] = self.event_bus.get_stats()
            except Exception:
                pass
        if self.perf_governor:
            try:
                status["perf_governor"] = self.perf_governor.get_report()
            except Exception:
                pass
        if self.multi_level_cache:
            try:
                status["cache_system"] = self.multi_level_cache.get_stats()
            except Exception:
                pass
        if self.benchmark:
            try:
                status["benchmarks"] = self.benchmark.get_stats()
            except Exception:
                pass
        if self.dyn_model_router:
            try:
                status["model_router_dyn"] = self.dyn_model_router.get_stats()
            except Exception:
                pass
        return status

    def shutdown(self):
        logger.info("Shutting down JARVIS MK-X")
        self.context.flush()
        self.memory.flush_conversations()
        self.memory.close()
        if self.knowledge_graph:
            try:
                self.knowledge_graph.close()
            except Exception:
                pass
        if self.security:
            try:
                self.security.shutdown()
            except Exception:
                pass
        # ── Shutdown new subsystems ───────────────────────────────────────
        if self.health_monitor:
            try:
                self.health_monitor.stop()
            except Exception:
                pass
        if self.prefetch_engine:
            try:
                self.prefetch_engine.invalidate("*")
            except Exception:
                pass
        if self.process_optimizer:
            try:
                self.process_optimizer.defragment_memory()
            except Exception:
                pass
        # ── Shutdown Part 90 subsystems ──────────────────────────────────
        if self.hyp_resource_pred:
            try:
                self.hyp_resource_pred.stop_monitoring()
            except Exception:
                pass
        # ── Shutdown Part 91 + external + SE factory ─────────────────────
        if self.event_bus:
            try:
                self.event_bus.emit("system.shutdown", {}, source="jarvis")
                self.event_bus.shutdown()
            except Exception:
                pass
        if self.adaptive_scheduler:
            try:
                self.adaptive_scheduler.stop()
            except Exception:
                pass
        logger.info("Shutdown complete")
