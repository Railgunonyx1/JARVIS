"""Central style vocabulary for the JARVIS MK-X terminal UI.

Keeps the Rich/ANSI look consistent across the REPL, the status clock and any
future panels. Matches the colours already in use around the CLI (cyan brand,
green ok, yellow warn, red err, magenta provider, dim metadata).
"""

from __future__ import annotations

# Brand / identity
BRAND = "bold cyan"
TITLE = "bold cyan"
PROMPT = "bold"
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
