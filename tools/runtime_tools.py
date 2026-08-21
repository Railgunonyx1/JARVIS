"""Runtime diagnostics — self-monitoring tools for JARVIS."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

from tools.schema import ToolResult, tool_result, truncate

logger = logging.getLogger("jarvis.tools.runtime")

_MAX_OUTPUT = 8000


def _ollama_run(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["ollama", *args], capture_output=True, text=True, timeout=5,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode == 0:
            return result.stdout
    except Exception:
        pass
    return None


def _find_agent_loop():
    import gc
    try:
        from core.agent.loop import AgentLoop
    except Exception:
        return None
    for obj in gc.get_objects():
        if isinstance(obj, AgentLoop):
            return obj
    return None


def _fmt_ts(ts: float) -> str:
    try:
        return time.strftime("%H:%M:%S", time.localtime(ts))
    except Exception:
        return "-"


async def runtime_status(params: dict) -> ToolResult:
    """Report JARVIS runtime health: providers, memory, tools, Ollama.

    Returns a structured health report covering all major subsystems.
    """
    sections = []

    # ── Ollama status ───────────────────────────────────────────
    try:
        import subprocess
        import sys
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode == 0:
            models = [line.split()[0] for line in result.stdout.strip().splitlines()[1:] if line.strip()]
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


async def runtime_latency(params: dict) -> ToolResult:
    """Show model/provider latency data from the live agent loop.

    Combines the LatencyAwareRouter (live TTFT tracking) and PerfTracker
    (learned rolling metrics). Returns empty output when no loop is active
    or no calls have been recorded yet.
    """
    try:
        from core.agent.latency_router import LatencyAwareRouter
        from core.agent.perf_tracker import PerfTracker
    except Exception as e:
        return tool_result(False, error=f"latency modules unavailable: {e}")

    loop = _find_agent_loop()
    router = getattr(loop, "_latency_router", None) if loop else None
    tracker = getattr(loop, "_perf_tracker", None) if loop else None
    stats = router.get_stats() if isinstance(router, LatencyAwareRouter) else {}
    metrics = tracker.get_metrics() if isinstance(tracker, PerfTracker) else {}

    if not stats and not metrics:
        return tool_result(True, output="No latency data: agent loop not initialized or no model calls recorded.")

    lines = []
    if stats:
        lines.append("LIVE LATENCY (LatencyAwareRouter):")
        hdr = (f"  {'model':<26} {'calls':>6} {'succ%':>7}"
               f" {'ttft avg':>9} {'ttft min':>9} {'ttft max':>9} {'lat avg':>9}")
        lines.append(hdr)
        for name in sorted(stats):
            s = stats[name]
            lines.append(
                f"  {name:<26} {s.get('calls', 0):>6} {s.get('success_rate', 0.0):>7.3f}"
                f" {s.get('avg_ttft_ms', 0.0):>8.1f}ms {s.get('min_ttft_ms', 0.0):>8.1f}ms"
                f" {s.get('max_ttft_ms', 0.0):>8.1f}ms {s.get('avg_latency_ms', 0.0):>8.1f}ms"
            )
    if metrics:
        lines.append("LEARNED METRICS (PerfTracker):")
        hdr2 = (f"  {'model':<26} {'calls':>6} {'succ%':>7}"
                f" {'tool%':>7} {'p50 ttft':>9} {'p95 ttft':>9} {'lat avg':>9}")
        lines.append(hdr2)
        for name in sorted(metrics):
            m = metrics[name]
            lines.append(
                f"  {name:<26} {m.get('calls', 0):>6} {m.get('success_rate', 0.0):>7.3f}"
                f" {m.get('tool_success_rate', 0.0):>7.3f} {m.get('p50_ttft_ms', 0.0):>8.1f}ms"
                f" {m.get('p95_ttft_ms', 0.0):>8.1f}ms {m.get('avg_latency_ms', 0.0):>8.1f}ms"
            )

    return tool_result(True, output=truncate("\n".join(lines), _MAX_OUTPUT))


async def runtime_errors(params: dict) -> ToolResult:
    """Show recent errors from the decision log and audit trail.

    Parameters
    ----------
    limit : int
        Max errors to show. Default 20.
    """
    limit = max(1, min(int(params.get("limit", 20) or 20), 100))
    entries = []
    try:
        from core.decision_logger import get_decision_logger
        dl = get_decision_logger()
    except Exception as e:
        return tool_result(False, error=f"decision logger unavailable: {e}")

    try:
        for name in ("tool.failed", "task.failed"):
            for ev in dl.events.query(name=name, limit=limit):
                detail = ""
                for key in ("error", "reason", "goal"):
                    if ev.data.get(key):
                        detail = str(ev.data[key])[:120]
                        break
                entries.append((ev.timestamp, name, detail, ev.trace_id))
    except Exception as e:
        logger.debug("event query failed: %s", e)

    try:
        dl.audit.flush()
        for row in dl.audit.query(limit=200):
            failed = not row.get("success", 1)
            denied = not row.get("allowed", 1)
            if failed or denied:
                detail = row.get("error") or ("permission denied" if denied else "")
                entries.append((
                    row.get("timestamp", 0.0),
                    f"audit.{row.get('tool', '')}",
                    str(detail)[:120],
                    row.get("trace_id", ""),
                ))
    except Exception as e:
        logger.debug("audit query failed: %s", e)

    entries.sort(key=lambda x: x[0], reverse=True)
    entries = entries[:limit]

    if not entries:
        return tool_result(True, output="No recent errors recorded.")

    lines = [f"RECENT ERRORS ({len(entries)}):"]
    for ts, source, detail, trace_id in entries:
        tid = f" trace={trace_id}" if trace_id else ""
        lines.append(f"  {_fmt_ts(ts)} {source}: {detail}{tid}")
    return tool_result(True, output=truncate("\n".join(lines), _MAX_OUTPUT))


async def runtime_events(params: dict) -> ToolResult:
    """Show recent BusEvents published on the canonical event bus.

    Parameters
    ----------
    limit : int
        Max events to show. Default 20.
    """
    limit = max(1, min(int(params.get("limit", 20) or 20), 200))
    try:
        from runtime.event_bus import get_event_bus
    except Exception as e:
        return tool_result(False, error=f"event bus unavailable: {e}")

    bus = get_event_bus()
    events = bus.recent(limit)

    if not events:
        return tool_result(
            True,
            output=(
                "Event bus is online but no BusEvents have been recorded yet. "
                "Events appear once subsystems publish through runtime.event_bus."
            ),
        )

    lines = [f"RECENT BUS EVENTS ({len(events)}, newest first):"]
    for ev in reversed(events):
        payload = ", ".join(f"{k}={str(v)[:40]}" for k, v in list(ev.payload.items())[:3])
        suffix = f" {payload}" if payload else ""
        src = ev.source or "-"
        lines.append(f"  {_fmt_ts(ev.timestamp)} {ev.name} src={src}{suffix}")
    return tool_result(True, output=truncate("\n".join(lines), _MAX_OUTPUT))


async def runtime_models(params: dict) -> ToolResult:
    """Show loaded Ollama models and residency tier state."""
    sections = []

    installed = []
    ps_out = _ollama_run(["ps"])
    list_out = _ollama_run(["list"])
    if list_out:
        installed = [line.split()[0] for line in list_out.strip().splitlines()[1:] if line.strip()]
    sections.append(f"OLLAMA: {len(installed)} models installed" if installed else "OLLAMA: OFFLINE or no models")

    loaded_lines = []
    if ps_out:
        for line in ps_out.strip().splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 4:
                until = parts[4] if len(parts) > 4 else "-"
                loaded_lines.append(f"  {parts[0]:<30} {parts[2]:<10} {parts[3]:<14} expires {until}")
    if loaded_lines:
        sections.append("RESIDENT (loaded in memory):")
        sections.extend(loaded_lines)
    else:
        sections.append("RESIDENT: no models currently loaded")

    try:
        from core.agent.model_residency import ModelResidencyScheduler, ResidencyTier
    except Exception as e:
        sections.append(f"RESIDENCY TIERS: unavailable ({str(e)[:60]})")
        return tool_result(True, output="\n".join(sections))

    loop = _find_agent_loop()
    scheduler = getattr(loop, "_residency", None) if loop else None
    live = isinstance(scheduler, ModelResidencyScheduler)
    if scheduler is None:
        scheduler = ModelResidencyScheduler()

    profiles = getattr(scheduler, "_profiles", {})
    by_tier: dict[str, list[str]] = {}
    for model, profile in profiles.items():
        usage = ""
        if profile.total_calls > 0:
            usage = f" (calls={profile.total_calls}, ttft={profile.avg_ttft_ms:.0f}ms, succ={profile.success_rate:.2f})"
        by_tier.setdefault(profile.tier.name, []).append(f"{model}{usage}")

    origin = "live scheduler" if live else "default policy"
    sections.append(f"RESIDENCY TIERS ({origin}):")
    for tier in sorted(ResidencyTier, reverse=True):
        models = by_tier.get(tier.name, [])
        if models:
            sections.append(f"  {tier.name:<10} {', '.join(models)}")

    return tool_result(True, output=truncate("\n".join(sections), _MAX_OUTPUT))
