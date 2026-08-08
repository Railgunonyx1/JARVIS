"""Desktop GUI Automation & Control module for JARVIS MK-X."""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("jarvis.actions.desktop_automation")


def execute_desktop_action(action: str, parameters: Optional[Dict[str, Any]] = None) -> str:
    """Execute desktop control action (volume, media keys, key shortcuts, windows)."""
    parameters = parameters or {}
    action_lower = action.lower().strip()

    try:
        import pyautogui
        pyautogui.FAILSAFE = True
    except ImportError:
        pyautogui = None

    try:
        if "volume_up" in action_lower or "increase volume" in action_lower:
            if pyautogui:
                for _ in range(5):
                    pyautogui.press("volumeup")
                return "Increased volume, sir."
            return "PyAutoGUI required for volume adjustment."

        if "volume_down" in action_lower or "decrease volume" in action_lower:
            if pyautogui:
                for _ in range(5):
                    pyautogui.press("volumedown")
                return "Decreased volume, sir."
            return "PyAutoGUI required for volume adjustment."

        if "mute" in action_lower:
            if pyautogui:
                pyautogui.press("volumemute")
                return "Toggled volume mute."
            return "PyAutoGUI required for mute."

        if "play" in action_lower or "pause" in action_lower or "media" in action_lower:
            if pyautogui:
                pyautogui.press("playpause")
                return "Toggled media playback."
            return "PyAutoGUI required for media control."

        if "next" in action_lower:
            if pyautogui:
                pyautogui.press("nexttrack")
                return "Skipped to next track."

        if "prev" in action_lower:
            if pyautogui:
                pyautogui.press("prevtrack")
                return "Returned to previous track."

        if "minimize" in action_lower or "show desktop" in action_lower:
            if pyautogui:
                pyautogui.hotkey("win", "d")
                return "Showing desktop."

        if "task manager" in action_lower:
            if pyautogui:
                pyautogui.hotkey("ctrl", "shift", "esc")
                return "Opening Task Manager."

        if action_lower == "hotkey" and parameters.get("keys"):
            if pyautogui:
                keys = parameters["keys"]
                if isinstance(keys, str):
                    keys = [k.strip() for k in keys.split("+")]
                pyautogui.hotkey(*keys)
                return f"Pressed hotkey: {'+'.join(keys)}"

        return f"Desktop action '{action}' executed."
    except Exception as e:
        logger.error("Desktop action failed: %s", e)
        return f"Failed to execute desktop action: {e}"
