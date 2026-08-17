"""Sprint 9F -- Configurable keymap.

Maps raw key codes to UIIntents.  The keymap is the ONLY place where
physical keys become semantic actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis.terminal.intents import IntentType, UIIntent


@dataclass(frozen=True)
class KeyBinding:
    key: str
    ctrl: bool = False
    shift: bool = False
    alt: bool = False
    intent_type: IntentType = IntentType.UNKNOWN
    payload: dict[str, Any] = field(default_factory=dict)


_DEFAULT_BINDINGS: list[KeyBinding] = [
    KeyBinding(key="c", ctrl=True, intent_type=IntentType.CANCEL),
    KeyBinding(key="d", ctrl=True, intent_type=IntentType.CANCEL),
    KeyBinding(key="y", ctrl=True, intent_type=IntentType.CONFIRM_YES),
    KeyBinding(key="n", ctrl=True, intent_type=IntentType.CONFIRM_NO),
    KeyBinding(key="1", ctrl=True, intent_type=IntentType.SET_LAYOUT, payload={"mode": "minimal"}),
    KeyBinding(key="2", ctrl=True, intent_type=IntentType.SET_LAYOUT, payload={"mode": "normal"}),
    KeyBinding(key="3", ctrl=True, intent_type=IntentType.SET_LAYOUT, payload={"mode": "focus"}),
    KeyBinding(key="4", ctrl=True, intent_type=IntentType.SET_LAYOUT, payload={"mode": "plan"}),
    KeyBinding(key="p", ctrl=True, intent_type=IntentType.SET_LAYOUT, payload={"mode": "plan"}),
    KeyBinding(key="l", ctrl=True, intent_type=IntentType.SET_LAYOUT, payload={"mode": "activity"}),
]


class Keymap:
    """Configurable key-to-intent mapping with override support."""

    def __init__(self, bindings: list[KeyBinding] | None = None):
        self._bindings: list[KeyBinding] = list(bindings or _DEFAULT_BINDINGS)

    def resolve(self, key: str, ctrl: bool = False, shift: bool = False, alt: bool = False) -> UIIntent:
        """Map a physical key to a UIIntent. Returns Unknown if no match."""
        for b in self._bindings:
            if b.key == key and b.ctrl == ctrl and b.shift == shift and b.alt == alt:
                return UIIntent(type=b.intent_type, payload=dict(b.payload))
        return UIIntent(type=IntentType.UNKNOWN)

    def override(self, binding: KeyBinding) -> None:
        """Add or replace a binding."""
        self._bindings = [
            b for b in self._bindings
            if not (b.key == binding.key and b.ctrl == binding.ctrl
                    and b.shift == binding.shift and b.alt == binding.alt)
        ]
        self._bindings.append(binding)

    def remove(self, key: str, ctrl: bool = False) -> None:
        """Remove a binding by key combo."""
        self._bindings = [
            b for b in self._bindings
            if not (b.key == key and b.ctrl == ctrl)
        ]

    @property
    def bindings(self) -> list[KeyBinding]:
        return list(self._bindings)
