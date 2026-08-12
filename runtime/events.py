"""Simple async event bus for publish/subscribe pattern."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


class EventBus:
    """In-process pub/sub event bus.

    Subscribers are sync or async callables receiving ``(name, payload)``.
    """

    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[str, Any], Any]]] = {}

    def subscribe(self, name: str, handler: Callable[[str, Any], Any]) -> None:
        self._subs.setdefault(name, []).append(handler)

    def unsubscribe(self, name: str, handler: Callable[[str, Any], Any]) -> None:
        subs = self._subs.get(name, [])
        if handler in subs:
            subs.remove(handler)

    async def publish(self, name: str, payload: Any = None) -> None:
        for handler in list(self._subs.get(name, [])):
            result = handler(name, payload)
            if asyncio.iscoroutine(result):
                await result
