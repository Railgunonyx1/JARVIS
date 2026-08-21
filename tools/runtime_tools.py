"""Runtime diagnostics — self-monitoring tools for JARVIS."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from tools.schema import ToolResult, tool_result

logger = logging.getLogger("jarvis.tools.runtime")


async def runtime_status(params: dict) -> ToolResult:
    """Report JARVIS runtime health: providers, memory, tools, Ollama.

    Returns a structured health report covering all major subsystems.
    """
    sections = []

    # ── Ollama status ───────────────────────────────────────────
    try:
        import subprocess, sys
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode == 0:
            models = [l.split()[0] for l in result.stdout.strip().splitlines()[1:] if l.strip()]
            sections.append(f"OLLAMA: ONLINE ({len(models)} models: {', '.join(models[:5])})")
        else:
            sections.append("OLLAMA: OFFLINE")
    except Exception:
        sections.append("OLLAMA: UNREACHABLE")

    # ── Memory status ───────────────────────────────────────────
    try:
        from memory.mem import get_mem
        mem = get_mem()
        if mem is not None:
            stats = mem.stats() if hasattr(mem, "stats") else {}
            count = stats.get("total_memories", "unknown")
            sections.append(f"MEMORY: OK ({count} memories)")
        else:
            sections.append("MEMORY: NOT INITIALIZED")
    except Exception as e:
        sections.append(f"MEMORY: ERROR ({str(e)[:60]})")

    # ── Tool registry ───────────────────────────────────────────
    try:
        from tools import build_default_registry
        registry = build_default_registry()
        tools = registry.list()
        categories = {}
        for t in tools:
            cat = getattr(t, "category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
        cat_str = ", ".join(f"{k}={v}" for k, v in sorted(categories.items()))
        sections.append(f"TOOLS: {len(tools)} registered ({cat_str})")
    except Exception as e:
        sections.append(f"TOOLS: ERROR ({str(e)[:60]})")

    # ── Provider status ─────────────────────────────────────────
    try:
        from core.config import Config
        from providers.router import ProviderRouter
        config = Config.instance()
        router = ProviderRouter(config.get_section("models"), config.api_keys)
        providers = list(router._providers.keys())
        sections.append(f"PROVIDERS: {', '.join(providers)}")
    except Exception as e:
        sections.append(f"PROVIDERS: ERROR ({str(e)[:60]})")

    # ── Disk/workspace ──────────────────────────────────────────
    try:
        import os
        cwd = Path.cwd()
        disk = os.statvfs(str(cwd)) if hasattr(os, "statvfs") else None
        if disk:
            free_gb = (disk.f_bavail * disk.f_frsize) / (1024**3)
            sections.append(f"DISK: {free_gb:.1f}GB free")
        else:
            sections.append(f"WORKSPACE: {cwd}")
    except Exception:
        sections.append("DISK: unknown")

    # ── Uptime ──────────────────────────────────────────────────
    try:
        import psutil
        boot = psutil.boot_time()
        uptime_s = time.time() - boot
        hours = int(uptime_s // 3600)
        mins = int((uptime_s % 3600) // 60)
        sections.append(f"UPTIME: {hours}h {mins}m")
    except Exception:
        pass

    output = "\n".join(sections)
    return tool_result(True, output=output)
