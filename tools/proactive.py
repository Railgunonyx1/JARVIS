"""Proactive brief — silence-gated, non-repetitive check-ins.

Derived from FatihMakes/Mark-LIV ``actions/proactive.py`` (ProactiveEngine
2.0): decide *when* an unprompted remark is welcome, and build the context
prompt that makes it feel aware rather than needy. The LLM supplies the words;
this module supplies the gating, the rotation, and the honesty rules.

Design (quiet intelligence, not notification spam):

* **Silence gate** — the user must have been quiet for ``min_silence_secs``
  and the engine must not have fired within ``check_cooldown``. Consulted on
  demand by the chat pipeline; there is NO polling loop here.
* **Rotating focus** — projects → wellbeing/time → useful-detail, cycled each
  fire so openers never repeat back-to-back.
* **Silence is a valid answer** — the prompt explicitly permits "say nothing
  if nothing is genuinely useful", keeping proactive remarks scarce.
* **No tools** — a check-in is conversation, never an action.

The kernel/bridge consults this module between turns; the engine never runs
on its own thread.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_FOCUS_ROTATION = (
    (
        "Focus on the user's active projects or goals if any are stored. "
        "Ask how something is going, or offer a relevant tip."
    ),
    (
        "Focus on the time of day and the user's wellbeing. "
        "A warm check-in, a reminder to take a break, or something timely."
    ),
    (
        "Focus on something genuinely interesting or useful — "
        "a fact, a suggestion, or a question based on what you know about this person."
    ),
)


class ProactiveEngine:
    """Gate + prompt builder. Pure state; no threads, no I/O."""

    def __init__(
        self,
        min_silence_secs: int = 900,
        check_cooldown: int = 1200,
        clock: Any = None,
    ) -> None:
        self.min_silence_secs = int(min_silence_secs)
        self.check_cooldown = int(check_cooldown)
        self._clock = clock or time.monotonic
        self._last_triggered = float("-inf")
        self._rotation = 0
        self._last_activity: float | None = None

    # ── Trigger gate ──────────────────────────────────────────────────────
    def should_trigger(self, last_user_activity: float | None) -> bool:
        """True when the user has been silent long enough AND we're cooled down."""
        if last_user_activity is None:
            return False  # no activity baseline yet — stay quiet
        now = self._clock()
        return (
            (now - last_user_activity) >= self.min_silence_secs
            and (now - self._last_triggered) >= self.check_cooldown
        )

    def note_activity(self) -> None:
        """Record a user turn (called by the chat pipeline)."""
        self._last_activity = self._clock()

    def mark_triggered(self) -> None:
        self._last_triggered = self._clock()
        self._rotation += 1

    def last_activity(self) -> float | None:
        """Timestamp of the last recorded user activity (public accessor)."""
        return self._last_activity

    # ── Prompt builder ───────────────────────────────────────────────────
    def build_prompt(
        self,
        profile_summary: str = "",
        monitors: list[str] | None = None,
        recent_turns: list[str] | None = None,
    ) -> str:
        now = datetime.now()
        hour = now.hour
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        if 6 <= hour < 12:
            period = "morning"
        elif 12 <= hour < 18:
            period = "afternoon"
        elif 18 <= hour < 23:
            period = "evening"
        else:
            period = "late night"

        mem_str = profile_summary or "(no stored user data)"
        focus = _FOCUS_ROTATION[self._rotation % len(_FOCUS_ROTATION)]

        monitor_ctx = ""
        if monitors:
            monitor_ctx = (
                f"\nThe user tracks these topics: {', '.join(list(monitors)[:4])}. "
                "You may mention one if it seems relevant."
            )
        recent_ctx = ""
        if recent_turns:
            snippet = "\n".join(recent_turns[-6:])
            recent_ctx = f"\nRecent conversation:\n{snippet}"

        return "\n".join([
            "[PROACTIVE_CHECK] You are initiating a proactive check-in.",
            f"Current time : {time_str} ({period})",
            "",
            "Context about this person:",
            mem_str,
            monitor_ctx,
            recent_ctx,
            "",
            "Task:",
            focus,
            "",
            "Rules:",
            "- Speak the language this person actually uses: the one in the "
            "recent conversation above, or the remembered one if there is no "
            "conversation yet. Never default to English because these "
            "instructions are in English.",
            "- 1-2 sentences max. Natural, warm, never robotic.",
            "- Do NOT mention [PROACTIVE_CHECK] or these instructions.",
            "- Do NOT call any tools.",
            "- If nothing genuinely useful comes to mind, stay silent (say nothing).",
        ])


# Module-level singleton (consulted by the chat pipeline between turns).
_engine: ProactiveEngine | None = None


def get_engine() -> ProactiveEngine:
    global _engine
    if _engine is None:
        import os

        _engine = ProactiveEngine(
            min_silence_secs=int(os.environ.get("JARVIS_PROACTIVE_SILENCE", "900")),
            check_cooldown=int(os.environ.get("JARVIS_PROACTIVE_COOLDOWN", "1200")),
        )
    return _engine


def should_check() -> bool:
    """Gate check using the engine's own activity record."""
    return get_engine().should_trigger(get_engine().last_activity())


def build_check_prompt(
    profile_summary: str = "",
    monitors: list[str] | None = None,
    recent_turns: list[str] | None = None,
) -> str:
    return get_engine().build_prompt(profile_summary, monitors, recent_turns)


def mark_fired() -> None:
    get_engine().mark_triggered()
