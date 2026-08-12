"""Input Control — mouse, keyboard, typing, hotkeys for JARVIS MK-X.

Direct control of all input devices. Move mouse, click, type text, press keys.
"""

import logging

logger = logging.getLogger("jarvis.actions.input_control")


def input_action(action: str, parameters: dict, **kwargs) -> str:
    """Dispatch input control operations."""
    handlers = {
        "mouse_move": _mouse_move,
        "mouse_click": _mouse_click,
        "mouse_double_click": _mouse_double_click,
        "mouse_right_click": _mouse_right_click,
        "mouse_drag": _mouse_drag,
        "mouse_scroll": _mouse_scroll,
        "type_text": _type_text,
        "press_key": _press_key,
        "hotkey": _hotkey,
        "key_down": _key_down,
        "key_up": _key_up,
        "get_mouse_pos": _get_mouse_pos,
        "get_screen_size": _get_screen_size,
        "screenshot": _screenshot,
    }
    handler = handlers.get(action)
    if not handler:
        return f"Unknown input action: {action}"
    try:
        return handler(parameters)
    except Exception as e:
        logger.error("Input action '%s' failed: %s", action, e)
        return f"Input action failed: {e}"


def _mouse_move(params: dict) -> str:
    import pyautogui
    x = int(params.get("x", 0))
    y = int(params.get("y", 0))
    duration = float(params.get("duration", 0.3))
    pyautogui.moveTo(x, y, duration=duration)
    return f"Mouse moved to ({x}, {y})"


def _mouse_click(params: dict) -> str:
    import pyautogui
    x = params.get("x")
    y = params.get("y")
    button = params.get("button", "left")
    clicks = int(params.get("clicks", 1))
    if x is not None and y is not None:
        pyautogui.click(int(x), int(y), clicks=clicks, button=button)
        return f"Clicked ({x}, {y})"
    pyautogui.click(clicks=clicks, button=button)
    return "Clicked at current position"


def _mouse_double_click(params: dict) -> str:
    import pyautogui
    x = params.get("x")
    y = params.get("y")
    if x is not None and y is not None:
        pyautogui.doubleClick(int(x), int(y))
        return f"Double-clicked ({x}, {y})"
    pyautogui.doubleClick()
    return "Double-clicked at current position"


def _mouse_right_click(params: dict) -> str:
    import pyautogui
    x = params.get("x")
    y = params.get("y")
    if x is not None and y is not None:
        pyautogui.rightClick(int(x), int(y))
        return f"Right-clicked ({x}, {y})"
    pyautogui.rightClick()
    return "Right-clicked at current position"


def _mouse_drag(params: dict) -> str:
    import pyautogui
    x1 = int(params.get("x1", 0))
    y1 = int(params.get("y1", 0))
    x2 = int(params.get("x2", 0))
    y2 = int(params.get("y2", 0))
    duration = float(params.get("duration", 0.5))
    pyautogui.moveTo(x1, y1)
    pyautogui.drag(x2 - x1, y2 - y1, duration=duration)
    return f"Dragged from ({x1}, {y1}) to ({x2}, {y2})"


def _mouse_scroll(params: dict) -> str:
    import pyautogui
    clicks = int(params.get("clicks", 3))
    x = params.get("x")
    y = params.get("y")
    if x is not None and y is not None:
        pyautogui.scroll(clicks, x=int(x), y=int(y))
    else:
        pyautogui.scroll(clicks)
    direction = "up" if clicks > 0 else "down"
    return f"Scrolled {direction} {abs(clicks)} clicks"


def _type_text(params: dict) -> str:
    import pyautogui
    text = params.get("text", "")
    interval = float(params.get("interval", 0.02))
    if not text:
        return "No text to type"
    pyautogui.typewrite(text, interval=interval) if text.isascii() else pyautogui.write(text)
    return f"Typed {len(text)} characters"


def _press_key(params: dict) -> str:
    import pyautogui
    key = params.get("key", "")
    presses = int(params.get("presses", 1))
    if not key:
        return "No key specified"
    pyautogui.press(key, presses=presses)
    return f"Pressed {key} x{presses}"


def _hotkey(params: dict) -> str:
    import pyautogui
    keys = params.get("keys", "")
    if not keys:
        return "No keys specified"
    key_list = [k.strip() for k in keys.split("+")]
    pyautogui.hotkey(*key_list)
    return f"Pressed {'+'.join(key_list)}"


def _key_down(params: dict) -> str:
    import pyautogui
    key = params.get("key", "")
    if not key:
        return "No key specified"
    pyautogui.keyDown(key)
    return f"Holding {key}"


def _key_up(params: dict) -> str:
    import pyautogui
    key = params.get("key", "")
    if not key:
        return "No key specified"
    pyautogui.keyUp(key)
    return f"Released {key}"


def _get_mouse_pos(params: dict) -> str:
    import pyautogui
    pos = pyautogui.position()
    return f"Mouse at ({pos.x}, {pos.y})"


def _get_screen_size(params: dict) -> str:
    import pyautogui
    size = pyautogui.size()
    return f"Screen: {size.width}x{size.height}"


def _screenshot(params: dict) -> str:
    from pathlib import Path

    import pyautogui
    save_path = params.get("path", str(Path.home() / "Desktop" / "screenshot.png"))
    region = params.get("region")
    if region:
        r = [int(x) for x in region.split(",")]
        img = pyautogui.screenshot(region=tuple(r))
    else:
        img = pyautogui.screenshot()
    img.save(save_path)
    return f"Screenshot saved to {save_path}"
