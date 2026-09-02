"""JARVIS MK-X Skills Package.

Provides a manifest-driven skill registry. Each skill is a ``skills/manifests/*.json``
capability declaration (name, description, tags, the live tools it draws on, and an
optional runtime contract: risk, timeout, preferred_models).

- ``SkillRegistry``: Auto-discovers and loads skill manifests.
- ``SkillMetadata``: Parsed manifest metadata.
- ``SkillContract``: Runtime contract for skill execution with sandbox limits.
- ``build_default_skill_registry``: Warm entrypoint used by the CLI ``/skills`` command.
"""

from skills.registry import (
    SkillContract,
    SkillMetadata,
    SkillRegistry,
    Skill,
    build_default_skill_registry,
    reset_skill_registry_cache,
)

__all__ = [
    "SkillRegistry",
    "SkillMetadata",
    "SkillContract",
    "Skill",
    "build_default_skill_registry",
    "reset_skill_registry_cache",
]
