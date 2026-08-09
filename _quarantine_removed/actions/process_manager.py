"""Process Manager — list, kill, and manage system processes for JARVIS MK-X."""

import os
import heapq
import subprocess
import logging
from typing import Optional

logger = logging.getLogger("jarvis.actions.process_manager")


def process_action(action: str, parameters: dict, **kwargs) -> str:
    """Dispatch process operations."""
    handlers = {
        "list": _list_processes,
        "kill": _kill_process,
        "search": _search_processes,
        "info": _process_info,
        "top": _top_cpu,
        "top_mem": _top_memory,
    }
    handler = handlers.get(action)
    if not handler:
        return f"Unknown process action: {action}"
    try:
        return handler(parameters)
    except Exception as e:
        logger.error("Process action '%s' failed: %s", action, e)
        return f"Process operation failed: {e}"


def _list_processes(params: dict) -> str:
    """List running processes."""
    import psutil
    limit = params.get("limit", 30)
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    top_procs = heapq.nlargest(limit, procs, key=lambda x: x.get("cpu_percent", 0) or 0)
    lines = []
    for p in top_procs:
        cpu = p.get("cpu_percent", 0) or 0
        mem = p.get("memory_percent", 0) or 0
        lines.append(f"  PID {p['pid']:>6}  {p['name'][:30]:<30}  CPU {cpu:5.1f}%  RAM {mem:5.1f}%")

    return f"Top {min(limit, len(procs))} processes by CPU:\n" + "\n".join(lines)


def _kill_process(params: dict) -> str:
    """Kill a process by name or PID."""
    import psutil

    name = params.get("name", "")
    pid = params.get("pid")

    if pid:
        try:
            p = psutil.Process(int(pid))
            p_name = p.name()
            p.terminate()
            try:
                p.wait(timeout=5)
            except psutil.TimeoutExpired:
                p.kill()
            return f"Killed process: {p_name} (PID {pid})"
        except psutil.NoSuchProcess:
            return f"No process with PID {pid}"
        except psutil.AccessDenied:
            return f"Access denied killing PID {pid}"

    if name:
        killed = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if name.lower() in p.info["name"].lower():
                    p.terminate()
                    killed.append(f"{p.info['name']} (PID {p.info['pid']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if killed:
            return f"Killed {len(killed)} processes: {', '.join(killed[:10])}"
        return f"No processes matching '{name}' found"

    return "Provide a process name or PID to kill"


def _search_processes(params: dict) -> str:
    """Search for processes by name."""
    import psutil

    query = params.get("query", "").lower()
    if not query:
        return "Provide a search query"

    matches = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            if query in p.info["name"].lower():
                matches.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if matches:
        lines = [f"  PID {m['pid']:>6}  {m['name']}" for m in matches[:20]]
        return f"Found {len(matches)} matches:\n" + "\n".join(lines)
    return f"No processes matching '{query}'"


def _process_info(params: dict) -> str:
    """Get detailed info about a process."""
    import psutil

    pid = params.get("pid")
    name = params.get("name", "")

    if not pid and name:
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if name.lower() in p.info["name"].lower():
                    pid = p.info["pid"]
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    if not pid:
        return "Process not found"

    try:
        p = psutil.Process(int(pid))
        info = p.as_dict(attrs=["pid", "name", "status", "cpu_percent", "memory_percent",
                                  "create_time", "num_threads", "exe", "cmdline"])
        lines = [
            f"PID: {info['pid']}",
            f"Name: {info['name']}",
            f"Status: {info.get('status', '?')}",
            f"CPU: {info.get('cpu_percent', 0):.1f}%",
            f"RAM: {info.get('memory_percent', 0):.1f}%",
            f"Threads: {info.get('num_threads', '?')}",
            f"EXE: {info.get('exe', '?')}",
        ]
        if info.get("cmdline"):
            lines.append(f"CMD: {' '.join(info['cmdline'][:5])}")
        return "\n".join(lines)
    except psutil.NoSuchProcess:
        return f"No process with PID {pid}"


def _top_cpu(params: dict) -> str:
    """Show top CPU-consuming processes."""
    import psutil
    limit = params.get("limit", 10)
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    top_procs = heapq.nlargest(limit, procs, key=lambda x: x.get("cpu_percent", 0) or 0)
    lines = []
    for p in top_procs:
        cpu = p.get("cpu_percent", 0) or 0
        lines.append(f"  {p['name'][:30]:<30}  {cpu:5.1f}%  (PID {p['pid']})")

    return f"Top {limit} CPU consumers:\n" + "\n".join(lines)


def _top_memory(params: dict) -> str:
    """Show top memory-consuming processes."""
    import psutil
    limit = params.get("limit", 10)
    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_percent", "memory_info"]):
        try:
            info = p.info
            info["rss_mb"] = (info.get("memory_info", None) and info["memory_info"].rss / (1024*1024)) or 0
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    top_procs = heapq.nlargest(limit, procs, key=lambda x: x.get("rss_mb", 0))
    lines = []
    for p in top_procs:
        mem = p.get("memory_percent", 0) or 0
        rss = p.get("rss_mb", 0)
        lines.append(f"  {p['name'][:30]:<30}  {mem:5.1f}%  ({rss:.0f} MB)  (PID {p['pid']})")

    return f"Top {limit} memory consumers:\n" + "\n".join(lines)
