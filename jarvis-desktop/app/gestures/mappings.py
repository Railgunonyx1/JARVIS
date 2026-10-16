"""Gesture-to-action mapping for JARVIS Desktop.

Translates recognized gestures into application or desktop commands.
Mappings are configurable; defaults follow the master plan §7 vocabulary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from app.gestures.recognition import GestureEvent, GestureType

logger = logging.getLogger("jarvis.desktop.gestures.mappings")


@dataclass
class GestureMapping:
    """Maps a gesture to an action."""
    gesture: GestureType
    action: str
    description: str = ""
    enabled: bool = True
    require_confirmation: bool = False


DEFAULT_MAPPINGS: dict[GestureType, GestureMapping] = {
    GestureType.PINCH: GestureMapping(GestureType.PINCH, "select", "Select or grab"),
    GestureType.PINCH_MOVE: GestureMapping(GestureType.PINCH_MOVE, "move", "Move selected panel"),
    GestureType.OPEN_PALM: GestureMapping(GestureType.OPEN_PALM, "release", "Release selection"),
    GestureType.ZOOM_IN: GestureMapping(GestureType.ZOOM_IN, "zoom_in", "Zoom in"),
    GestureType.ZOOM_OUT: GestureMapping(GestureType.ZOOM_OUT, "zoom_out", "Zoom out"),
    GestureType.SWIPE_LEFT: GestureMapping(GestureType.SWIPE_LEFT, "prev_panel", "Previous panel"),
    GestureType.SWIPE_RIGHT: GestureMapping(GestureType.SWIPE_RIGHT, "next_panel", "Next panel"),
    GestureType.GRAB: GestureMapping(GestureType.GRAB, "grab", "Grab object"),
    GestureType.RELEASE: GestureMapping(GestureType.RELEASE, "release", "Release object"),
}


class GestureMapper:
    """Maps gesture events to actions.

    Usage:
        mapper = GestureMapper()
        mapper.set_handler("select", my_select_fn)
        mapper.handle(gesture_event)
    """

    def __init__(self, *, on_action: Callable[[str, GestureEvent], None] | None = None):
        self._mappings = dict(DEFAULT_MAPPINGS)
        self._handlers: dict[str, Callable] = {}
        self._on_action = on_action

    def set_handler(self, action: str, handler: Callable) -> None:
        """Register a handler for an action name."""
        self._handlers[action] = handler

    def remove_handler(self, action: str) -> None:
        self._handlers.pop(action, None)

    def handle(self, event: GestureEvent) -> str | None:
        """Map a gesture event to an action and dispatch it."""
        if event.gesture == GestureType.NONE:
            return None
        mapping = self._mappings.get(event.gesture)
        if not mapping or not mapping.enabled:
            return None
        action = mapping.action
        handler = self._handlers.get(action)
        if handler:
            try:
                handler(event)
            except Exception as e:
                logger.warning("Action handler %s failed: %s", action, e)
        if self._on_action:
            self._on_action(action, event)
        return action

    def enable_gesture(self, gesture: GestureType, enabled: bool = True) -> None:
        if gesture in self._mappings:
            self._mappings[gesture].enabled = enabled

    def get_mapping(self, gesture: GestureType) -> GestureMapping | None:
        return self._mappings.get(gesture)

    def get_all_mappings(self) -> dict[GestureType, GestureMapping]:
        return dict(self._mappings)
