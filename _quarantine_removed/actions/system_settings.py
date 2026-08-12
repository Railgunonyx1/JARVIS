"""System Settings — brightness, WiFi, power, display, Bluetooth for JARVIS MK-X.

Uses PowerShell and Windows APIs for system control.
"""

import logging
import subprocess

logger = logging.getLogger("jarvis.actions.system_settings")


def settings_action(action: str, parameters: dict, **kwargs) -> str:
    """Dispatch system settings operations."""
    handlers = {
        "brightness": _set_brightness,
        "get_brightness": _get_brightness,
        "wifi_on": _wifi_on,
        "wifi_off": _wifi_off,
        "wifi_status": _wifi_status,
        "bluetooth_on": _bluetooth_on,
        "bluetooth_off": _bluetooth_off,
        "shutdown": _shutdown,
        "restart": _restart,
        "sleep": _sleep,
        "hibernate": _hibernate,
        "lock": _lock_screen,
        "display_off": _display_off,
        "night_mode_on": _night_mode_on,
        "night_mode_off": _night_mode_off,
        "airplane_on": _airplane_on,
        "airplane_off": _airplane_off,
    }
    handler = handlers.get(action)
    if not handler:
        return f"Unknown settings action: {action}"
    try:
        return handler(parameters)
    except Exception as e:
        logger.error("Settings action '%s' failed: %s", action, e)
        return f"Settings operation failed: {e}"


def _run_ps(cmd: str) -> str:
    """Run a PowerShell command and return output."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def _set_brightness(params: dict) -> str:
    level = params.get("level", 50)
    try:
        import screen_brightness_control as sbc
        sbc.set_brightness(int(level))
        return f"Brightness set to {level}%"
    except ImportError:
        _run_ps(f"(Get-WmiObject -Namespace root\\wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})")
        return f"Brightness set to {level}%"


def _get_brightness(params: dict) -> str:
    try:
        import screen_brightness_control as sbc
        current = sbc.get_brightness()
        return f"Brightness: {current}%"
    except Exception:
        return _run_ps("(Get-WmiObject -Namespace root\\wmi -Class WmiMonitorBrightness).CurrentBrightness")


def _wifi_on(params: dict) -> str:
    _run_ps("netsh interface set interface 'Wi-Fi' admin=enable")
    return "WiFi turned on"


def _wifi_off(params: dict) -> str:
    _run_ps("netsh interface set interface 'Wi-Fi' admin=disable")
    return "WiFi turned off"


def _wifi_status(params: dict) -> str:
    profiles = _run_ps("netsh wlan show interfaces")
    if "connected" in profiles.lower():
        ssid = _run_ps("netsh wlan show interfaces | Select-String 'SSID'")
        return f"WiFi connected. {ssid}"
    return "WiFi disconnected"


def _bluetooth_on(params: dict) -> str:
    _run_ps("Start-Process 'ms-settings:bluetooth'")
    return "Opening Bluetooth settings (toggle manually)"


def _bluetooth_off(params: dict) -> str:
    _run_ps("Start-Process 'ms-settings:bluetooth'")
    return "Opening Bluetooth settings (toggle manually)"


def _shutdown(params: dict) -> str:
    delay = params.get("delay", 0)
    _run_ps(f"shutdown /s /t {delay}")
    return f"Shutting down in {delay} seconds"


def _restart(params: dict) -> str:
    delay = params.get("delay", 0)
    _run_ps(f"shutdown /r /t {delay}")
    return f"Restarting in {delay} seconds"


def _sleep(params: dict) -> str:
    _run_ps("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
    return "Going to sleep"


def _hibernate(params: dict) -> str:
    _run_ps("rundll32.exe powrprof.dll,SetSuspendState 1,1,0")
    return "Hibernating"


def _lock_screen(params: dict) -> str:
    _run_ps("rundll32.exe user32.dll,LockWorkStation")
    return "Screen locked"


def _display_off(params: dict) -> str:
    _run_ps("(Get-WmiObject -Namespace root\\wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,0)")
    return "Display turned off"


def _night_mode_on(params: dict) -> str:
    _run_ps("Start-Process 'ms-settings:nightlight'")
    return "Opening night light settings"


def _night_mode_off(params: dict) -> str:
    _run_ps("Start-Process 'ms-settings:nightlight'")
    return "Opening night light settings"


def _airplane_on(params: dict) -> str:
    _run_ps("Start-Process 'ms-settings:network-airplanemode'")
    return "Opening airplane mode settings"


def _airplane_off(params: dict) -> str:
    _run_ps("Start-Process 'ms-settings:network-airplanemode'")
    return "Opening airplane mode settings"
