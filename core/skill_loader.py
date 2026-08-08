"""Skill Manifest Loader — loads skill.json manifests and integrates with mode system."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from core.mode_manager import get_mode_manager, ExecutionMode
from core.capability_registry import get_capability, CAPABILITY_REGISTRY

logger = logging.getLogger("jarvis.skills")


@dataclass
class SkillManifest:
    name: str
    version: str
    description: str
    capabilities: List[str]
    permissions: List[str]
    supported_modes: List[ExecutionMode]
    entry_point: str


class SkillLoader:
    """Loads skill manifests and validates against current execution mode."""

    def __init__(self, manifests_dir: Optional[Path] = None):
        if manifests_dir is None:
            manifests_dir = Path(__file__).resolve().parent.parent / "skills" / "manifests"
        self.manifests_dir = manifests_dir
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
        self._skills: Dict[str, SkillManifest] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all skill manifests from the manifests directory."""
        if not self.manifests_dir.exists():
            logger.warning("Manifests directory not found: %s", self.manifests_dir)
            return

        for json_file in self.manifests_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                manifest = SkillManifest(
                    name=data["name"],
                    version=data["version"],
                    description=data["description"],
                    capabilities=data["capabilities"],
                    permissions=data.get("permissions", []),
                    supported_modes=[ExecutionMode(m) for m in data.get("supported_modes", [])],
                    entry_point=data.get("entry_point", ""),
                )

                # Validate capabilities exist in registry
                for cap in manifest.capabilities:
                    if cap not in CAPABILITY_REGISTRY:
                        logger.warning("Skill '%s' references unknown capability: %s", manifest.name, cap)

                self._skills[manifest.name] = manifest
                logger.info("Loaded skill manifest: %s (v%s)", manifest.name, manifest.version)

            except Exception as e:
                logger.error("Failed to load skill manifest %s: %s", json_file, e)

    def get_skill(self, name: str) -> Optional[SkillManifest]:
        """Get a skill manifest by name."""
        return self._skills.get(name)

    def get_all_skills(self) -> Dict[str, SkillManifest]:
        """Get all loaded skill manifests."""
        return self._skills.copy()

    def get_skills_for_mode(self, mode: Optional[ExecutionMode] = None) -> Dict[str, SkillManifest]:
        """Get skills compatible with the given mode."""
        if mode is None:
            mode = get_mode_manager().get_mode()

        return {
            name: skill
            for name, skill in self._skills.items()
            if mode in skill.supported_modes
        }

    def get_capabilities_for_mode(self, mode: Optional[ExecutionMode] = None) -> List[str]:
        """Get all capabilities from skills compatible with the given mode."""
        skills = self.get_skills_for_mode(mode)
        capabilities = []
        for skill in skills.values():
            capabilities.extend(skill.capabilities)
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for cap in capabilities:
            if cap not in seen:
                seen.add(cap)
                unique.append(cap)
        return unique

    def validate_skill_for_mode(self, skill_name: str, mode: Optional[ExecutionMode] = None) -> bool:
        """Check if a skill is valid for the given mode."""
        skill = self._skills.get(skill_name)
        if not skill:
            return False
        if mode is None:
            mode = get_mode_manager().get_mode()
        return mode in skill.supported_modes


_skill_loader: Optional[SkillLoader] = None


def get_skill_loader() -> SkillLoader:
    global _skill_loader
    if _skill_loader is None:
        _skill_loader = SkillLoader()
    return _skill_loader


def reload_skills() -> SkillLoader:
    """Reload all skill manifests."""
    global _skill_loader
    _skill_loader = SkillLoader()
    return _skill_loader