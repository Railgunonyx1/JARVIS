"""Skill Registry — loads skill manifests and integrates with the mode system.

Maps skills/manifests/*.json into the JARVIS capability registry so skills
are discoverable, searchable, and usable at runtime via the tool executor.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.capability_registry import (
    Capability,
    CapabilityCategory,
    CapabilityRisk,
    get_capability,
    merge_capabilities,
)

logger = logging.getLogger("jarvis.skills.registry")

_MANIFESTS_DIR = Path(__file__).resolve().parent / "manifests"


def _load_manifests() -> list[dict[str, Any]]:
    """Load all skill manifests from the manifests directory."""
    if not _MANIFESTS_DIR.is_dir():
        return []
    manifests: list[dict[str, Any]] = []
    for path in sorted(_MANIFESTS_DIR.glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            manifests.append(data)
        except Exception as e:
            logger.warning("Failed to load manifest %s: %s", path, e)
    return manifests


def _manifest_to_capability(m: dict[str, Any]) -> Capability | None:
    """Convert a skill manifest dict into a Capability instance."""
    name = m.get("name", "")
    description = m.get("description", "")
    tools = m.get("tools", [])
    tags = m.get("tags", [])
    version = m.get("version", "1.0.0")

    # Map risk from manifest (default to SAFE if not specified)
    risk_str = m.get("risk", "low")
    risk_map = {
        "low": CapabilityRisk.LOW,
        "medium": CapabilityRisk.MEDIUM,
        "high": CapabilityRisk.HIGH,
    }
    risk = risk_map.get(risk_str, CapabilityRisk.SAFE)

    # Map timeout to cost (simple heuristic: higher timeout = higher cost)
    timeout = m.get("timeout")
    cost = round(timeout / 60, 2) if timeout else 0.0

    # Preferred models from manifest
    preferred_models = m.get("preferred_models", [])

    # Build capability name from manifest name
    cap_name = f"skills.{name}"

    # Build description combining manifest description with tool info
    tool_descriptions = "; ".join(tools) if tools else "No tools configured"
    full_description = f"{description}. Tools: {tool_descriptions}"

    cap = Capability(
        name=cap_name,
        category=CapabilityCategory.MEMORY,  # Skills are memory-adjacent
        risk=risk,
        description=full_description,
        tags=tags,
        cost=cost,
        latency="medium",
        provider="local",
        examples=[f"skills/{name}"],
    )

    # Attach preferred_models as metadata for the executor
    cap.metadata["preferred_models"] = preferred_models

    return cap


def build_default_skill_registry() -> dict[str, Capability]:
    """Build a capability registry from all skill manifests.

    Scans ``skills/manifests/*.json``, converts each into a ``Capability``,
    and merges them into the global capability tree via the atomic merge
    protocol.  Returns the flat registry dict keyed by capability name.

    Returns:
        dict[str, Capability]: Flat map of all registered skills.
    """
    manifests = _load_manifests()
    capabilities: list[Capability] = []

    for m in manifests:
        cap = _manifest_to_capability(m)
        if cap and cap.name:
            capabilities.append(cap)

    if not capabilities:
        logger.warning("No skill manifests found in %s", _MANIFESTS_DIR)
        return {}

    # Merge all capabilities into the global tree via atomic merge
    merged = CapabilityTree.build_branch(capabilities)
    _get_tree().merge(merged)

    # Return flat cache
    from core.capability_registry import _get_tree as _gt
    _gt._ensure_cache()
    return _gt._flat_cache.copy()


def get_skill(name: str) -> Capability | None:
    """Resolve a skill by its manifest name."""
    from core.capability_registry import _get_tree
    return _get_tree().resolve(f"skills.{name}")


def list_skills(
    tags: list[str] | None = None,
    risk: CapabilityRisk | None = None,
    max_risk: CapabilityRisk | None = None,
) -> list[Capability]:
    """Search skills by tags, risk, or max_risk."""
    from core.capability_registry import _get_tree
    return _get_tree().search(tags=tags, risk=risk, max_risk=max_risk)


def list_all_skills() -> list[Capability]:
    """List all registered skills."""
    from core.capability_registry import _get_tree
    _get_tree._ensure_cache()
    return list(_get_tree._flat_cache.values())


# Auto-load manifests on import so the registry is populated when skills is imported
_AUTOMERGED = build_default_skill_registry()

if _AUTOMERGED:
    logger.info("Loaded %d skill manifests into capability registry", len(_AUTOMERGED))
else:
    logger.warning("No skill manifests loaded — check skills/manifests/ directory")