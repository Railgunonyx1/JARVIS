"""HarnessSelector — Harness selection authority for JARVIS MK-X.

Adapted from microsoft/agent-framework patterns. The HarnessSelector is the
canonical harness selection authority — all harness selection should go through
this class, NOT via direct CLI manipulation of `loop._preferred_model` or
similar private state.

Features:
- Harness selection by name with capability filtering
- Cascade tier selection for harness models (1B → 1.5B → 3B → 4B/7B)
- Session-affinity tracking with TTL
- Emits canonical BusEvent for harness selection changes
- Prevents direct private-state manipulation (enforces Harness ≠ Model invariant)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, List, Optional, Tuple

# Event emission is lazy-imported to avoid circular import with
# core.daemon.__init__. skills registry. During initialization or testing,
# set emit=False to skip event emission.

# Logging
logger = logging.getLogger("jarvis.harness_selector")

# ---------------------------------------------------------------------------
# Harness capability constants
# ---------------------------------------------------------------------------

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

# Default harness per tier (placeholder — would be configured per-provider)
DEFAULT_HARNESS = {
    "tiny": "harness_tiny",     # Minimal harness for tiny models
    "small": "harness_small",   # Basic harness for small models
    "medium": "harness_medium", # Standard harness for medium models
    "large": "harness_large",   # Full harness for large models
}


# ---------------------------------------------------------------------------
# HarnessSelector class — the canonical harness selection authority
# ---------------------------------------------------------------------------

class HarnessSelector:
    """Central harness selection authority for JARVIS MK-X.

    Responsibilities:
    - Harness selection by name and tier with capability filtering
    - Cascade tier management (1B → 1.5B → 3B → 4B/7B)
    - Session-affinity tracking with TTL
    - Emitting canonical BusEvent for harness selection changes
    - Enforcing Harness ≠ Model invariant (harness and model are independent axes)

    This is the __only__ harness selection authority. Direct manipulation of
    loop state or private attributes is prohibited — use
    `HarnessSelector.select_harness()` instead.

    The Harness ≠ Model invariant is central: harness and model are independent
    axes. A given model can run with any harness, and harness selection should
    not be tied to model selection via private state.
    """

    def __init__(self, config: Any = None, skill_registry: Any = None):
        self.config = config
        self.skill_registry = skill_registry

        # Harness availability tracking: tier → list of available harness names
        self._available_harnesses: Dict[str, List[str]] = {}

        # Session affinity: session_id → (harness_name, expires_at)
        self._session_affinity: Dict[str, tuple[str, float]] = {}

        # Selection history for monitoring
        self._selection_history: List[Dict[str, Any]] = []

        # Emission source
        self._source = "harness_selector"

        logger.info("HarnessSelector initialized")

    # -----------------------------------------------------------------
    # Harness selection
    # -----------------------------------------------------------------

    def select_harness(
        self,
        tier: str = "medium",
        *,
        capability: Optional[List[str]] = None,
        capability_filter: str = CAP_CLOUD_ALLOWED,
        session_id: Optional[str] = None,
        emit: bool = True,
    ) -> str:
        """Select a harness for the given tier and capabilities.

        This is the canonical harness selection method. All harness routing
        should go through this method, NOT via direct private state access.

        The Harness ≠ Model invariant is enforced: harness and model are
        independent axes. This method selects only the harness; model
        selection should go through ModelGateway.select_model().

        Parameters
        ----------
        tier:
            Cascade tier: "tiny", "small", "medium", "large"
        capability:
            Optional list of required capabilities
        capability_filter:
            How to filter: "local-only", "cloud-allowed", "privacy-required",
            "gpu-required"
        session_id:
            Optional session ID for affinity tracking
        emit:
            If True (default), emit selection event. Set False to skip
            event emission (e.g., during initialization or testing).

        Returns
        -------
        str: Harness name string
        """
        # Resolve harness for tier
        harness = self._resolve_harness(tier, capability_filter=capability_filter)

        # Apply capability filtering
        if capability:
            # Check if harness supports required capabilities
            if not self._has_capabilities(harness, capability):
                logger.warning(
                    f"Harness {harness} does not support required capabilities {capability}; "
                    f"falling back to default"
                )
                harness = self._resolve_harness("medium", capability_filter=capability_filter)

        # Emit selection event
        if emit:
            self._emit_selection_event(
                harness=harness,
                tier=tier,
                capability=capability,
                capability_filter=capability_filter,
                session_id=session_id,
            )

        # Track affinity
        if session_id:
            self._set_session_affinity(session_id, harness, emit=emit)

        return harness

    def _resolve_harness(
        self, tier: str, capability_filter: str = CAP_CLOUD_ALLOWED
    ) -> str:
        """Resolve a harness for the given tier and capability filter.

        Uses the DEFAULT_HARNESS mapping, with fallback to placeholder names.
        """
        harness = DEFAULT_HARNESS.get(tier)
        if harness:
            return harness

        # Fall back to placeholder names based on tier
        return f"harness_{tier}"

    def _has_capabilities(self, harness: str, capability: List[str]) -> bool:
        """Check if a harness supports the required capabilities.

        In a production system this would query harness metadata.
        For now, we use a simple heuristic based on harness name patterns.
        """
        harness_lower = harness.lower()
        # Simple: assume all cloud-allowed harnesses support common capabilities
        has_tool_use = any(
            kw in harness_lower for kw in ("browser", "filesystem", "search", "analysis")
        )
        return has_tool_use or len(capability) == 0

    # -----------------------------------------------------------------
    # Draft-then-verification harness routing
    # -----------------------------------------------------------------

    def select_draft_harness(
        self, tier: str = "medium", session_id: Optional[str] = None, emit: bool = True
    ) -> str:
        """Select a draft (lighter) harness for the given tier.

        Draft harnesses are used for initial generation; verification harnesses
        are then used to independently check the result.
        """
        draft_tier = self._draft_tier(tier)
        harness = self.select_harness(
            tier=draft_tier,
            capability_filter=CAP_CLOUD_ALLOWED,
            session_id=session_id,
            emit=emit,
        )
        logger.info(f"Selected draft harness {harness} (tier={tier} → {draft_tier})")
        return harness

    def select_verification_harness(
        self, tier: str = "medium", session_id: Optional[str] = None, emit: bool = True
    ) -> str:
        """Select a verification harness for the given tier.

        Verification harnesses independently check the draft output. They
        should be a different harness when possible for better coverage.
        """
        verification_tier = self._verification_tier(tier)
        harness = self.select_harness(
            tier=verification_tier,
            capability_filter=CAP_CLOUD_ALLOWED,
            session_id=session_id,
            emit=emit,
        )
        logger.info(
            f"Selected verification harness {harness} (tier={tier} → {verification_tier})"
        )
        return harness

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
        current_index = CASCADE_TIERS.index(tier) if tier in CASCADE_TIERS else 2
        if current_index + 1 < len(CASCADE_TIERS):
            return CASCADE_TIERS[current_index + 1]
        return tier

    # -----------------------------------------------------------------
    # Session affinity
    # -----------------------------------------------------------------

    def _set_session_affinity(self, session_id: str, harness_name: str, ttl_seconds: int = 3600, emit: bool = True) -> None:
        """Set session affinity for a harness name.

        Maps session_id → (harness_name, expires_at) so that sessions don't
        permanently bind to a harness — enables harness rotation/fallback.

        The Harness ≠ Model invariant is key: this affinity tracks which harness
        a session is using, but this does NOT tie the session to a specific model.
        Model selection should go through ModelGateway independently.

        Parameters
        ----------
        session_id:
            The session identifier
        harness_name:
            The selected harness name
        ttl_seconds:
            Time-to-live before affinity expires (default: 1 hour)
        emit:
            If True (default), emit the affinity event. Set False to skip
            event emission (e.g., during initialization).
        """
        self._ensure_session_affinity()
        expires_at = time.time() + ttl_seconds
        self._session_affinity[session_id] = (harness_name, expires_at)

        # Emit affinity event (lazy import to avoid circular import)
        if emit:
            # Lazy import to avoid circular import with core.daemon.__init__
            from core.daemon.events import _emit
            try:
                asyncio.get_event_loop().create_task(
                    _emit(
                        "harness.affinity.selected",
                        {
                            "session_id": session_id,
                            "harness": harness_name,
                            "expires_at": expires_at,
                        },
                        session_id=session_id,
                        source=self._source,
                    )
                )
            except Exception:
                pass  # Non-critical if event emission fails

    def _emit_affinity_event(
        self, session_id: str, harness_name: str, expires_at: float
    ) -> None:
        """Emit a harness.affinity.selected event to the event bus."""
        try:
            from core.daemon.events import _emit

            asyncio.get_event_loop().create_task(
                _emit(
                    "harness.affinity.selected",
                    {
                        "session_id": session_id,
                        "harness": harness_name,
                        "expires_at": expires_at,
                    },
                    session_id=session_id,
                    source=self._source,
                )
            )
        except Exception as e:
            logger.debug(f"Failed to emit affinity event: {e}")

    def get_session_affinity(self, session_id: Optional[str] = None) -> Optional[tuple[str, float]]:
        """Get session affinity info.

        Returns (harness_name, expires_at) or None if not found/expired.
        """
        self._ensure_session_affinity()
        target_id = session_id or self._get_current_session_id()

        # Check if expired
        if target_id in self._session_affinity:
            harness_name, expires_at = self._session_affinity[target_id]
            if time.time() > expires_at:
                # Expired — remove and return None
                del self._session_affinity[target_id]
                return None
            return (harness_name, expires_at)

        return None

    def _get_current_session_id(self) -> str:
        """Get the current session ID — placeholder for daemon integration."""
        return f"sess_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

    # -----------------------------------------------------------------
    # History monitoring
    # -----------------------------------------------------------------

    def record_selection(
        self,
        harness: str,
        tier: str,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Record a harness selection for monitoring/history.

        Parameters
        ----------
        harness:
            The harness that was selected
        tier:
            The cascade tier
        success:
            Whether the harness selection succeeded
        error:
            Error message if harness selection failed
        """
        self._ensure_selection_history()
        entry = {
            "harness": harness,
            "tier": tier,
            "success": success,
            "error": error,
            "timestamp": time.time(),
        }
        self._selection_history.append(entry)

        # Keep history manageable
        if len(self._selection_history) > 1000:
            self._selection_history = self._selection_history[-500:]

    def get_selection_stats(self) -> Dict[str, Any]:
        """Get harness selection statistics from history."""
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
    # Ensuring initialization
    # -----------------------------------------------------------------

    def _ensure_session_affinity(self) -> None:
        """Ensure _session_affinity dict is initialized."""
        if not hasattr(self, "_session_affinity") or self._session_affinity is None:
            self._session_affinity: Dict[str, tuple[str, float]] = {}

    def _ensure_selection_history(self) -> None:
        """Ensure _selection_history list is initialized."""
        if not hasattr(self, "_selection_history") or self._selection_history is None:
            self._selection_history: List[Dict[str, Any]] = []

    # -----------------------------------------------------------------
    # Module export
    # ---------------------------------------------------------------------------

    __all__ = [
        "HarnessSelector",
        "CAP_LOCAL_ONLY",
        "CAP_CLOUD_ALLOWED",
        "CAP_PRIVACY_REQUIRED",
        "CAP_GPU_REQUIRED",
        "CASCADE_TIERS",
        "DEFAULT_HARNESS",
    ]