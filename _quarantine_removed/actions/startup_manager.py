"""Startup Manager — manage Windows startup programs for JARVIS MK-X."""

import logging
import subprocess

logger = logging.getLogger("jarvis.actions.startup_manager")


def startup_action(action: str, parameters: dict, **kwargs) -> str:
    handlers = {
        "list": _list_startup,
        "add": _add_startup,
        "remove": _remove_startup,
        "check": _check_startup,
    }
    handler = handlers.get(action)
    if not handler:
        return f"Unknown startup action: {action}"
    try:
        return handler(parameters)
    except Exception as e:
        logger.error("Startup action '%s' failed: %s", action, e)
        return f"Startup operation failed: {e}"


def _ps(cmd: str) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def _list_startup(params: dict) -> str:
    userStartup = _ps("Get-CimInstance Win32_StartupCommand | Select-Object Name, Command, Location | Format-Table -AutoSize")
    regStartup = _ps("Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run' | Select-Object * -ExcludeProperty PS* | Format-List")
    parts = []
    if userStartup:
        parts.append(f"Startup items:\n{userStartup}")
    if regStartup:
        parts.append(f"Registry startup:\n{regStartup}")
    return "\n".join(parts) if parts else "No startup programs found"


def _add_startup(params: dict) -> str:
    name = params.get("name", "")
    command = params.get("command", "")
    if not name or not command:
        return "Provide name and command"
    _ps(f"New-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run' -Name '{name}' -Value '{command}' -PropertyType String -Force")
    return f"Added '{name}' to startup"


def _remove_startup(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a name to remove"
    _ps(f"Remove-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run' -Name '{name}' -ErrorAction Stop")
    return f"Removed '{name}' from startup"


def _check_startup(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a name to check"
    out = _ps(f"Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run' -Name '{name}' -ErrorAction SilentlyContinue")
    if out and name.lower() in out.lower():
        return f"'{name}' is in startup"
    return f"'{name}' is NOT in startup"
