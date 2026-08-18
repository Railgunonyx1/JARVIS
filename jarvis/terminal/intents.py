"""Sprint 9E — UIIntent types.

The terminal converts raw input (keystrokes, paste, resize) into UIIntents.
Intents are the ONLY way the terminal talks to the core kernel.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from jarvis.terminal.types import _uuid


class IntentType(enum.Enum):
    SUBMIT_MESSAGE = "submit_message"
    CANCEL = "cancel"
    CONFIRM_YES = "confirm_yes"
    CONFIRM_NO = "confirm_no"
    SET_LAYOUT = "set_layout"
    SWITCH_MODEL = "switch_model"
    SWITCH_PROVIDER = "switch_provider"
    SWITCH_HARNESS = "switch_harness"
    RESIZE = "resize"
    SCROLL_UP = "scroll_up"
    SCROLL_DOWN = "scroll_down"
    PAUSE = "pause"
    RESUME = "resume"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class UIIntent:
    type: IntentType
    payload: dict[str, Any] = field(default_factory=dict)
    intent_id: str = field(default_factory=_uuid)


def intent_submit(text: str) -> UIIntent:
    return UIIntent(type=IntentType.SUBMIT_MESSAGE, payload={"text": text})


def intent_cancel() -> UIIntent:
    return UIIntent(type=IntentType.CANCEL)


def intent_confirm(yes: bool) -> UIIntent:
    t = IntentType.CONFIRM_YES if yes else IntentType.CONFIRM_NO
    return UIIntent(type=t)


def intent_set_layout(mode: str) -> UIIntent:
    return UIIntent(type=IntentType.SET_LAYOUT, payload={"mode": mode})


def intent_switch_model(model: str) -> UIIntent:
    return UIIntent(type=IntentType.SWITCH_MODEL, payload={"model": model})


def intent_switch_provider(provider: str) -> UIIntent:
    return UIIntent(type=IntentType.SWITCH_PROVIDER, payload={"provider": provider})


def intent_switch_harness(harness_type: str) -> UIIntent:
    return UIIntent(type=IntentType.SWITCH_HARNESS, payload={"harness": harness_type})


def intent_resize(width: int, height: int) -> UIIntent:
    return UIIntent(type=IntentType.RESIZE, payload={"width": width, "height": height})
