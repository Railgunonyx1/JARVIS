"""Central style vocabulary for the JARVIS MK-X terminal UI.

Keeps the Rich/ANSI look consistent across the REPL, the status clock and any
future panels. Matches the colours already in use around the CLI (cyan brand,
green ok, yellow warn, red err, magenta provider, dim metadata).
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.box import DOUBLE, HEAVY, MINIMAL, ROUNDED, SIMPLE
from rich.theme import Theme


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

    # UI chrome — grey (not bright_black which is invisible on dark themes)
    border: str = "grey50"
    border_focus: str = "bright_cyan"
    muted: str = "grey50"
    dim: str = "dim"
    highlight: str = "white"

    # Agent / tool states
    running: str = "bright_yellow"
    planned: str = "grey50"
    done: str = "bright_green"
    failed: str = "bright_red"
    active: str = "bright_cyan"

    # Conversation — Claude Code aesthetic
    user: str = "bold bright_white"
    user_label: str = "bold bright_cyan"
    agent: str = "bright_cyan"
    agent_label: str = "bold"
    tool: str = "yellow"
    system: str = "grey50"


COLORS = JarvisColors()

# Backward-compatible constant (prefer Renderer.print_prompt())
PROMPT_TEXT = "> "


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
            "jarvis.user_label": COLORS.user_label,
            "jarvis.agent": COLORS.agent,
            "jarvis.agent_label": COLORS.agent_label,
            "jarvis.tool": COLORS.tool,
            "jarvis.system": COLORS.system,
            "jarvis.running": COLORS.running,
            "jarvis.done": COLORS.done,
            "jarvis.failed": COLORS.failed,
            "jarvis.active": COLORS.active,
            # Markdown helpers
            "markdown.code": "bright_white on grey11",
            "markdown.h1": "bold bright_cyan",
            "markdown.h2": "bold cyan",
            "markdown.h3": "bold white",
        }
    )


# Panel titles and status indicators
PANEL_TITLES: dict[str, str] = {
    "plan": "PLAN",
    "activity": "ACTIVITY",
    "code": "CODE",
    "memory": "MEMORY",
    "context": "CONTEXT",
    "audit": "AUDIT",
    "conversation": "CONVERSATION",
}


# Box styles for different panel types
class BoxStyles:
    """Consistent box styles for different UI contexts."""
    HEADER = HEAVY          # Status bar — strong, authoritative
    PANEL = ROUNDED         # Side panels — modern, clean
    PROMPT = MINIMAL        # Input area — lightweight
    ACTIVITY = SIMPLE       # Activity stream — unobtrusive
    CONFIRMATION = DOUBLE   # Security dialogs — attention-grabbing
    CODE = MINIMAL          # Code blocks — no visual noise


# Status symbols (Unicode preferred, ASCII fallback)
SYMBOLS = {
    "running": "\u25cf",    # ●
    "done": "\u2713",       # ✓
    "failed": "\u2717",     # ✗
    "planned": "\u25cb",    # ○
    "current": "\u2192",    # →
    "bullet": "\u2022",     # •
    "prompt": "\u203a",     # ›
    "separator": "\u00b7",  # ·
    "star": "\u2605",       # ★
    "arrow_right": "\u25b6",# ▶
    "ellipsis": "\u2026",   # …
    "bar_full": "\u2588",   # █
    "bar_empty": "\u2591",  # ░
    "diamond": "\u25c6",    # ◆
    "sparkle": "\u2728",    # ✨
    "thinking": "\u25d8",   # ◘
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
    "star": "*",
    "arrow_right": ">",
    "ellipsis": "...",
    "bar_full": "#",
    "bar_empty": "-",
    "diamond": "+",
    "sparkle": "*",
    "thinking": "*",
}


def get_symbols(unicode_supported: bool = True) -> dict[str, str]:
    return SYMBOLS if unicode_supported else SYMBOLS_ASCII
