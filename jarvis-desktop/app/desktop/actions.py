"""Desktop action layer for JARVIS Desktop.

Controlled, permission-aware PC actions. The AI and gestures can only
execute actions registered here — no unrestricted shell execution.

Security model:
  - Actions must be explicitly registered
  - Destructive actions require confirmation
  - All actions are logged
  - No arbitrary command execution from AI text
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable

logger = logging.getLogger("jarvis.desktop.actions")


class ActionRisk(StrEnum):
    SAFE = "safe"           # read-only, no side effects
    LOW = "low"             # minor side effects (volume, brightness)
    MEDIUM = "medium"       # app/window management
    HIGH = "high"           # system-level (shutdown, restart)
    CRITICAL = "critical"   # destructive (delete, format)


@dataclass
class Action:
    """A registered desktop action."""
    name: str
    description: str
    risk: ActionRisk
    handler: Callable
    require_confirmation: bool = False
    category: str = "general"


class DesktopActionLayer:
    """Controlled desktop action layer.

    Usage:
        layer = DesktopActionLayer()
        layer.register("volume_up", "Volume up", ActionRisk.LOW, vol_up_fn)
        layer.execute("volume_up")
    """

    def __init__(self, *, confirmation_handler: Callable[[str], bool] | None = None):
        self._actions: dict[str, Action] = {}
        self._confirmation_handler = confirmation_handler
        self._history: list[dict] = []
        self._register_defaults()

    def register(self, name: str, description: str, risk: ActionRisk,
                 handler: Callable, *, require_confirmation: bool = False,
                 category: str = "general") -> None:
        """Register an action."""
        self._actions[name] = Action(
            name=name, description=description, risk=risk,
            handler=handler, require_confirmation=require_confirmation,
            category=category,
        )

    def unregister(self, name: str) -> None:
        self._actions.pop(name, None)

    def execute(self, name: str, *, confirmed: bool = False) -> bool:
        """Execute a registered action. Returns True on success."""
        action = self._actions.get(name)
        if not action:
            logger.warning("Unknown action: %s", name)
            return False

        if action.require_confirmation and not confirmed:
            if self._confirmation_handler:
                if not self._confirmation_handler(action.name):
                    logger.info("Action %s denied by confirmation", name)
                    self._log(action.name, False, "denied")
                    return False
            else:
                logger.warning("Action %s requires confirmation but no handler wired", name)
                return False

        try:
            action.handler()
            self._log(action.name, True)
            return True
        except Exception as e:
            logger.warning("Action %s failed: %s", name.name, e)
            self._log(action.name, False, str(e)[:200])
            return False

    def _log(self, name: str, success: bool, error: str = "") -> None:
        self._history.append({
            "action": name,
            "success": success,
            "error": error,
            "timestamp": time.time(),
        })
        if len(self._history) > 1000:
            self._history = self._history[-1000:]

    def _register_defaults(self) -> None:
        """Register safe default actions."""
        # Volume control
        self.register("volume_up", "Volume up", ActionRisk.LOW,
                      lambda: self._pactl("set-sink-volume", "@DEFAULT_SINK@", "+5%"),
                      category="media")
        self.register("volume_down", "Volume down", ActionRisk.LOW,
                      lambda: self._pactl("set-sink-volume", "@DEFAULT_SINK@", "-5%"),
                      category="media")
        self.register("volume_mute", "Mute/unmute", ActionRisk.LOW,
                      lambda: self._pactl("set-sink-mute", "@DEFAULT_SINK@", "toggle"),
                      category="media")

        # Media control
        self.register("media_play_pause", "Play/pause", ActionRisk.LOW,
                      lambda: self._playerctl("play-pause"), category="media")
        self.register("media_next", "Next track", ActionRisk.LOW,
                      lambda: self._playerctl("next"), category="media")
        self.register("media_prev", "Previous track", ActionRisk.LOW,
                      lambda: self._playerctl("previous"), category="media")

        # Window management
        self.register("window_close", "Close window", ActionRisk.MEDIUM,
                      lambda: self._wmctrl("-c", ":ACTIVE:"),
                      require_confirmation=True, category="window")
        self.register("window_maximize", "Maximize window", ActionRisk.MEDIUM,
                      lambda: self._wmctrl("-r", ":ACTIVE:", "add", "maximized"),
                      category="window")
        self.register("window_minimize", "Minimize window", ActionRisk.MEDIUM,
                      lambda: self._wmctrl("-r", ":ACTIVE:", "remove", "maximized"),
                      category="window")

        # Application launching
        self.register("app_terminal", "Open terminal", ActionRisk.MEDIUM,
                      lambda: self._launch("foot"), category="app")
        self.register("app_browser", "Open browser", ActionRisk.MEDIUM,
                      lambda: self._launch("firefox"), category="app")

    @staticmethod
    def _pactl(*args: str) -> None:
        subprocess.run(["pactl", *args], capture_output=True, timeout=5)

    @staticmethod
    def _playerctl(*args: str) -> None:
        subprocess.run(["playerctl", *args], capture_output=True, timeout=5)

    @staticmethod
    def _wmctrl(*args: str) -> None:
        subprocess.run(["wmctrl", *args], capture_output=True, timeout=5)

    @staticmethod
    def _launch(cmd: str) -> None:
        subprocess.Popen([cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def get_actions(self, category: str | None = None) -> list[Action]:
        """List registered actions, optionally filtered by category."""
        actions = list(self._actions.values())
        if category:
            actions = [a for a in actions if a.category == category]
        return actions

    def get_action(self, name: str) -> Action | None:
        return self._actions.get(name)

    def get_history(self, limit: int = 50) -> list[dict]:
        return self._history[-limit:]
