"""Context Engine — conversation history, user profile, situational context.
Uses write-behind cache: profile saves are queued and flushed every 30s."""

import datetime
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

# Token-efficient prompt compression
from core.prompt_compressor import compress_prompt, compress_tool_output, _split_into_sections


@dataclass
class ContextFrame:
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    intent: str = ""
    confidence: float = 0.0


@dataclass
class UserProfile:
    name: str = "Aayan"
    preferences: dict = field(default_factory=dict)
    facts: list[str] = field(default_factory=list)
    timezone: str = "Asia/Kolkata"


class ContextEngine:
    def __init__(self, config: dict, data_dir: Path | None = None):
        # Read config with defaults
        self.MAX_HISTORY = config.get("max_history", 20)
        self.COMPRESS_THRESHOLD = config.get("compress_threshold", 15)
        self.MAX_SUMMARY_TURNS = config.get("max_summary_turns", 5)
        self._FLUSH_INTERVAL = config.get("flush_interval", 30.0)
        self._timezone = config.get("timezone", "Asia/Kolkata")

        self._data_dir = data_dir or Path.home() / ".jarvis" / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self.history: list[ContextFrame] = []
        self.user = UserProfile(timezone=self._timezone)
        self.active_topic: str = ""
        self.session_start: float = time.time()
        self._conversation_summary: str = ""
        self._messages_cache: list[dict] | None = None
        self._messages_cache_len: int = 0
        self._load_profile()

        # Write-behind cache
        self._dirty = False
        self._flush_lock = threading.Lock()
        self._flush_timer: threading.Timer | None = None

    def add_turn(self, role: str, content: str, **kwargs) -> ContextFrame:
        frame = ContextFrame(role=role, content=content, **kwargs)
        self.history.append(frame)
        self._messages_cache = None  # invalidate cache

        # Auto-compress when history gets long
        if len(self.history) > self.COMPRESS_THRESHOLD:
            self._compress_old_turns()

        return frame

    def _compress_old_turns(self):
        """Compress older turns into a summary, keeping recent turns verbatim."""
        if len(self.history) <= self.MAX_SUMMARY_TURNS:
            return

        # Split: old turns to summarize, recent turns to keep
        old_turns = self.history[:-self.MAX_SUMMARY_TURNS]
        recent_turns = self.history[-self.MAX_SUMMARY_TURNS:]

        # Build prompt from old turns and compress
        old_prompt = "\n".join([f"{'User' if f.role == 'user' else 'JARVIS'}: {f.content}"
                                for f in old_turns])
        
        # Use segment-aware prompt compression
        compressed_prompt = compress_prompt(
            old_prompt,
            system_retain=0.7,
            fewshot_retain=0.5,
            rag_retain=0.3,
            code_retain=0.5,
        )
        
        # Build summary from compressed prompt
        summary_parts = []
        if self._conversation_summary:
            summary_parts.append(self._conversation_summary)
        summary_parts.append(f"[Compressed context]: {compressed_prompt}")

        self._conversation_summary = " | ".join(summary_parts)

        # Keep only recent turns
        self.history = recent_turns
        self._messages_cache = None  # invalidate cache
        logger.info("Compressed history: summary=%d chars, %d recent turns kept",
                     len(self._conversation_summary), len(recent_turns))

    def get_messages(self, max_turns: int | None = None) -> list[dict]:
        # Return cached version if history hasn't changed
        effective_max = max_turns or self.MAX_HISTORY
        if (self._messages_cache is not None
                and self._messages_cache_len == len(self.history)
                and effective_max == self.MAX_HISTORY):
            return self._messages_cache

        messages = []

        # Inject compressed summary as first context message if available
        if self._conversation_summary:
            messages.append({
                "role": "system",
                "content": f"[Conversation so far]: {self._conversation_summary}"
            })

        # Add recent turns
        turns = self.history[-effective_max:]
        messages.extend([{"role": f.role, "content": f.content} for f in turns])

        # Cache for next call
        if effective_max == self.MAX_HISTORY:
            self._messages_cache = messages
            self._messages_cache_len = len(self.history)

        return messages

    def get_context_summary(self) -> str:
        now = datetime.datetime.now()
        hour = now.hour
        period = "night" if hour < 6 else "morning" if hour < 12 else "afternoon" if hour < 17 else "evening" if hour < 21 else "night"
        parts = [
            f"User: {self.user.name}",
            f"Time: {now.strftime('%I:%M %p, %A, %B %d')}",
            f"Period: {period.title()}",
        ]
        if self.active_topic:
            parts.append(f"Topic: {self.active_topic}")
        if len(self.history) > 5:
            intents = {f.intent for f in self.history[-5:] if f.intent}
            if intents:
                parts.append(f"Recent: {', '.join(intents)}")
        if self.user.preferences:
            parts.append(f"Prefs: {', '.join(f'{k}={v}' for k, v in self.user.preferences.items())}")
        return "\n".join(parts)

    def add_fact(self, fact: str):
        if fact not in self.user.facts:
            self.user.facts.append(fact)
            self._schedule_save()

    def clear_history(self):
        self.history.clear()
        self.active_topic = ""
        self.session_start = time.time()

    def _schedule_save(self):
        """Queue a profile save — debounced to max once per FLUSH_INTERVAL."""
        self._dirty = True
        with self._flush_lock:
            if self._flush_timer and self._flush_timer.is_alive():
                return  # already scheduled
            self._flush_timer = threading.Timer(self._FLUSH_INTERVAL, self._flush_to_disk)
            self._flush_timer.daemon = True
            self._flush_timer.start()

    def _flush_to_disk(self):
        """Write profile to disk if dirty."""
        if not self._dirty:
            return
        with self._flush_lock:
            try:
                (self._data_dir / "user_profile.json").write_text(json.dumps({
                    "name": self.user.name, "preferences": self.user.preferences,
                    "facts": self.user.facts, "timezone": self.user.timezone,
                }, indent=2))
                self._dirty = False
            except Exception as e:
                logger.error("Profile save failed: %s", e)

    def flush(self):
        """Force immediate flush (called on shutdown)."""
        self._flush_to_disk()

    def _save_profile(self):
        """Immediate save — kept for backward compatibility."""
        self._dirty = True
        self._flush_to_disk()

    def _load_profile(self):
        path = self._data_dir / "user_profile.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.user.name = data.get("name", "Aayan")
                self.user.preferences = data.get("preferences", {})
                self.user.facts = data.get("facts", [])
                self.user.timezone = data.get("timezone", "Asia/Kolkata")
            except Exception as e:
                logger.error("Profile load failed: %s", e)
