"""Simple DI container for services."""

from __future__ import annotations

from typing import Any


class ServiceContainer:
    """Register and resolve named services."""

    def __init__(self) -> None:
        self.services: dict[str, Any] = {}

    def register(self, name: str, service: Any) -> None:
        self.services[name] = service

    def get(self, name: str) -> Any | None:
        return self.services.get(name)

    def has(self, name: str) -> bool:
        return name in self.services
