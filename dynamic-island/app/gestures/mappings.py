"""Gesture-to-action mapping for JARVIS Desktop.

Translates recognized gestures into application or desktop commands.
Mappings are configurable; defaults follow the master plan §7 vocabulary.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

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
    # Island workspace gestures — mapped to coordinator actions, not desktop OS.
    GestureType.PINCH: GestureMapping(GestureType.PINCH, "toggle_gesture_mode", "Enter/exit gesture mode"),
    GestureType.PINCH_MOVE: GestureMapping(GestureType.PINCH_MOVE, "pan_workspace", "Pan the 3D workspace"),
    GestureType.OPEN_PALM: GestureMapping(GestureType.OPEN_PALM, "exit_gesture_mode", "Exit gesture mode without action"),
    GestureType.ZOOM_IN: GestureMapping(GestureType.ZOOM_IN, "zoom_in", "Zoom in (workspace)"),
    GestureType.ZOOM_OUT: GestureMapping(GestureType.ZOOM_OUT, "zoom_out", "Zoom out (workspace)"),
    GestureType.SWIPE_LEFT: GestureMapping(GestureType.SWIPE_LEFT, "prev_task", "Previous task/panel"),
    GestureType.SWIPE_RIGHT: GestureMapping(GestureType.SWIPE_RIGHT, "next_task", "Next task/panel"),
    GestureType.GRAB: GestureMapping(GestureType.GRAB, "capture_selection", "Capture/selection mode"),
    GestureType.RELEASE: GestureMapping(GestureType.RELEASE, "deselect", "Deselect/cancel mode"),
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
