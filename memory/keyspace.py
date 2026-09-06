"""Constellation keyspace + ownership for selective memory (G12).

Every memory key lives in one owned namespace — the *constellation*:

    user.<domain>.<name>            the operator's stable memory
    agent.<agent_id>.<domain>.<name>  one agent's working memory
    system.<domain>.<name>          runtime-owned state

Writing outside your namespace is denied (mirrors tab ownership): USER may
write only ``user.*``, an AGENT only ``agent.<its-id>.*``, SYSTEM only
``system.*``. Reading is scoped: USER and SYSTEM read everything; an AGENT
reads ``user.*``, ``system.*`` and its own ``agent.<id>.*`` — never a
sibling agent's namespace.

Legacy unprefixed keys (written before ownership existed) are treated as
user-owned and readable by everyone, so existing memories keep working and
only the operator can still write them.

This module is pure logic (no storage) so the rules are trivially testable.
"""

from __future__ import annotations

import re

# Stable identity kinds.
KIND_USER = "user"
KIND_AGENT = "agent"
KIND_SYSTEM = "system"

_NAMESPACES = (KIND_USER, KIND_AGENT, KIND_SYSTEM)

_AGENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

# Legacy keys that predate the keyspace have no known namespace prefix and
# remain user-owned (readable by everyone, writable only by the operator).
_LEGACY_PREFIXES: tuple[str, ...] = ()


def is_valid_agent_id(agent_id: str) -> bool:
    """A stable agent id is a short lowercase-ish slug (letters/digits/-/_)."""
    return bool(agent_id) and bool(_AGENT_ID_RE.match(agent_id))


def parse_key(key: str) -> tuple[str, str, str]:
    """Return ``(namespace, owner_id, rest)`` for a keyspace key.

    ``owner_id`` is ``""`` for user/system namespaces and the agent id for
    ``agent.<id>.`` keys. Raises ``ValueError`` for malformed keyspace keys.
    """
    key = (key or "").strip()
    if not key:
        raise ValueError("memory key is empty")
    parts = key.split(".")
    if len(parts) < 2 or parts[0] not in _NAMESPACES:
        raise ValueError(
            "memory key must start with user., agent.<id>. or system. "
            f"(got {key!r})"
        )
    namespace = parts[0]
    rest = ".".join(parts[1:])
    if not rest or not _SEGMENT_RE.match(rest):
        raise ValueError(f"invalid memory key segment: {key!r}")
    if namespace == KIND_AGENT:
        owner_id = parts[1]
        if not is_valid_agent_id(owner_id):
            raise ValueError(f"invalid agent id in memory key: {key!r}")
        return namespace, owner_id, ".".join(parts[2:])
    return namespace, "", rest


def owner_key(kind: str, agent_id: str = "") -> str:
    """Canonical owner string stored on rows: user | agent:<id> | system."""
    if kind == KIND_AGENT:
        if not is_valid_agent_id(agent_id):
            raise ValueError(f"invalid agent id: {agent_id!r}")
        return f"{KIND_AGENT}:{agent_id}"
    if kind in (KIND_USER, KIND_SYSTEM):
        return kind
    raise ValueError(f"unknown owner kind: {kind!r}")


def key_namespace(key: str) -> str:
    """Namespace of a keyspace key ('user' | 'agent' | 'system')."""
    return key.split(".", 1)[0]


def _is_legacy(key: str) -> bool:
    return key_namespace(key) not in _NAMESPACES


def can_write(key: str, owner: str) -> bool:
    """May ``owner`` (user | agent:<id> | system) write ``key``?"""
    if _is_legacy(key):
        return owner == KIND_USER or owner == "user"
    namespace = key_namespace(key)
    if owner == KIND_USER or owner == "user":
        return namespace == KIND_USER
    if owner == KIND_SYSTEM or owner == "system":
        return namespace == KIND_SYSTEM
    if owner.startswith(f"{KIND_AGENT}:"):
        agent_id = owner.split(":", 1)[1]
        try:
            ns, owner_id, _ = parse_key(key)
        except ValueError:
            return False
        return ns == KIND_AGENT and owner_id == agent_id
    return False


def can_read(key: str, owner: str) -> bool:
    """May ``owner`` read ``key``? Sibling agent namespaces are private."""
    if _is_legacy(key):
        return True
    namespace = key_namespace(key)
    if namespace != KIND_AGENT:
        return True
    if owner in (KIND_USER, "user", KIND_SYSTEM, "system"):
        return True
    if owner.startswith(f"{KIND_AGENT}:"):
        agent_id = owner.split(":", 1)[1]
        try:
            ns, owner_id, _ = parse_key(key)
        except ValueError:
            return False
        return owner_id == agent_id
    return False


__all__ = [
    "KIND_AGENT",
    "KIND_SYSTEM",
    "KIND_USER",
    "can_read",
    "can_write",
    "is_valid_agent_id",
    "key_namespace",
    "owner_key",
    "parse_key",
]
