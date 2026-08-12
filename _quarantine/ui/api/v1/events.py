"""Event API v1 — publish, subscribe, unsubscribe.

Plugins use this API to communicate through the EventBus.
"""
import logging
from collections.abc import Callable
from typing import Any

from api.v1.models import EventRecord

logger = logging.getLogger("jarvis.api.v1.events")


class EventAPI:
    """Stable interface to JARVIS EventBus."""

    def __init__(self, event_bus):
        self._bus = event_bus

    def publish(self, event: EventRecord) -> bool:
        try:
            self._bus.emit(
                event_name=event.name,
                data=event.data,
                source=event.source or "api.v1",
                trace_id=event.trace_id or "",
            )
            return True
        except Exception as e:
            logger.error("EventAPI.publish failed: %s", e)
            return False

    def subscribe(self, event_name: str, handler: Callable) -> bool:
        try:
            self._bus.subscribe(event_name, handler)
            return True
        except Exception as e:
            logger.error("EventAPI.subscribe failed: %s", e)
            return False

    def unsubscribe(self, event_name: str, handler: Callable) -> bool:
        try:
            self._bus.unsubscribe(event_name, handler)
            return True
        except Exception as e:
            logger.error("EventAPI.unsubscribe failed: %s", e)
            return False

    def get_recent(self, count: int = 20) -> list[dict[str, Any]]:
        try:
            return self._bus.get_recent_events(count=count)
        except Exception:
            return []
