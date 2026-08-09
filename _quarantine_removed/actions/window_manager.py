"""Window Manager — focus, snap, close, list windows for JARVIS MK-X.

Uses pyautogui and win32gui for window management.
"""

import logging
from typing import Optional

logger = logging.getLogger("jarvis.actions.window_manager")


def window_action(action: str, parameters: dict, **kwargs) -> str:
    """Dispatch window management operations."""
    handlers = {
        "list": _list_windows,
        "focus": _focus_window,
        "close": _close_window,
        "minimize": _minimize_window,
        "maximize": _maximize_window,
        "restore": _restore_window,
        "snap_left": _snap_left,
        "snap_right": _snap_right,
        "snap_top": _snap_top,
        "snap_bottom": _snap_bottom,
        "fullscreen": _fullscreen,
        "move": _move_window,
        "resize": _resize_window,
        "title": _get_active_title,
    }
    handler = handlers.get(action)
    if not handler:
        return f"Unknown window action: {action}"
    try:
        return handler(parameters)
    except Exception as e:
        logger.error("Window action '%s' failed: %s", action, e)
        return f"Window operation failed: {e}"


def _get_all_windows():
    """Get all visible windows."""
    import win32gui

    windows = []
    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            title = win32gui.GetWindowText(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            windows.append({"hwnd": hwnd, "title": title, "rect": rect})
    win32gui.EnumWindows(callback, None)
    return windows


def _find_window(name: str) -> Optional[int]:
    """Find a window by partial title match."""
    import win32gui

    name_lower = name.lower()
    result = None

    def callback(hwnd, _):
        nonlocal result
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).lower()
            if name_lower in title:
                result = hwnd
    win32gui.EnumWindows(callback, None)
    return result


def _list_windows(params: dict) -> str:
    windows = _get_all_windows()
    if not windows:
        return "No visible windows found"

    lines = []
    for w in windows[:30]:
        title = w["title"][:50]
        lines.append(f"  {title}")

    return f"Visible windows ({len(windows)}):\n" + "\n".join(lines)


def _focus_window(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a window name to focus"

    import win32gui
    import win32con

    hwnd = _find_window(name)
    if not hwnd:
        return f"No window matching '{name}'"

    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        title = win32gui.GetWindowText(hwnd)
        return f"Focused: {title}"
    except Exception as e:
        return f"Failed to focus: {e}"


def _close_window(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a window name to close"

    import win32gui
    import win32con

    hwnd = _find_window(name)
    if not hwnd:
        return f"No window matching '{name}'"

    try:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        title = win32gui.GetWindowText(hwnd)
        return f"Closed: {title}"
    except Exception as e:
        return f"Failed to close: {e}"


def _minimize_window(params: dict) -> str:
    name = params.get("name", "")
    import win32gui
    import win32con

    hwnd = _find_window(name) if name else win32gui.GetForegroundWindow()
    if hwnd:
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        return f"Minimized: {win32gui.GetWindowText(hwnd)}"
    return "No window found"


def _maximize_window(params: dict) -> str:
    name = params.get("name", "")
    import win32gui
    import win32con

    hwnd = _find_window(name) if name else win32gui.GetForegroundWindow()
    if hwnd:
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        return f"Maximized: {win32gui.GetWindowText(hwnd)}"
    return "No window found"


def _restore_window(params: dict) -> str:
    name = params.get("name", "")
    import win32gui
    import win32con

    hwnd = _find_window(name) if name else win32gui.GetForegroundWindow()
    if hwnd:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        return f"Restored: {win32gui.GetWindowText(hwnd)}"
    return "No window found"


def _snap_left(params: dict) -> str:
    import pyautogui
    import win32gui

    hwnd = _find_window(params.get("name", "")) if params.get("name") else win32gui.GetForegroundWindow()
    if hwnd:
        screen_w = pyautogui.size().width
        win32gui.MoveWindow(hwnd, 0, 0, screen_w // 2, pyautogui.size().height, True)
        return f"Snapped left: {win32gui.GetWindowText(hwnd)}"
    return "No window found"


def _snap_right(params: dict) -> str:
    import pyautogui
    import win32gui

    hwnd = _find_window(params.get("name", "")) if params.get("name") else win32gui.GetForegroundWindow()
    if hwnd:
        screen_w = pyautogui.size().width
        screen_h = pyautogui.size().height
        win32gui.MoveWindow(hwnd, screen_w // 2, 0, screen_w // 2, screen_h, True)
        return f"Snapped right: {win32gui.GetWindowText(hwnd)}"
    return "No window found"


def _snap_top(params: dict) -> str:
    import win32gui

    hwnd = _find_window(params.get("name", "")) if params.get("name") else win32gui.GetForegroundWindow()
    if hwnd:
        win32gui.ShowWindow(hwnd, 4)  # SW_MAXIMIZE
        return f"Maximized: {win32gui.GetWindowText(hwnd)}"
    return "No window found"


def _snap_bottom(params: dict) -> str:
    return _minimize_window(params)


def _fullscreen(params: dict) -> str:
    import pyautogui
    import win32gui

    hwnd = _find_window(params.get("name", "")) if params.get("name") else win32gui.GetForegroundWindow()
    if hwnd:
        screen_w, screen_h = pyautogui.size()
        win32gui.MoveWindow(hwnd, 0, 0, screen_w, screen_h, True)
        return f"Fullscreen: {win32gui.GetWindowText(hwnd)}"
    return "No window found"


def _move_window(params: dict) -> str:
    import win32gui

    name = params.get("name", "")
    x = params.get("x", 0)
    y = params.get("y", 0)

    hwnd = _find_window(name) if name else win32gui.GetForegroundWindow()
    if hwnd:
        rect = win32gui.GetWindowRect(hwnd)
        w = rect[2] - rect[0]
        h = rect[3] - rect[1]
        win32gui.MoveWindow(hwnd, int(x), int(y), w, h, True)
        return f"Moved to ({x}, {y})"
    return "No window found"


def _resize_window(params: dict) -> str:
    import win32gui

    name = params.get("name", "")
    w = params.get("width", 800)
    h = params.get("height", 600)

    hwnd = _find_window(name) if name else win32gui.GetForegroundWindow()
    if hwnd:
        rect = win32gui.GetWindowRect(hwnd)
        win32gui.MoveWindow(hwnd, rect[0], rect[1], int(w), int(h), True)
        return f"Resized to {w}x{h}"
    return "No window found"


def _get_active_title(params: dict) -> str:
    import win32gui
    hwnd = win32gui.GetForegroundWindow()
    if hwnd:
        return f"Active window: {win32gui.GetWindowText(hwnd)}"
    return "No active window"
