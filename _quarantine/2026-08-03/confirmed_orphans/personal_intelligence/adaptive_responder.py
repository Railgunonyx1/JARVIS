"""Adaptive Responder — Response style selection and proactive suggestions."""

import time
import logging
import threading
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

from personal_intelligence.user_model import UserModel

logger = logging.getLogger("jarvis.personal_intelligence.adaptive_responder")

_STYLE_PROFILES = {
    "terse": {
        "max_words": 30,
        "greeting": False,
        "examples": True,
        "preamble": False,
        "emoji": False,
    },
    "neutral": {
        "max_words": 80,
        "greeting": True,
        "examples": True,
        "preamble": True,
        "emoji": False,
    },
    "verbose": {
        "max_words": 200,
        "greeting": True,
        "examples": True,
        "preamble": True,
        "emoji": False,
    },
    "formal": {
        "max_words": 100,
        "greeting": True,
        "examples": False,
        "preamble": True,
        "emoji": False,
    },
    "casual": {
        "max_words": 60,
        "greeting": True,
        "examples": True,
        "preamble": False,
        "emoji": True,
    },
    "professional": {
        "max_words": 100,
        "greeting": False,
        "examples": True,
        "preamble": False,
        "emoji": False,
    },
    "quiet": {
        "max_words": 40,
        "greeting": False,
        "examples": False,
        "preamble": False,
        "emoji": False,
    },
    "energetic": {
        "max_words": 80,
        "greeting": True,
        "examples": True,
        "preamble": True,
        "emoji": False,
    },
    "focused": {
        "max_words": 50,
        "greeting": False,
        "examples": True,
        "preamble": False,
        "emoji": False,
    },
    "relaxed": {
        "max_words": 80,
        "greeting": True,
        "examples": True,
        "preamble": True,
        "emoji": False,
    },
    "detailed": {
        "max_words": 200,
        "greeting": True,
        "examples": True,
        "preamble": True,
        "emoji": False,
    },
    "polite": {
        "max_words": 100,
        "greeting": True,
        "examples": True,
        "preamble": True,
        "emoji": False,
    },
}

_INTENT_STYLE_OVERRIDES = {
    "system.exit": "neutral",
    "system.clear": "neutral",
    "meta.help": "neutral",
    "meta.greet": "casual",
    "meta.howareyou": "casual",
    "meta.thanks": "casual",
    "query.time": "terse",
    "query.date": "terse",
}

_PROACTIVE_SUGGESTIONS = {
    "query.time": [
        "Want me to set a reminder?",
        "Need to schedule something?",
    ],
    "query.weather": [
        "Should I check the forecast for tomorrow too?",
    ],
    "vision.screen_capture": [
        "Want me to find something specific on screen?",
    ],
    "action.browser": [
        "Want me to bookmark this?",
        "Need me to search for something related?",
    ],
    "general.chat": [],
}

_MORNING_SUGGESTIONS = [
    "Want me to check your schedule?",
    "Should I read the weather forecast?",
    "Need any files organized?",
]

_EVENING_SUGGESTIONS = [
    "Want me to review what we accomplished today?",
    "Should I set any reminders for tomorrow?",
]


@dataclass
class ResponseDirective:
    style: str
    max_words: int
    include_greeting: bool
    include_examples: bool
    include_preamble: bool
    include_emoji: bool
    proactive_hint: str
    confidence: float


class AdaptiveResponder:
    def __init__(self, user_model: UserModel):
        self._user_model = user_model
        self._recent_intents: list[str] = []
        self._recent_times: list[float] = []
        self._topic_memory: dict[str, int] = {}
        self._lock = threading.Lock()

    def get_directive(
        self,
        text: str,
        intent: str,
        context: str = "",
    ) -> ResponseDirective:
        tone_pref = self._user_model.get_preference("tone")
        verbosity_pref = self._user_model.get_preference("verbosity")

        if intent in _INTENT_STYLE_OVERRIDES:
            style_name = _INTENT_STYLE_OVERRIDES[intent]
        elif tone_pref and tone_pref.decayed_confidence() > 0.3:
            style_name = tone_pref.value
        else:
            style_name = self._user_model.get_style_for_context(context)

        if verbosity_pref and verbosity_pref.decayed_confidence() > 0.3:
            style_name = verbosity_pref.value

        profile = _STYLE_PROFILES.get(style_name, _STYLE_PROFILES["neutral"])

        topic_familiarity = self._get_topic_familiarity(intent)
        if topic_familiarity > 3:
            max_words = min(profile["max_words"], 40)
        elif topic_familiarity == 0:
            max_words = profile["max_words"]
        else:
            max_words = profile["max_words"]

        proactive = self._get_proactive_hint(intent, text)

        with self._lock:
            self._recent_intents.append(intent)
            self._recent_times.append(time.time())
            if len(self._recent_intents) > 20:
                self._recent_intents = self._recent_intents[-20:]
                self._recent_times = self._recent_times[-20:]

            self._topic_memory[intent] = self._topic_memory.get(intent, 0) + 1

        confidence = 0.7
        if tone_pref:
            confidence = max(confidence, tone_pref.decayed_confidence())

        return ResponseDirective(
            style=style_name,
            max_words=max_words,
            include_greeting=profile["greeting"],
            include_examples=profile["examples"],
            include_preamble=profile["preamble"],
            include_emoji=profile["emoji"],
            proactive_hint=proactive,
            confidence=confidence,
        )

    def _get_topic_familiarity(self, intent: str) -> int:
        with self._lock:
            return self._topic_memory.get(intent, 0)

    def _get_proactive_hint(self, intent: str, text: str) -> str:
        suggestions = _PROACTIVE_SUGGESTIONS.get(intent, [])
        if not suggestions:
            return ""

        hour = datetime.now().hour
        if 6 <= hour < 10 and _MORNING_SUGGESTIONS:
            combined = suggestions + _MORNING_SUGGESTIONS
        elif 18 <= hour < 22 and _EVENING_SUGGESTIONS:
            combined = suggestions + _EVENING_SUGGESTIONS
        else:
            combined = suggestions

        recent_hash = hash(text[:50]) % len(combined) if combined else 0
        return combined[recent_hash] if combined else ""

    def adapt_response(self, response: str, directive: ResponseDirective) -> str:
        if not response:
            return response

        words = response.split()
        if len(words) > directive.max_words:
            truncated = " ".join(words[:directive.max_words])
            last_period = truncated.rfind(".")
            if last_period > len(truncated) * 0.5:
                truncated = truncated[:last_period + 1]
            else:
                truncated += "..."
            response = truncated

        if not directive.include_emoji:
            response = self._strip_emoji(response)

        return response

    def _strip_emoji(self, text: str) -> str:
        result = []
        i = 0
        while i < len(text):
            cp = ord(text[i])
            if cp > 0xFFFF:
                i += 2
                continue
            if 0x2600 <= cp <= 0x27BF or 0x1F600 <= cp <= 0x1F9FF or 0x1F300 <= cp <= 0x1F5FF:
                i += 1
                continue
            result.append(text[i])
            i += 1
        return "".join(result)

    def get_session_summary(self) -> dict:
        with self._lock:
            recent = self._recent_intents[-10:] if self._recent_intents else []
            most_common = {}
            for intent in recent:
                most_common[intent] = most_common.get(intent, 0) + 1

        return {
            "recent_intents": recent,
            "topic_distribution": most_common,
            "total_recent_interactions": len(recent),
            "dominant_topic": max(most_common, key=most_common.get) if most_common else None,
        }

    def reset_session(self) -> None:
        with self._lock:
            self._recent_intents.clear()
            self._recent_times.clear()
            self._topic_memory.clear()
