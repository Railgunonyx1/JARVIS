"""Sprint 9G -- Responsive layout breakpoints.

Defines terminal width thresholds that control panel visibility.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Breakpoint(enum.Enum):
    NARROW = "narrow"
    MEDIUM = "medium"
    WIDE = "wide"
    ULTRA = "ultra"


@dataclass(frozen=True)
class BreakpointConfig:
    narrow_max: int = 70
    medium_max: int = 90
    wide_max: int = 120


_DEFAULT_CONFIG = BreakpointConfig()


def classify_width(width: int, config: BreakpointConfig | None = None) -> Breakpoint:
    cfg = config or _DEFAULT_CONFIG
    if width <= cfg.narrow_max:
        return Breakpoint.NARROW
    if width <= cfg.medium_max:
        return Breakpoint.MEDIUM
    if width <= cfg.wide_max:
        return Breakpoint.WIDE
    return Breakpoint.ULTRA


def panels_for_breakpoint(bp: Breakpoint) -> list[str]:
    """Return the list of visible panel names for a given breakpoint."""
    base = ["conversation", "status_bar"]
    if bp == Breakpoint.NARROW:
        return base
    if bp == Breakpoint.MEDIUM:
        return base + ["plan"]
    if bp == Breakpoint.WIDE:
        return base + ["plan", "activity"]
    return base + ["plan", "activity", "code", "memory"]


def should_show(bp: Breakpoint, panel: str) -> bool:
    return panel in panels_for_breakpoint(bp)
