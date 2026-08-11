"""Renderable helpers for the JARVIS MK-X terminal.

Assistant responses are usually Markdown; the Rich ``Markdown`` renderable adds
syntax highlighting for code blocks and neat lists. Plain text stays plain, and
the ``--json`` output path is never routed through here.
"""

from __future__ import annotations

import logging

from rich.markdown import Markdown
from rich.text import Text

logger = logging.getLogger("jarvis.cli.renderer")

CODE_THEME = "solarized-dark"


def render_markdown(text: str, *, plain: bool = False):
    """Turn an assistant response into a Rich renderable.

    Args:
        text: raw assistant output.
        plain: force plain-text rendering (no Markdown interpretation).
    """
    if plain or not _looks_like_markdown(text):
        return Text(text)
    return Markdown(text, code_theme=CODE_THEME)


def _looks_like_markdown(text: str) -> bool:
    """Cheap heuristic: only interpret as Markdown when it looks like it.

    Avoids mangling one-line answers or plain prose with stray '#'/'*' that a
    naive renderer would choke on, and keeps rendering cheap for JSON/plain
    output.
    """
    stripped = text.lstrip()
    if not stripped:
        return False
    if "\n" not in text:
        # Single-line answers: only treat explicit emphasis/links/code as MD.
        return bool(stripped.startswith(("#", "- ", "* ", "> ", "```")))
    return True
