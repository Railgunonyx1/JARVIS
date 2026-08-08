"""Dialogue State Machine — tracks conversation flow and turn management."""

import time
import logging
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger("jarvis.dialogue")


class DialogueState(Enum):
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    RESPONDING = auto()
    WAITING = auto()
    ERROR = auto()


# Valid transitions: state -> {event -> new_state}
_TRANSITIONS = {
    DialogueState.IDLE:        {"wake_detected": DialogueState.LISTENING, "speech_input": DialogueState.PROCESSING},
    DialogueState.LISTENING:   {"speech_input": DialogueState.PROCESSING, "timeout": DialogueState.IDLE},
    DialogueState.PROCESSING:  {"processing_done": DialogueState.RESPONDING, "error": DialogueState.ERROR},
    DialogueState.RESPONDING:  {"reset": DialogueState.IDLE, "speech_input": DialogueState.PROCESSING, "await_followup": DialogueState.WAITING},
    DialogueState.WAITING:     {"speech_input": DialogueState.PROCESSING, "timeout": DialogueState.IDLE, "reset": DialogueState.IDLE},
    DialogueState.ERROR:       {"reset": DialogueState.IDLE},
}


class DialogueStateMachine:
    WAIT_TIMEOUT_S = 8.0

    def __init__(self):
        self.state = DialogueState.IDLE
        self._entered_at = time.time()
        self._last_input = ""

    def transition(self, event: str, data: Optional[dict] = None) -> DialogueState:
        valid = _TRANSITIONS.get(self.state, {})
        if event not in valid:
            logger.warning("Invalid transition: %s in %s", event, self.state.name)
            return self.state
        old = self.state
        self.state = valid[event]
        self._entered_at = time.time()
        if data:
            self._last_input = data.get("text", self._last_input)
        logger.info("Dialogue: %s -> %s", old.name, self.state.name)
        return self.state

    @property
    def time_in_state(self) -> float:
        return time.time() - self._entered_at

    @property
    def should_timeout(self) -> bool:
        return self.state == DialogueState.WAITING and self.time_in_state > self.WAIT_TIMEOUT_S

    def reset(self):
        self.transition("reset")
        self._last_input = ""
