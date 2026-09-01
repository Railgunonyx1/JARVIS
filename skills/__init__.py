"""JARVIS Daemon Skills Package.

Adapted from Cordis microkernel philosophy — "everything is a plugin".

Provides:
- SkillRegistry: Auto-discoverable skill registry with frontmatter permission gating
- SkillMetadata: Parsed from skill.md frontmatter
- SkillContract: Runtime contract for skill execution with sandbox limits
"""

from core.daemon.skills.registry import SkillRegistry, SkillMetadata, SkillContract  # noqa: F401

__all__ = ["SkillRegistry", "SkillMetadata", "SkillContract"]