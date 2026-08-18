"""Intent Router — translates UIIntents into BusEvents and publishes on the bus.

This is the ONLY path from terminal input to core kernel.
The terminal converts keystrokes → UIIntents → IntentRouter → BusEvent → bus.

Architecture:
    Terminal UI -> UIIntent -> IntentRouter -> BusEvent -> Event Bus -> Core Kernel
"""

from __future__ import annotations

import logging
from typing import Any

from jarvis.terminal.events import EventType, make_terminal_event
from jarvis.terminal.intents import IntentType, UIIntent
from runtime.event_bus import EventBus, get_event_bus

logger = logging.getLogger("jarvis.intent_router")


class IntentRouter:
    """Routes UIIntents to the canonical event bus.

    The terminal calls route(intent) for every user action.
    The router converts it to a BusEvent and publishes it on the bus.
    Core kernel subscribers pick it up.
    """

    def __init__(self, bus: EventBus | None = None):
        self._bus = bus or get_event_bus()

    def route(self, intent: UIIntent) -> Any:
        """Convert a UIIntent to a BusEvent and publish.

        Returns the published BusEvent for testing/inspection.
        """
        handler = _INTENT_HANDLERS.get(intent.type)
        if handler is None:
            logger.warning("No handler for intent type %s", intent.type)
            event = make_terminal_event(
                EventType.INTENT_SUBMITTED,
                payload={"intent_type": intent.type.value, **intent.payload},
            )
        else:
            event = handler(intent)

        self._bus.publish(event)
        return event


def _handle_submit(intent: UIIntent) -> Any:
    return make_terminal_event(
        EventType.INTENT_SUBMITTED,
        payload={"text": intent.payload.get("text", "")},
    )


def _handle_cancel(intent: UIIntent) -> Any:
    return make_terminal_event(EventType.INTENT_CANCEL)


def _handle_confirm(intent: UIIntent) -> Any:
    yes = intent.type == IntentType.CONFIRM_YES
    return make_terminal_event(
        EventType.INTENT_CONFIRM,
        payload={"accepted": yes},
    )


def _handle_set_layout(intent: UIIntent) -> Any:
    return make_terminal_event(
        EventType.INTENT_LAYOUT,
        payload={"mode": intent.payload.get("mode", "normal")},
    )


def _handle_switch_model(intent: UIIntent) -> Any:
    return make_terminal_event(
        EventType.INTENT_MODEL_SWITCH,
        payload={"model": intent.payload.get("model", "")},
    )


def _handle_switch_provider(intent: UIIntent) -> Any:
    return make_terminal_event(
        EventType.INTENT_PROVIDER_SWITCH,
        payload={"provider": intent.payload.get("provider", "")},
    )


def _handle_switch_harness(intent: UIIntent) -> Any:
    return make_terminal_event(
        EventType.INTENT_HARNESS_SWITCH,
        payload={"harness": intent.payload.get("harness", "native")},
    )


_INTENT_HANDLERS: dict[IntentType, Any] = {
    IntentType.SUBMIT_MESSAGE: _handle_submit,
    IntentType.CANCEL: _handle_cancel,
    IntentType.CONFIRM_YES: _handle_confirm,
    IntentType.CONFIRM_NO: _handle_confirm,
    IntentType.SET_LAYOUT: _handle_set_layout,
    IntentType.SWITCH_MODEL: _handle_switch_model,
    IntentType.SWITCH_PROVIDER: _handle_switch_provider,
    IntentType.SWITCH_HARNESS: _handle_switch_harness,
}
