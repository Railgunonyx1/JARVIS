"""Capability API v1 — register, query, search capabilities.

Plugins register their capabilities through this API.
The CapabilityRegistry remains the single source of truth.
"""
import logging
from typing import Any, Dict, List, Optional

from api.v1.models import CapabilityInfo

logger = logging.getLogger("jarvis.api.v1.capabilities")


class CapabilityAPI:
    """Stable interface for capability discovery and registration."""

    def __init__(self, capability_registry=None, action_registry=None):
        self._cap_registry = capability_registry
        self._action_registry = action_registry

    def query(self, name: str) -> Optional[CapabilityInfo]:
        try:
            cap = self._cap_registry.get(name)
            if cap:
                return CapabilityInfo(
                    name=cap.name,
                    description=getattr(cap, "description", ""),
                    tags=getattr(cap, "tags", []),
                    permissions=getattr(cap, "permissions", []),
                    risk=getattr(cap, "risk", "safe"),
                )
        except Exception as e:
            logger.error("CapabilityAPI.query failed: %s", e)
        return None

    def search(self, tags: List[str] = None, query: str = "") -> List[CapabilityInfo]:
        results = []
        try:
            if self._cap_registry and hasattr(self._cap_registry, "search"):
                caps = self._cap_registry.search(tags=tags or [])
                for cap in caps:
                    results.append(CapabilityInfo(
                        name=cap.name,
                        description=getattr(cap, "description", ""),
                        tags=getattr(cap, "tags", []),
                        permissions=getattr(cap, "permissions", []),
                        risk=getattr(cap, "risk", "safe"),
                    ))
        except Exception as e:
            logger.error("CapabilityAPI.search failed: %s", e)
        return results

    def list_all(self) -> List[str]:
        if self._action_registry:
            return self._action_registry.get_names()
        return []

    def get_stats(self) -> Dict[str, Any]:
        return {
            "registered_actions": len(self.list_all()),
        }
