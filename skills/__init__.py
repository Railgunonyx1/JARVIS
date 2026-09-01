"""JARVIS Daemon Skills Package.

Adapted from Cordis microkernel philosophy — "everything is a plugin".

Provides:
- build_default_skill_registry(): Load skill manifests into capability registry
- get_skill(): Resolve a skill by name
- list_skills(): Search skills by tags/risk
- list_all_skills(): List all registered skills
"""

from .registry import (
    build_default_skill_registry,
    get_skill,
    list_skills,
    list_all_skills,
)  # noqa: F401

__all__ = [
    "build_default_skill_registry",
    "get_skill",
    "list_skills",
    "list_all_skills",
]