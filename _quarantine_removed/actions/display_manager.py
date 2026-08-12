"""Display Manager — resolution, monitors, wallpaper for JARVIS MK-X."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("jarvis.actions.display_manager")


def display_action(action: str, parameters: dict, **kwargs) -> str:
    handlers = {
        "resolution": _set_resolution,
        "get_resolution": _get_resolution,
        "monitors": _list_monitors,
        "wallpaper": _set_wallpaper,
        "get_wallpaper": _get_wallpaper,
        "dual_screen": _dual_screen,
        "extend": _extend_screens,
        "mirror": _mirror_screens,
        "primary": _set_primary,
    }
    handler = handlers.get(action)
    if not handler:
        return f"Unknown display action: {action}"
    try:
        return handler(parameters)
    except Exception as e:
        logger.error("Display action '%s' failed: %s", action, e)
        return f"Display operation failed: {e}"


def _ps(cmd: str) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def _get_resolution(params: dict) -> str:
    try:
        import pyautogui
        size = pyautogui.size()
        return f"Resolution: {size.width}x{size.height}"
    except Exception:
        out = _ps("(Get-CimInstance Win32_VideoController).CurrentHorizontalResolution")
        return f"Resolution: {out}" if out else "Could not get resolution"


def _set_resolution(params: dict) -> str:
    w = params.get("width", 1920)
    h = params.get("height", 1080)
    _ps(f'Set-DisplayResolution -Width {w} -Height {h} -Force')
    return f"Resolution set to {w}x{h}"


def _list_monitors(params: dict) -> str:
    out = _ps("Get-CimInstance Win32_DesktopMonitor | Select-Object Name, ScreenWidth, ScreenHeight | Format-Table -AutoSize")
    return out if out else "No monitors detected"


def _set_wallpaper(params: dict) -> str:
    path = params.get("path", "")
    if not path:
        return "Provide a wallpaper path"
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Image not found: {p}"
    import ctypes
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, "WallPaper", 0, winreg.REG_SZ, str(p))
    winreg.CloseKey(key)
    ctypes.windll.user32.SystemParametersInfoW(20, 0, str(p), 3)
    return f"Wallpaper set to {p.name}"


def _get_wallpaper(params: dict) -> str:
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_READ)
    val, _ = winreg.QueryValueEx(key, "WallPaper")
    winreg.CloseKey(key)
    return f"Wallpaper: {val}"


def _dual_screen(params: dict) -> str:
    return _ps("Get-CimInstance Win32_VideoController | Select-Object Name, CurrentHorizontalResolution, CurrentVerticalResolution | Format-Table -AutoSize")


def _extend_screens(params: dict) -> str:
    _ps("Set-DisplayConfiguration -Path '\\.\\DISPLAY2' -Position @{X=1920;Y=0}")
    return "Extended display layout"


def _mirror_screens(params: dict) -> str:
    _ps("Set-DisplayConfiguration -Path '\\.\\DISPLAY2' -Position @{X=0;Y=0}")
    return "Mirrored display layout"


def _set_primary(params: dict) -> str:
    monitor = params.get("monitor", "1")
    _ps(f"Set-DisplayConfiguration -Path '\\.\\DISPLAY{monitor}' -Primary")
    return f"Set monitor {monitor} as primary"
