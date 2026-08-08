"""Service Manager — Windows services control for JARVIS MK-X."""

import subprocess
import logging
from typing import Optional

logger = logging.getLogger("jarvis.actions.service_manager")


def service_action(action: str, parameters: dict, **kwargs) -> str:
    """Dispatch service operations."""
    handlers = {
        "list": _list_services,
        "start": _start_service,
        "stop": _stop_service,
        "restart": _restart_service,
        "status": _service_status,
        "search": _search_services,
        "disable": _disable_service,
        "enable": _enable_service,
    }
    handler = handlers.get(action)
    if not handler:
        return f"Unknown service action: {action}"
    try:
        return handler(parameters)
    except Exception as e:
        logger.error("Service action '%s' failed: %s", action, e)
        return f"Service operation failed: {e}"


def _ps(cmd: str) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def _list_services(params: dict) -> str:
    status_filter = params.get("status", "running")
    limit = params.get("limit", 30)
    if status_filter == "running":
        out = _ps(f"Get-Service | Where-Object {{$_.Status -eq 'Running'}} | Select-Object -First {limit} Name, DisplayName, Status | Format-Table -AutoSize")
    elif status_filter == "stopped":
        out = _ps(f"Get-Service | Where-Object {{$_.Status -eq 'Stopped'}} | Select-Object -First {limit} Name, DisplayName, Status | Format-Table -AutoSize")
    else:
        out = _ps(f"Get-Service | Select-Object -First {limit} Name, DisplayName, Status | Format-Table -AutoSize")
    return out if out else "No services found"


def _start_service(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a service name"
    out = _ps(f"Start-Service -Name '{name}' -ErrorAction Stop")
    return f"Started service: {name}"


def _stop_service(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a service name"
    _ps(f"Stop-Service -Name '{name}' -Force -ErrorAction Stop")
    return f"Stopped service: {name}"


def _restart_service(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a service name"
    _ps(f"Restart-Service -Name '{name}' -Force -ErrorAction Stop")
    return f"Restarted service: {name}"


def _service_status(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a service name"
    out = _ps(f"(Get-Service -Name '{name}').Status")
    return f"Service '{name}': {out}"


def _search_services(params: dict) -> str:
    query = params.get("query", "")
    if not query:
        return "Provide a search query"
    out = _ps(f"Get-Service | Where-Object {{$_.Name -like '*{query}*' -or $_.DisplayName -like '*{query}*'}} | Select-Object Name, DisplayName, Status | Format-Table -AutoSize")
    return out if out else f"No services matching '{query}'"


def _disable_service(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a service name"
    _ps(f"Set-Service -Name '{name}' -StartupType Disabled")
    return f"Disabled service: {name}"


def _enable_service(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a service name"
    _ps(f"Set-Service -Name '{name}' -StartupType Automatic")
    return f"Enabled service: {name}"
