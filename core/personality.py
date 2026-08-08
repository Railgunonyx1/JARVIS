"""Personality layer — mood tracking, greetings, time awareness."""

import random
import time
from dataclasses import dataclass
from enum import Enum


class Mood(Enum):
    NEUTRAL = "neutral"
    CHEERFUL = "cheerful"
    FOCUSED = "focused"


class TimeOfDay(Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


def _get_time_of_day() -> TimeOfDay:
    h = time.localtime().tm_hour
    if 5 <= h < 12:   return TimeOfDay.MORNING
    if 12 <= h < 17:  return TimeOfDay.AFTERNOON
    if 17 <= h < 21:  return TimeOfDay.EVENING
    return TimeOfDay.NIGHT


_GREETINGS = {
    TimeOfDay.MORNING:   ["Good morning, Aayan.", "Morning. Ready when you are.", "Good morning. What's on the agenda?"],
    TimeOfDay.AFTERNOON: ["Good afternoon.", "Afternoon. How can I help?", "Good afternoon, Aayan."],
    TimeOfDay.EVENING:   ["Good evening.", "Evening. What do you need?", "Good evening, Aayan."],
    TimeOfDay.NIGHT:     ["Good evening. Working late?", "Night mode active.", "Still at it? How can I help?"],
}

_HOW_ARE_YOU = [
    "I'm running at full capacity. All systems nominal.",
    "Systems are healthy. Ready for your next command.",
    "All green. CPU's cool, memory's fine. How can I help?",
    "Operational and standing by. What do you need?",
    "Feeling sharp. What's next?",
]

_EXIT = ["Goodbye, Aayan. Shutting down.", "Shutting down. See you next time.", "Goodbye.", "Powering down. Take care."]


@dataclass
class PersonalityState:
    mood: Mood = Mood.NEUTRAL
    interaction_count: int = 0
    last_interaction: float = 0.0


class PersonalityEngine:
    def __init__(self):
        self.state = PersonalityState()
        self._tod = _get_time_of_day()

    def refresh_time(self):
        self._tod = _get_time_of_day()

    def get_greeting(self) -> str:
        self.refresh_time()
        self.state.interaction_count += 1
        self.state.last_interaction = time.time()
        return random.choice(_GREETINGS[self._tod])

    def get_how_are_you(self) -> str:
        return random.choice(_HOW_ARE_YOU)

    def get_exit_message(self) -> str:
        return random.choice(_EXIT)

    def get_thinking_phrase(self) -> str:
        return random.choice(["Let me think...", "Processing...", "One moment...", "Working on it..."])

    def get_cant_help(self) -> str:
        return random.choice(["I'm not sure I can help with that yet.", "That's beyond my current capabilities."])

    def get_time_greeting(self) -> str:
        self.refresh_time()
        return {"morning": "It is currently morning.", "afternoon": "It is currently afternoon.",
                "evening": "It is currently evening.", "night": "It is currently late at night."}[self._tod.value]

    def style_response(self, response: str, intent: str) -> str:
        return response  # Keep meta/system responses as-is

    def on_interaction_complete(self, success: bool):
        self.state.mood = Mood.CHEERFUL if success else Mood.NEUTRAL
        self.state.last_interaction = time.time()
