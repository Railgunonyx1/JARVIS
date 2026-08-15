"""Central style vocabulary for the JARVIS MK-X terminal UI.

Keeps the Rich/ANSI look consistent across the REPL, the status clock and any
future panels. Matches the colours already in use around the CLI (cyan brand,
green ok, yellow warn, red err, magenta provider, dim metadata).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from rich.style import Style
from rich.theme import Theme

# Brand / identity
BRAND = "bold cyan"
TITLE = "bold cyan"

# REPL input
PROMPT_TEXT = "JARVIS> "
PROMPT_STYLE = "bold"
PROMPT_HINT = "dim"

# Status
OK = "green"
WARN = "yellow"
ERR = "red"
BUSY = "bold red blink"
DIM = "dim"
PROVIDER = "magenta"

# Panels
BORDER_CORE = "cyan"
BORDER_CONTEXT = "blue"
BORDER_MEMORY = "magenta"
BORDER_OBSERVER = "green"


@dataclass(frozen=True)
class JarvisColors:
    """Semantic color tokens. Keep the palette small and consistent."""

    # Core identity
    primary: str = "bright_cyan"
    secondary: str = "cyan"
    accent: str = "bright_white"

    # Status
    success: str = "bright_green"
    warning: str = "yellow"
    error: str = "bright_red"
    info: str = "bright_blue"

    # UI chrome
    border: str = "bright_black"
    muted: str = "bright_black"
    dim: str = "dim"
    highlight: str = "white"

    # Agent / tool states
    running: str = "bright_yellow"
    planned: str = "bright_black"
    done: str = "bright_green"
    failed: str = "bright_red"
    active: str = "bright_cyan"

    # Conversation
    user: str = "bright_white"
    agent: str = "bright_cyan"
    tool: str = "yellow"
    system: str = "bright_black"


COLORS = JarvisColors()


def build_rich_theme() -> Theme:
    """Rich Theme used by the Console."""
    return Theme(
        {
            "jarvis.primary": COLORS.primary,
            "jarvis.secondary": COLORS.secondary,
            "jarvis.accent": COLORS.accent,
            "jarvis.success": COLORS.success,
            "jarvis.warning": COLORS.warning,
            "jarvis.error": COLORS.error,
            "jarvis.info": COLORS.info,
            "jarvis.border": COLORS.border,
            "jarvis.muted": COLORS.muted,
            "jarvis.dim": COLORS.dim,
            "jarvis.user": COLORS.user,
            "jarvis.agent": COLORS.agent,
            "jarvis.tool": COLORS.tool,
            "jarvis.system": COLORS.system,
            "jarvis.running": COLORS.running,
            "jarvis.done": COLORS.done,
            "jarvis.failed": COLORS.failed,
            "jarvis.active": COLORS.active,
            # Markdown helpers
            "markdown.code": "bright_white on black",
            "markdown.h1": "bold bright_cyan",
            "markdown.h2": "bold cyan",
            "markdown.h3": "bold white",
        }
    )


# Panel titles and status indicators
PANEL_TITLES: Dict[str, str] = {
    "plan": "PLAN",
    "activity": "ACTIVITY",
    "code": "CODE",
    "memory": "MEMORY",
    "context": "CONTEXT",
    "audit": "AUDIT",
    "conversation": "CONVERSATION",
}


# Status symbols (ASCII-safe fallbacks available)
SYMBOLS = {
    "running": "●",
    "done": "✓",
    "failed": "✗",
    "planned": "○",
    "current": "→",
    "bullet": "•",
    "prompt": ">",
    "separator": "·",
}


# ASCII-safe alternatives for non-Unicode terminals
SYMBOLS_ASCII = {
    "running": "*",
    "done": "+",
    "failed": "x",
    "planned": "o",
    "current": ">",
    "bullet": "-",
    "prompt": ">",
    "separator": "|",
}


def get_symbols(unicode_supported: bool = True) -> Dict[str, str]:
    return SYMBOLS if unicode_supported else SYMBOLS_ASCII
