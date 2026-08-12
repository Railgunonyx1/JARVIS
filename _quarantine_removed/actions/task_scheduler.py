"""Task Scheduler — Windows scheduled tasks for JARVIS MK-X."""

import logging
import subprocess

logger = logging.getLogger("jarvis.actions.task_scheduler")


def task_action(action: str, parameters: dict, **kwargs) -> str:
    handlers = {
        "list": _list_tasks,
        "create": _create_task,
        "delete": _delete_task,
        "run": _run_task,
        "status": _task_status,
        "enable": _enable_task,
        "disable": _disable_task,
    }
    handler = handlers.get(action)
    if not handler:
        return f"Unknown task action: {action}"
    try:
        return handler(parameters)
    except Exception as e:
        logger.error("Task action '%s' failed: %s", action, e)
        return f"Task operation failed: {e}"


def _ps(cmd: str) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def _list_tasks(params: dict) -> str:
    limit = params.get("limit", 20)
    out = _ps(f"Get-ScheduledTask | Where-Object {{$_.State -ne 'Disabled'}} | Select-Object -First {limit} TaskName, TaskPath, State | Format-Table -AutoSize")
    return out if out else "No scheduled tasks found"


def _create_task(params: dict) -> str:
    name = params.get("name", "")
    command = params.get("command", "")
    time_str = params.get("time", "12:00")
    if not name or not command:
        return "Provide name and command"
    _ps(f'Schtasks /Create /TN "{name}" /TR "{command}" /ST {time_str} /SC DAILY /F')
    return f"Created scheduled task '{name}' to run daily at {time_str}"


def _delete_task(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a task name"
    _ps(f'Schtasks /Delete /TN "{name}" /F')
    return f"Deleted task '{name}'"


def _run_task(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a task name"
    _ps(f'Schtasks /Run /TN "{name}"')
    return f"Running task '{name}'"


def _task_status(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a task name"
    out = _ps(f'(Get-ScheduledTask -TaskName "{name}").State')
    return f"Task '{name}': {out}"


def _enable_task(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a task name"
    _ps(f'Enable-ScheduledTask -TaskName "{name}"')
    return f"Enabled task '{name}'"


def _disable_task(params: dict) -> str:
    name = params.get("name", "")
    if not name:
        return "Provide a task name"
    _ps(f'Disable-ScheduledTask -TaskName "{name}"')
    return f"Disabled task '{name}'"
