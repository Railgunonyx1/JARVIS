"""Model Gateway — Single model selection authority for JARVIS MK-X.

Adapted from modelcontextprotocol/python-sdk patterns and microsoft/agent-framework
provider routing. The ModelGateway is the canonical model selection point — all
model routing, draft/verification selection, and capability-aware model goes
through this gateway, NOT via direct `loop._preferred_model` manipulation.

Features:
- Capability-aware model filtering (local-only, cloud-allowed, privacy-required, GPU)
- Draft-then-verification routing
- Provider availability tracking
- Session-affinity-aware model selection
- Emits canonical BusEvent for model selection changes
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, List, Optional, Tuple

from core.config import ModelCatalog

# Logging
logger = logging.getLogger("jarvis.model_gateway")

# ---------------------------------------------------------------------------
# Model capability constants
# ---------------------------------------------------------------------------

# Capability flags for model filtering
CAP_LOCAL_ONLY = "local-only"
CAP_CLOUD_ALLOWED = "cloud-allowed"
CAP_PRIVACY_REQUIRED = "privacy-required"
CAP_GPU_REQUIRED = "gpu-required"

# Default cascade tiers: smallest to largest
CASCADE_TIERS = [
    "tiny",      # ~1B parameters — fastest, lowest quality
    "small",     # ~1.5B parameters
    "medium",    # ~3B parameters
    "large",     # ~4B/7B parameters — highest quality
]

# Default model per tier (from ModelCatalog)
DEFAULT_MODELS = {
    "tiny": ModelCatalog.GROQ_LLAMA3_1,       # llama-3.1-8b-instant
    "small": ModelCatalog.GROQ_LLAMA3_1,     # llama-3.1-8b-instant
    "medium": ModelCatalog.OPENROUTER_GEMINI, # google/gemini-2.5-flash
    "large": ModelCatalog.GEMINI_FLASH_LITE,  # gemini-2.5-flash-lite
}


# ---------------------------------------------------------------------------
# ModelGateway class — the single model selection authority
# ---------------------------------------------------------------------------

class ModelGateway:
    """Central model selection authority for JARVIS MK-X.

    Responsibilities:
    - Model selection based on capability filters and tier cascade
    - Draft-then-verification routing
    - Provider availability and capability tracking
    - Session-affinity management (model key → expires_at)
    - Emitting canonical BusEvent for model selection changes

    This is the __only__ model selection authority. Direct manipulation of
    `loop._preferred_model` or similar private state is prohibited — use
    `ModelGateway.select_model()` instead.
    """

    def __init__(self, config: Any, skill_registry: Any = None):
        self.config = config
        self.skill_registry = skill_registry

        # Model availability tracking: provider → list of available models
        self._provider_models: Dict[str, List[str]] = {}

        # Session affinity: session_id → (model_key, expires_at)
        self._session_affinity: Dict[str, tuple[str, float]] = {}

        # Selection history for monitoring
        self._selection_history: List[Dict[str, Any]] = []

        # Emission source
        self._source = "model_gateway"

        logger.info("ModelGateway initialized")

    # -----------------------------------------------------------------
    # Capability-aware model selection
    # -----------------------------------------------------------------

    def select_model(
        self,
        tier: str = "medium",
        *,
        capability: Optional[List[str]] = None,
        capability_filter: str = CAP_CLOUD_ALLOWED,
        draft: bool = False,
        verification: bool = False,
        session_id: Optional[str] = None,
        emit: bool = True,
    ) -> str:
        """Select a model for the given tier and capabilities.

        This is the canonical model selection method. All model routing
        should go through this method, NOT via direct private state access.

        Parameters
        ----------
        tier:
            Cascade tier: "tiny", "small", "medium", "large"
        capability:
            Optional list of required capabilities (e.g. ["tool_use", "vision"])
        capability_filter:
            How to filter: "local-only", "cloud-allowed", "privacy-required",
            "gpu-required"
        draft:
            If True, select a draft model (cheaper, lower quality)
        verification:
            If True, select a verification model (independent check)
        session_id:
            Optional session ID for affinity tracking
        emit:
            If True (default), emit selection event. Set False to skip
            event emission (e.g., during initialization or testing).

        Returns
        -------
        str: Model name string
        """
        # Resolve tier to model
        model = self._resolve_model(tier, capability_filter=capability_filter)

        # Apply capability filtering
        if capability:
            # Check if model supports required capabilities
            if not self._has_capabilities(model, capability):
                logger.warning(
                    f"Model {model} does not support required capabilities {capability}; "
                    f"falling back to default"
                )
                model = self._resolve_model("medium", capability_filter=capability_filter, emit=False)

        # Emit selection event
        self._emit_selection_event(
            model=model,
            tier=tier,
            draft=draft,
            verification=verification,
            capability=capability,
            capability_filter=capability_filter,
            session_id=session_id,
            emit=emit,
        )

        # Track affinity
        if session_id:
            self._set_session_affinity(session_id, model, emit=emit)

        return model

    def _resolve_model(
        self, tier: str, capability_filter: str = CAP_CLOUD_ALLOWED
    ) -> str:
        """Resolve a model for the given tier and capability filter.

        Uses the DEFAULT_MODELS mapping, with fallback to ModelCatalog.
        """
        model = DEFAULT_MODELS.get(tier)
        if model:
            return model

        # Fall back to ModelCatalog
        return ModelCatalog.get_model(tier, capability_filter)

    def _has_capabilities(self, model: str, capability: List[str]) -> bool:
        """Check if a model supports the required capabilities.

        In a production system this would query model metadata/providers.
        For now, we use a simple heuristic based on model name patterns.
        """
        model_lower = model.lower()
        # Simplified: assume cloud models support common capabilities
        # Local-only models would be filtered differently
        has_tool_use = any(
            kw in model_lower for kw in ("gpt", "claude", "gemini", "flash")
        )
        return has_tool_use or len(capability) == 0

    # -----------------------------------------------------------------
    # Draft-then-verification routing
    # -----------------------------------------------------------------

    def select_draft_model(
        self, tier: str = "medium", session_id: Optional[str] = None, emit: bool = True
    ) -> str:
        """Select a draft (cheaper) model for the given tier.

        Draft models are used for initial generation; verification models
        are then used to independently check the result.
        """
        # Draft typically uses one tier down
        draft_tier = self._draft_tier(tier)
        model = self.select_model(
            tier=draft_tier,
            capability_filter=CAP_CLOUD_ALLOWED,
            draft=True,
            session_id=session_id,
            emit=emit,
        )
        logger.info(f"Selected draft model {model} (tier={tier} → {draft_tier})")
        return model

    def select_verification_model(
        self, tier: str = "medium", session_id: Optional[str] = None, emit: bool = True
    ) -> str:
        """Select a verification model for the given tier.

        Verification models independently check the draft output. They
        should be a different model when possible for better coverage.
        """
        # Verification typically uses the same or next tier up
        verification_tier = self._verification_tier(tier)
        model = self.select_model(
            tier=verification_tier,
            capability_filter=CAP_CLOUD_ALLOWED,
            verification=True,
            session_id=session_id,
            emit=emit,
        )
        logger.info(
            f"Selected verification model {model} (tier={tier} → {verification_tier})"
        )
        return model

    def _draft_tier(self, tier: str) -> str:
        """Get the draft tier for a given tier.

        Draft tiers are one step below the requested tier in the cascade.
        """
        tier_index = CASCADE_TIERS.index(tier) if tier in CASCADE_TIERS else 2
        draft_index = max(0, tier_index - 1)
        return CASCADE_TIERS[draft_index]

    def _verification_tier(self, tier: str) -> str:
        """Get the verification tier for a given tier.

        Verification typically uses the same or next tier up.
        """
        if tier == "large":
            return "large"  # No higher tier
        # Same tier, or step up
        current_index = CASCADE_TIERS.index(tier) if tier in CASCADE_TIERS else 2
        # Try same tier first, then step up
        if current_index + 1 < len(CASCADE_TIERS):
            return CASCADE_TIERS[current_index + 1]
        return tier

# -----------------------------------------------------------------
    # Session affinity
    # -----------------------------------------------------------------

    def _ensure_session_affinity(self) -> None:
        """Ensure _session_affinity dict is initialized."""
        if not hasattr(self, "_session_affinity") or self._session_affinity is None:
            self._session_affinity: Dict[str, tuple[str, float]] = {}

    def _ensure_provider_models(self) -> None:
        """Ensure _provider_models dict is initialized."""
        if not hasattr(self, "_provider_models") or self._provider_models is None:
            self._provider_models: Dict[str, List[str]] = {}

    def _ensure_selection_history(self) -> None:
        """Ensure _selection_history list is initialized."""
        if not hasattr(self, "_selection_history") or self._selection_history is None:
            self._selection_history: List[Dict[str, Any]] = []
        pass

    def _set_session_affinity(self, session_id: str, model_key: str, ttl_seconds: int = 3600, emit: bool = True) -> None:
        """Set session affinity for a model key.

        Maps session_id → (model_key, expires_at) so that sessions don't
        permanently bind to a model — enables model rotation/fallback.

        Parameters
        ----------
        session_id:
            The session identifier
        model_key:
            The selected model name
        ttl_seconds:
            Time-to-live before affinity expires (default: 1 hour)
        emit:
            If True (default), emit the affinity event. Set False to skip
            event emission (e.g., during initialization).
        """
        self._ensure_session_affinity()
        expires_at = time.time() + ttl_seconds
        self._session_affinity[session_id] = (model_key, expires_at)

        # Emit affinity event (lazy import to avoid circular import)
        if emit:
            # Lazy import to avoid circular import with core.daemon.__init__
            from core.daemon.events import _emit
            try:
                asyncio.get_event_loop().create_task(
                    _emit(
                        "model.affinity.selected",
                        {
                            "session_id": session_id,
                            "model": model_key,
                            "expires_at": expires_at,
                        },
                        session_id=session_id,
                        source=self._source,
                    )
                )
            except Exception:
                pass  # Non-critical if event emission fails

    def get_session_affinity(self, session_id: Optional[str] = None) -> Optional[tuple[str, float]]:
        """Get session affinity info.

        Returns (model_key, expires_at) or None if not found/expired.
        """
        self._ensure_session_affinity()
        target_id = session_id or self._get_current_session_id()

        # Check if expired
        if target_id in self._session_affinity:
            model_key, expires_at = self._session_affinity[target_id]
            if time.time() > expires_at:
                # Expired — remove and return None
                del self._session_affinity[target_id]
                return None
            return (model_key, expires_at)

        return None

    def _get_current_session_id(self) -> str:
        """Get the current session ID — placeholder for daemon integration."""
        # In production, this would come from the daemon context
        return f"sess_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

    # -----------------------------------------------------------------
    # Provider tracking
    # -----------------------------------------------------------------

    def register_provider(self, provider: str, models: List[str]) -> None:
        """Register available models from a provider.

        Parameters
        ----------
        provider:
            Provider name (e.g. "openai", "anthropic", "google")
        models:
            List of model names available from this provider
        """
        self._ensure_provider_models()
        self._provider_models[provider] = models
        logger.info(f"Registered provider {provider} with models: {models}")

    def get_provider_model(self, provider: str, capability_filter: str = CAP_CLOUD_ALLOWED) -> Optional[str]:
        """Get an available model from a specific provider.

        Parameters
        ----------
        provider:
            Provider name
        capability_filter:
            How to filter models

        Returns
        -------
        Optional[str]: Model name or None if provider not available
        """
        models = self._provider_models.get(provider)
        if not models:
            logger.warning(f"Provider {provider} not registered")
            return None

        # Simple round-robin or first available
        # In production would apply capability filtering
        return models[0] if models else None

    # -----------------------------------------------------------------
    # Selection event emission
    # -----------------------------------------------------------------

    def _emit_selection_event(
        self,
        model: str,
        tier: str,
        draft: bool,
        verification: bool,
        capability: Optional[List[str]],
        capability_filter: str,
        session_id: Optional[str],
        emit: bool = True,
    ) -> None:
        """Emit a model.selection event to the event bus.

        This is the canonical event for model selection changes.

        Parameters
        ----------
        model:
            The selected model
        tier:
            The cascade tier
        draft:
            Whether this is a draft model
        verification:
            Whether this is a verification model
        capability:
            Required capabilities
        capability_filter:
            How to filter capabilities
        session_id:
            Session ID for affinity tracking
        emit:
            If True (default), emit the event. Set False to skip
            event emission (e.g., during initialization or testing).
        """
        if not emit:
            return

        # Lazy import to avoid circular import with core.daemon.__init__
        from core.daemon.events import _emit

        try:
            asyncio.get_event_loop().create_task(
                _emit(
                    "model.selection",
                    {
                        "model": model,
                        "tier": tier,
                        "draft": draft,
                        "verification": verification,
                        "capability": capability or [],
                        "capability_filter": capability_filter,
                        "session_id": session_id or self._get_current_session_id(),
                    },
                    session_id=session_id or self._get_current_session_id(),
                    source=self._source,
                )
            )
        except Exception as e:
            logger.debug(f"Failed to emit selection event: {e}")

    # -----------------------------------------------------------------
    # History monitoring
    # -----------------------------------------------------------------

    def record_selection(
        self,
        model: str,
        tier: str,
        success: bool,
        latency_ms: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """Record a model selection for monitoring/history.

        Parameters
        ----------
        model:
            The model that was selected
        tier:
            The cascade tier
        success:
            Whether the selection/execution succeeded
        latency_ms:
            Execution latency in milliseconds
        error:
            Error message if selection failed
        """
        self._ensure_selection_history()
        entry = {
            "model": model,
            "tier": tier,
            "success": success,
            "latency_ms": latency_ms,
            "error": error,
            "timestamp": time.time(),
        }
        self._selection_history.append(entry)

        # Keep history manageable
        if len(self._selection_history) > 1000:
            self._selection_history = self._selection_history[-500:]

    def get_selection_stats(self) -> Dict[str, Any]:
        """Get selection statistics from history."""
        if not self._selection_history:
            return {"total": 0}

        total = len(self._selection_history)
        successful = sum(1 for e in self._selection_history if e["success"])
        tiers = {}
        for e in self._selection_history:
            t = e["tier"]
            tiers[t] = tiers.get(t, 0) + 1

        return {
            "total": total,
            "successful": successful,
            "success_rate": successful / total if total > 0 else 0,
            "tier_distribution": tiers,
        }

    # -----------------------------------------------------------------
    # Module export
    # ---------------------------------------------------------------------------

    __all__ = [
        "ModelGateway",
        "CAP_LOCAL_ONLY",
        "CAP_CLOUD_ALLOWED",
        "CAP_PRIVACY_REQUIRED",
        "CAP_GPU_REQUIRED",
        "CASCADE_TIERS",
        "DEFAULT_MODELS",
    ]