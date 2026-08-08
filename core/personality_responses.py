"""Deterministic response generator — no LLM needed for simple intents."""

import datetime
from typing import Optional
from core.intent_router import Intent
from core.personality import PersonalityEngine


def generate_deterministic_response(
    intent: Intent, text: str, personality: PersonalityEngine, memory_facts: Optional[list] = None,
) -> Optional[str]:
    """Returns a response for deterministic intents, or None if LLM is needed."""
    n = intent.name

    if n == "system.exit":     return personality.get_exit_message()
    if n == "system.clear":    return "Session cleared. Starting fresh."
    if n == "system.config":   return "Configuration panel not yet available in MK-X."
    if n == "query.time":      return datetime.datetime.now().strftime("It's %I:%M %p.")
    if n == "query.date":      return datetime.datetime.now().strftime("Today is %A, %B %d, %Y.")
    if n == "query.weather":   return f"I don't have weather API access yet. Check weather manually for now."
    if n == "query.status":    return None  # Handled by _handle_action
    if n == "meta.greet":      return personality.get_greeting()
    if n == "meta.howareyou":  return personality.get_how_are_you()
    if n == "meta.thanks":     return "You're welcome."
    if n == "meta.help":       return "I can help with: time, date, memories, web search, opening apps, notes, reminders, and conversation. Try voice commands or type directly."

    if n == "memory.store":
        fact = intent.entities.get("fact", "")
        return f"I'll remember that: {fact}" if fact else "What would you like me to remember?"

    if n == "memory.query":
        if memory_facts:
            return f"Here's what I know about you: {'; '.join(memory_facts[:5])}"
        return "I don't have any stored memories about you yet."

    if n in ("action.open", "action.search", "action.research", "action.calculate", "action.reminder", "action.note"):
        return None  # Handled by _handle_action

    return None  # Unknown — let LLM handle
