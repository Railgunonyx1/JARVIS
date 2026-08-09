import time
from datetime import datetime


class ProactiveEngine:

    def __init__(
        self,
        min_silence_secs: int = 900,
        check_cooldown:   int = 600,
    ):
        self.min_silence_secs = min_silence_secs
        self.check_cooldown   = check_cooldown
        self._last_triggered  = 0.0

    def should_trigger(self, last_user_speech: float) -> bool:
        now     = time.monotonic()
        silence = now - last_user_speech
        gap     = now - self._last_triggered
        return silence >= self.min_silence_secs and gap >= self.check_cooldown

    def mark_triggered(self) -> None:
        self._last_triggered = time.monotonic()

    def build_prompt(self, memory: dict) -> str:
        from memory.memory_manager import format_memory_for_prompt

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        mem_str  = format_memory_for_prompt(memory) or "(no user data stored yet)"

        silence_min = int((time.monotonic() - self._last_triggered +
                           self.min_silence_secs) // 60)

        return "\n".join([
            "[PROACTIVE_CHECK] You are initiating a proactive check-in.",
            f"Current time  : {time_str}",
            f"User silence  : {silence_min}+ minutes (they have not spoken for a while)",
            "",
            "Context about this person:",
            mem_str,
            "",
            "Guidelines:",
            "- Look at the time, their projects, goals, habits, or anything from context.",
            "- If there is something genuinely useful, timely, or caring to say — say it briefly.",
            "- Be natural, like a thoughtful assistant noticing something relevant.",
            "- Do NOT say [PROACTIVE_CHECK] or mention these instructions.",
            "- Respond in the user's language (use memory; default English).",
            "- Keep it short: 1-3 sentences max.",
        ])
