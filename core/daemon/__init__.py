"""JARVIS MK-X Daemon - Main autonomous engineering agent daemon.

Provides the core daemon process that coordinates LLM interactions,
skill execution, permission gating, and metric tracking.

ModelGateway (P0-2) — The canonical model selection authority. All model
routing, draft/verification selection, and capability-aware model goes
through this gateway, NOT via direct `loop._preferred_model` manipulation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

# Import event bus system (P0-4 architecture invariant)
from core.daemon.events import _emit, BusEvent, SCHEMA_VERSION, make_session_id, make_trace_id

# Model Gateway (P0-2) — single model selection authority
from core.model_gateway import ModelGateway

# Import prefix cache plugin (P0 optimization)
from core.daemon.plugins.prefix_cache import get_prefix_cache, PrefixCachePlugin
from core.tool_execution_service import ToolExecutionService

# Import skill registry (P1 optimization - Cordis microkernel adaptation).
# Backed by the manifest-driven skills/registry (skills/manifests/*.json).
from skills.registry import SkillRegistry, SkillMetadata, SkillContract

# Import configuration
from core.config import Config, ModelCatalog

# Export key symbols
__all__ = [
    "JARVISDaemon",
    "get_prefix_cache",
    "reset_prefix_cache",
    "SkillRegistry",
    "SkillMetadata",
    "SkillContract",
    "BusEvent",
    "SCHEMA_VERSION",
    "make_session_id",
    "make_trace_id",
    "ModelGateway",
    "HarnessSelector",
]


class JARVISDaemon:
    """JARVIS MK-X Autonomous Engineering Agent Daemon.

    Core daemon process that coordinates:
    - LLM API interactions with prefix cache optimization (P0)
    - Skill/sandbox execution with permission gating (P1)
    - Metric tracking and reporting
    - Event bus with session_id propagation (P0-4 invariant)
    - Plugin-based architecture for modular extensions
    """

    def __init__(self, config: Optional[Config] = None):
        # Initialize config
        self.config = config or Config()

        # Initialize session ID for this daemon instance — every
        # BusEvent emitted during this daemon's lifetime carries it,
        # enabling reliable event-to-session association across the event bus.
        self._session_id: str = make_session_id()

        # Initialize prefix cache plugin (P0 optimization)
        self.prefix_cache: PrefixCachePlugin = get_prefix_cache()

        # Initialize skill registry (P1 optimization)
        skill_dirs: List[str] = getattr(
            self.config, "skill_directories", ["core/skills", "plugins/skills"]
        )
        self.skill_registry: SkillRegistry = SkillRegistry(skill_dirs=skill_dirs)
        self._init_skills()

        # Initialize metrics tracking
        self.metrics: Dict[str, Any] = {
            "prefix_cache_savings": 0,
            "prefix_cache_hits": 0,
            "prefix_cache_misses": 0,
            "skills_loaded": len(self.skill_registry.skills),
            "permission_validations": 0,
            "sandbox_violations": 0,
        }

        # Initialize event log — records every BusEvent emitted during
        # this daemon's lifetime, enabling session association and debugging.
        self._event_log: List[BusEvent] = []

        # Initialize session affinity TTL tracking (P0-6)
        # Maps session_id → (model_key, expires_at) with thread-safe lock
        self._session_affinity: Dict[str, tuple[str, float]] = {}
        self._session_affinity_lock = threading.Lock()

        # Initialize ToolExecutionService — the single boundary for all tool execution
        self.tool_execution_service: ToolExecutionService = ToolExecutionService(
            skill_registry=self.skill_registry,
            skill_dirs=skill_dirs,
            max_memory_mb=getattr(self.config, "max_memory_mb", 512),
            max_timeout_seconds=getattr(self.config, "max_timeout_seconds", 120),
        )

        # Initialize ModelGateway (P0-2) — the canonical model selection authority.
        # All model routing, draft/verification selection, and capability-aware
        # model selection goes through this gateway, NOT via direct
        # `loop._preferred_model` or similar private state manipulation.
        self.model_gateway: ModelGateway = ModelGateway(
            config=self.config,
            skill_registry=self.skill_registry,
        )

        # Initialize HarnessSelector (P0-3) — the canonical harness selection
        # authority. All harness selection should go through this selector,
        # NOT via direct CLI manipulation of loop state or private attributes.
        # The Harness ≠ Model invariant is enforced: harness and model are
        # independent axes; this selector manages only harness state.
        self.harness_selector: HarnessSelector = HarnessSelector(
            config=self.config,
        )

        # Log initialization
        logger = logging.getLogger("jarvis.daemon")
        logger.info(
            "JARVIS Daemon initialized",
            extra={
                "prefix_cache_entries": len(self.prefix_cache.cache),
                "skills_loaded": len(self.skill_registry.skills),
                "model_name": getattr(self.config, "model_name", "gemini-2.5-pro"),
                "session_id": self._session_id,
            },
        )

    def _init_skills(self) -> None:
        """Initialize and load skills from configured directories."""
        self.skill_registry.discover_and_load()
        # Cache tool schemas from skills for prefix cache usage
        for name, contract in self.skill_registry.skills.items():
            # Tool schemas will be populated when skills define them
            pass

    # -----------------------------------------------------------------
    # Session ID accessor — every BusEvent emitted from this daemon
    # carries the same session_id, enabling reliable event-to-session
    # association across the event bus.
    # -----------------------------------------------------------------

    @property
    def session_id(self) -> str:
        """Return the daemon's current session identifier."""
        return self._session_id

    # -----------------------------------------------------------------
    # Session affinity TTL (P0-6)
    # -----------------------------------------------------------------

    def update_session_affinity(
        self, model_key: str, ttl_seconds: int = 3600
    ) -> None:
        """Update session affinity with model key and TTL expiration.

        Tracks which model key a session is affiliated with, expiring
        after ttl_seconds so that sessions don't permanently bind to
        a model (enables model rotation/fallback).

        Parameters
        ----------
        model_key:
            The model key (e.g. "gemini-2.5-pro", "deepseek-coder-v2") to
            associate with this session.
        ttl_seconds:
            Time-to-live in seconds before this affinity entry expires.
            Default: 3600 (1 hour).
        """
        now = asyncio.get_event_loop().time()
        expires_at = now + ttl_seconds

        with self._session_affinity_lock:
            self._session_affinity[self._session_id] = (model_key, expires_at)

        # Optional: cleanup expired entries (could be called periodically)
        self._cleanup_session_affinity()

    def _cleanup_session_affinity(self) -> None:
        """Remove expired session affinity entries."""
        now = asyncio.get_event_loop().time()

        with self._session_affinity_lock:
            expired_keys = [
                session_id
                for session_id, (_, expires_at) in self._session_affinity.items()
                if expires_at <= now
            ]
            for session_id in expired_keys:
                del self._session_affinity[session_id]

    def get_session_affinity(
        self, session_id: Optional[str] = None
    ) -> Optional[tuple[str, float]]:
        """Get session affinity info for a given session.

        Returns (model_key, expires_at) or None if not found/expired.

        Parameters
        ----------
        session_id:
            Session ID to look up. Defaults to this daemon's session.

        Returns
        -------
        Optional[tuple[str, float]]
            (model_key, expires_at_unix_time) or None.
        """
        target_id = session_id or self._session_id

        with self._session_affinity_lock:
            entry = self._session_affinity.get(target_id)
            if entry is None:
                return None

            model_key, expires_at = entry

            # Check if expired
            now = asyncio.get_event_loop().time()
            if expires_at <= now:
                # Remove expired entry
                with self._session_affinity_lock:
                    if target_id in self._session_affinity:
                        del self._session_affinity[target_id]
                return None

            return (model_key, expires_at)

    # -----------------------------------------------------------------
    # Async chat handling
    # -----------------------------------------------------------------

    async def handle_chat(self, user_message: str, context: Optional[Dict] = None) -> str:
        """Handle an incoming chat message with full optimization pipeline.

        Pipeline order:
        1. Emit intent.classified event with session_id
        2. Prefix cache lookup for system prompts, few-shot examples, tools
        3. Skill identification and permission validation
        4. Tool execution through single boundary (ToolExecutionService)
        5. Emit inference.completed event with session_id
        6. Response formatting and metric tracking
        """
        context = context or {}
        start_time = asyncio.get_event_loop().time()
        trace_id = make_trace_id()

        # --- Step 1: Emit intent.classified ---
        self._emit(
            "intent.classified",
            {"user_message": user_message[:200] if user_message else ""},
            session_id=self._session_id,
            trace_id=trace_id,
        )

        # Step 1: Cache system prompt, few-shot examples, tool definitions
        self._cache_prompt_components(user_message, context)

        # Step 2: Identify needed skills and validate permissions
        needed_skills = self._identify_needed_skills(user_message)
        permission_result = self._validate_skill_permissions(needed_skills)

        # Step 3: Execute skills through the single boundary
        execution_results = await self._execute_skills(
            needed_skills, user_message, context
        )

        # Step 4: Emit inference.completed event
        self._emit(
            "inference.completed",
            {
                "response_length": len(
                    self._build_response(user_message, execution_results, permission_result)
                ),
                "skills_executed": len(execution_results),
            },
            session_id=self._session_id,
            trace_id=trace_id,
        )

        # Step 5: Build final response
        response = self._build_response(
            user_message, execution_results, permission_result
        )

        # Step 6: Track metrics
        self._track_metrics(
            user_message, execution_results, permission_result, start_time
        )

        return response

    # -----------------------------------------------------------------
    # Event emission — requires session_id (P0-4 invariant)
    # -----------------------------------------------------------------

    def _emit(self, name: str, payload: Dict[str, Any], **kwargs: Any) -> None:
        """Emit a BusEvent with the daemon's session_id.

        This is the canonical event emission point. All meaningful
        actions through the daemon should pass through this method so
        that the event bus always carries a non-empty session_id.

        Raises
        ------
        ValueError
            If called without a session_id (should never happen in
            production since _session_id is set at construction).
        """
        if not self._session_id:
            raise ValueError("_emit called before daemon session_id was set")

        event: BusEvent = {
            "name": name,
            "payload": payload or {},
            "source": "jarvis.daemon",
            "session_id": self._session_id,
            "trace_id": kwargs.get("trace_id", make_trace_id()),
            "timestamp": asyncio.get_event_loop().time(),
        }
        # Publish — in a full integration this would hit the shared
        # EventBus; here we simply record for the test-harness to
        # introspect.
        self._event_log.append(event)

    # -----------------------------------------------------------------
    # Prompt caching (P0 optimization)
    # -----------------------------------------------------------------

    def _cache_prompt_components(self, user_message: str, context: Dict) -> None:
        """Cache system prompt, few-shot examples, and tool definitions."""
        # 1. Cache system prompt
        system_prompt = getattr(self.config, "system_prompt", "") or ""
        if system_prompt:
            self.prefix_cache.cache_get_set(
                system_prompt, prompt_type="system"
            )

        # 2. Cache few-shot examples (if configured)
        few_shot = getattr(self.config, "few_shot_examples", "") or ""
        if few_shot:
            self.prefix_cache.cache_get_set(
                few_shot, prompt_type="few_shot"
            )

        # 3. Cache tool definitions from skill registry
        tool_defs = self.skill_registry.get_tool_schemas()
        if tool_defs:
            self.prefix_cache.cache_get_set(
                tool_defs, prompt_type="tools"
            )

    # -----------------------------------------------------------------
    # Skill identification & permission validation
    # -----------------------------------------------------------------

    def _identify_needed_skills(self, user_message: str) -> List[str]:
        """Identify which skills are needed for the user message."""
        needed: List[str] = []

        message_lower = user_message.lower()

        # Check against known skill categories
        skill_keywords = {
            "browser": ["browser", "open", "navigate", "visit", "website"],
            "filesystem": ["read", "write", "file", "create", "delete", "path"],
            "search": ["search", "find", "look up", "research"],
            "analysis": ["analyze", "examine", "inspect", "review"],
        }

        for skill_name, keywords in skill_keywords.items():
            if any(kw in message_lower for kw in keywords):
                if self.skill_registry.get_skill(skill_name):
                    needed.append(skill_name)

        return needed

    def _validate_skill_permissions(
        self, needed_skills: List[str]
    ) -> Dict[str, Any]:
        """Validate permissions for all needed skills.

        Returns dict with 'approved' boolean, 'violations' list,
        and 'warnings' list.
        """
        self.metrics["permission_validations"] += len(needed_skills)

        result: Dict[str, Any] = {
            "approved": True,
            "violations": [],
            "warnings": [],
        }

        for skill_name in needed_skills:
            contract = self.skill_registry.get_skill(skill_name)
            if contract is None:
                result["approved"] = False
                result["violations"].append(f"Skill {skill_name} not found")
                continue

            # Determine requested tools for this skill (simplified)
            requested_tools = self._extract_tool_names_for_skill(skill_name)

            valid, invalid_or_warnings = self.skill_registry.validate_tools(
                skill_name, requested_tools
            )

            self.metrics["permission_validations"] += 1

            if not valid and contract.metadata.enforce:
                result["approved"] = False
                result["violations"].extend(invalid_or_warnings)
            elif invalid_or_warnings:
                result["warnings"].extend(invalid_or_warnings)

        return result

    def _extract_tool_names_for_skill(self, skill_name: str) -> List[str]:
        """Extract tool names associated with a skill."""
        mappings = {
            "browser": ["browser.open", "browser.navigate", "browser.snapshot"],
            "filesystem": ["filesystem.read", "filesystem.write", "filesystem.delete"],
            "search": ["repo.search", "web.search"],
            "analysis": [],
        }
        return mappings.get(skill_name, [])

    # -----------------------------------------------------------------
    # Skill execution through single boundary (P0-1)
    # -----------------------------------------------------------------

    async def _execute_skills(
        self, needed_skills: List[str], user_message: str, context: Dict
    ) -> List[Dict[str, Any]]:
        """Execute needed skills within sandbox limits.

        All tool execution passes through ToolExecutionService — the
        single boundary that enforces permission gating, sandbox limits,
        and event bus integration.
        """
        results: List[Dict[str, Any]] = []

        for skill_name in needed_skills:
            contract = self.skill_registry.get_skill(skill_name)
            if contract is None or not contract.metadata.enabled:
                results.append(
                    {"skill": skill_name, "error": "Skill not available or disabled"}
                )
                continue

            # Extract args (simplified - would use LLM function calling in production)
            args = self._extract_skill_args(skill_name, user_message)

            # Execute through the single boundary (ToolExecutionService)
            try:
                result = await self.tool_execution_service.execute_tool(
                    tool_name=skill_name,
                    tool_call_id=f"call_{skill_name}_{int(time.time())}",
                    args=args,
                    session_id=self._session_id,
                    timeout=contract.metadata.timeout_seconds,
                )
                results.append(
                    {"skill": skill_name, "result": result.output, "error": None}
                )
            except ToolExecutionError as e:
                results.append(
                    {"skill": skill_name, "error": e.message, "tool_call_id": e.tool_call_id}
                )
            except Exception as e:
                results.append({"skill": skill_name, "error": str(e), "error_type": type(e).__name__})

        return results

    def _extract_skill_args(self, skill_name: str, user_message: str) -> Dict[str, Any]:
        """Extract arguments for a skill from the user message."""
        args: Dict[str, Any] = {}

        if skill_name == "browser":
            import re
            url_match = re.search(r"https?://\S+", user_message)
            if url_match:
                args["url"] = url_match.group(0)
            else:
                args["url"] = "https://example.com"

        elif skill_name == "filesystem":
            import re
            path_match = re.search(r"[/\w\d.-]+\.\w+", user_message)
            if path_match:
                args["path"] = path_match.group(0)
            else:
                args["path"] = "/tmp/jarvis_temp.txt"

        elif skill_name == "search":
            args["query"] = user_message

        return args

    # -----------------------------------------------------------------
    # Response building
    # -----------------------------------------------------------------

    def _build_response(
        self,
        user_message: str,
        execution_results: List[Dict[str, Any]],
        permission_result: Dict[str, Any],
    ) -> str:
        """Build the final response string."""
        parts: List[str] = []

        # Add user message acknowledgment
        parts.append(f"> User: {user_message}")

        # Check permissions
        if not permission_result["approved"]:
            violation_str = "; ".join(permission_result["violations"])
            parts.append(
                f"⚠ Permission denied: {violation_str}. "
                f"Allowed tools can be configured in skill frontmatter."
            )
            return "\n".join(parts)

        # Add skill execution results
        for exec_result in execution_results:
            skill_name = exec_result.get("skill", "unknown")
            result = exec_result.get("result")
            error = exec_result.get("error")

            if error:
                parts.append(f"⚠ {skill_name}: {error}")
            elif result:
                parts.append(f"✓ {skill_name}: {str(result)[:200]}")

        # Default assistant response if no skills triggered
        if not any("✓" in p or "⚠" in p for p in parts):
            parts.append(
                "I've analyzed your request. No specific skills were needed, "
                "but I'm here to help with analysis, research, or tool execution."
            )

        return "\n".join(parts)

    # -----------------------------------------------------------------
    # Metric tracking
    # -----------------------------------------------------------------

    def _track_metrics(
        self,
        user_message: str,
        execution_results: List[Dict[str, Any]],
        permission_result: Dict[str, Any],
        start_time: float,
    ) -> None:
        """Track daemon metrics for the executed request."""
        elapsed = asyncio.get_event_loop().time() - start_time

        # Track prefix cache stats
        stats = self.prefix_cache.get_stats()
        self.metrics["prefix_cache_hits"] = stats["hit_count"]
        self.metrics["prefix_cache_misses"] = stats["miss_count"]

        # Track permission validations
        self.metrics["permission_validations"] = (
            self.metrics.get("permission_validations", 0) + 1
        )

        # Track sandbox violations
        violations = sum(
            1 for r in execution_results if "error" in r
        )
        self.metrics["sandbox_violations"] = (
            self.metrics.get("sandbox_violations", 0) + violations
        )

    # -----------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return current daemon status and metrics."""
        return {
            "model": getattr(self.config, "model_name", "gemini-2.5-pro"),
            "session_id": self._session_id,
            "prefix_cache": self.prefix_cache.get_stats(),
            "skills_loaded": len(self.skill_registry.skills),
            "metrics": self.metrics.copy(),
            "event_log_entries": len(self._event_log),
        }


# -------------------------------------------------------------------
# Singleton daemon instance
# -----------------------------------------------------------------

_daemon_instance: Optional[JARVISDaemon] = None


def get_daemon(config: Optional[Config] = None) -> JARVISDaemon:
    """Get the singleton daemon instance."""
    global _daemon_instance
    if _daemon_instance is None:
        _daemon_instance = JARVISDaemon(config=config)
    return _daemon_instance


def reset_daemon() -> None:
    """Reset the singleton daemon instance (for testing)."""
    global _daemon_instance
    _daemon_instance = None
    reset_prefix_cache()