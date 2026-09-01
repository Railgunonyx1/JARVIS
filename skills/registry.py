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
    CapabilityTree,
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
        metadata={"preferred_models": preferred_models},
    )

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
    tree = CapabilityTree()
    for cap in capabilities:
        tree.merge(CapabilityTree.build_branch([cap]))

    # Return flat cache
    tree._ensure_cache()
    return tree._flat_cache.copy()


def get_skill(name: str) -> Capability | None:
    """Resolve a skill by its manifest name."""
    registry = build_default_skill_registry()
    # Accept both "architecture_auditor" and "skills.architecture_auditor"
    key = name if name.startswith("skills.") else f"skills.{name}"
    return registry.get(key)


def list_skills(
    tags: list[str] | None = None,
    risk: CapabilityRisk | None = None,
    max_risk: CapabilityRisk | None = None,
) -> list[Capability]:
    """Search skills by tags, risk, or max_risk."""
    registry = build_default_skill_registry()
    results: list[Capability] = []

    from core.capability_registry import CapabilityRisk as CR
    all_skills = registry.values() if registry else []

    if tags:
        tag_set = set(tags)
        results = [c for c in all_skills if tag_set & set(c.tags)]

    if risk:
        results = [c for c in results if c.risk == risk]

    if max_risk:
        risk_order = {r: i for i, r in enumerate(CapabilityRisk)}
        results = [
            c for c in results
            if risk_order.get(c.risk, 99) <= risk_order.get(max_risk, 99)
        ]

    return results


def list_all_skills() -> list[Capability]:
    """List all registered skills."""
    registry = build_default_skill_registry()
    return list(registry.values()) if registry else []