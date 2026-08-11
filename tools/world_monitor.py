"""World Monitor tools — thin situational-awareness adapter.

Backs the curated ``world_monitor.*`` capabilities against a running World
Monitor instance (github.com/koala73/worldmonitor) over its REST API. Defaults
to the self-hosted Docker stack on ``127.0.0.1:3000`` (nginx proxies ``/api/*``
to the Node API). This is a *thin* adapter: no aggregation, scoring, or memory
here — the agent decides when a call is relevant and what to keep.

Degradation model (never a hard crash):
  * instance unreachable  -> ToolResult(success=False) with a clear
    "is it running / configured?" message
  * no API key configured -> public endpoints (get_sources) still work;
    live-data calls are attempted and only surface the key hint when the
    instance rejects them

Config (config/worldmonitor.toml):
  base_url  self-hosted origin, default http://127.0.0.1:3000
  variant   site variant, default "full"  (full | tech | finance)
  timeout   HTTP timeout seconds, default 10.0
  cache_ttl result TTL seconds, default 300
  api_key   inline fallback key (normally WORLDMONITOR_API_KEY from .env)
  endpoints per-tool RPC route overrides, e.g.
              [worldmonitor.endpoints]
              world_monitor.search = "getNewsIntelligence"
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from core.api_keys import get_api_key
from core.config import Config
from tools.schema import ToolResult, truncate

logger = logging.getLogger("jarvis.tools.world_monitor")

MAX_OUTPUT = 12000
MAX_ITEMS = 25

_LIST_KEYS = ("items", "results", "events", "alerts", "sources", "articles", "news", "disasters", "conflicts")

# Default RPC route per curated tool. All are overridable in config so the
# adapter keeps working if a particular instance names its routes differently.
_RPCS: dict[str, str] = {
    "world_monitor.search": "getNewsIntelligence",
    "world_monitor.get_alerts": "getAlerts",
    "world_monitor.get_region": "getCountryBrief",
    "world_monitor.get_event": "getEventDetail",
    "world_monitor.get_sources": "getSources",
    "world_monitor.world_brief": "getWorldBrief",
}

_CACHE: dict[tuple[Any, ...], tuple[float, ToolResult]] = {}
_CACHE_LOCK = threading.Lock()


# ── settings ────────────────────────────────────────────────────────────────


def _settings() -> dict[str, Any]:
    return Config.instance().get_section("worldmonitor") or {}


def _base_url() -> str:
    return str(_settings().get("base_url", "http://127.0.0.1:3000")).rstrip("/")


def _variant() -> str:
    return str(_settings().get("variant", "full"))


def _timeout() -> float:
    try:
        return float(_settings().get("timeout", 10.0))
    except (TypeError, ValueError):
        return 10.0


def _cache_ttl() -> float:
    try:
        return float(_settings().get("cache_ttl", 300.0))
    except (TypeError, ValueError):
        return 300.0


def _api_key() -> str | None:
    key = get_api_key("worldmonitor_api_key") or str(_settings().get("api_key", "") or "")
    return key.strip() or None


# ── transport (seam for tests) ──────────────────────────────────────────────


def _http_get(url: str, timeout: float, api_key: str | None) -> dict | None:
    """GET a JSON payload. Returns None on any failure (never raises)."""
    headers = {"User-Agent": "JARVIS/1.0", "Accept": "application/json"}
    if api_key:
        headers["X-WorldMonitor-Key"] = api_key
    try:
        import httpx

        resp = httpx.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # noqa: BLE001 - adapter must degrade, not crash
        logger.warning("world_monitor request failed for %s: %s", url, e)
        return None
    if not isinstance(data, dict):
        return {"data": data}
    return data


# ── endpoint resolution / cache ─────────────────────────────────────────────


def _endpoint_for(tool: str) -> str:
    rpc = _RPCS.get(tool, "")
    override = _settings().get("endpoints", {}).get(tool)
    if override:
        rpc = str(override)
    return rpc


def _call(tool: str, params: dict[str, Any]) -> ToolResult:
    rpc = _endpoint_for(tool)
    url = f"{_base_url()}/api/{_variant()}/v1/{rpc}"
    cache_key = (
        tool,
        _base_url(),
        _variant(),
        tuple(sorted((k, str(v)) for k, v in params.items())),
    )

    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(cache_key)
        if hit and now - hit[0] < _cache_ttl():
            return hit[1]

    data = _http_get(url, _timeout(), _api_key())
    if data is None:
        return _unreachable(tool, rpc, url)

    payload = data.get("data", data) if isinstance(data, dict) else data
    text, meta = _render(payload)
    result = ToolResult(
        success=True,
        output=text,
        metadata={"tool": tool, "endpoint": rpc, "url": url, **meta},
    )
    with _CACHE_LOCK:
        _CACHE[cache_key] = (now, result)
    return result


def _unreachable(tool: str, rpc: str, url: str) -> ToolResult:
    hint = "Add an API key via WORLDMONITOR_API_KEY in config/.env if the instance requires one."
    return ToolResult(
        success=False,
        error=(
            f"World Monitor unreachable for {tool} (GET {url}). "
            f"Is the self-hosted stack running on {_base_url()}? "
            "See config/worldmonitor.toml and the project SELF_HOSTING.md. " + hint
        ),
        metadata={"tool": tool, "endpoint": rpc, "url": url},
    )


# ── rendering ───────────────────────────────────────────────────────────────


def _items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in _LIST_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return [payload]


def _render(payload: Any) -> tuple[str, dict[str, Any]]:
    items = _items(payload)
    shown = items[:MAX_ITEMS]
    lines = [json.dumps(item, default=str, ensure_ascii=False) for item in shown]
    text = truncate("\n".join(lines) or "(empty)", MAX_OUTPUT)
    meta = {
        "count": len(items),
        "shown": len(shown),
        "truncated": len(items) > len(shown),
    }
    return text, meta


# ── arg helpers ─────────────────────────────────────────────────────────────


def _text(args: dict[str, Any], key: str, default: str = "") -> str:
    value = args.get(key)
    return default if value is None else str(value)


def _int(args: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(args.get(key, default) or default)
    except (TypeError, ValueError):
        return default


# ── curated tool handlers ───────────────────────────────────────────────────


def world_monitor_search(args: dict[str, Any]) -> ToolResult:
    """Cross-source news/event intelligence search."""
    return _call("world_monitor.search", {
        "q": _text(args, "query"),
        "category": _text(args, "category"),
        "limit": _int(args, "limit", 10),
    })


def world_monitor_get_alerts(args: dict[str, Any]) -> ToolResult:
    """Live situational alerts (conflicts, disasters)."""
    return _call("world_monitor.get_alerts", {
        "region": _text(args, "region"),
        "severity": _text(args, "severity"),
        "limit": _int(args, "limit", 10),
    })


def world_monitor_get_region(args: dict[str, Any]) -> ToolResult:
    """Regional/country situational brief and risk snapshot."""
    country = _text(args, "country", _text(args, "region"))
    return _call("world_monitor.get_region", {
        "country": country,
        "limit": _int(args, "limit", 10),
    })


def world_monitor_get_event(args: dict[str, Any]) -> ToolResult:
    """Detail for one specific event."""
    event_id = _text(args, "event_id")
    if not event_id:
        return ToolResult(
            success=False,
            error="world_monitor.get_event requires 'event_id' (an event id returned by search/get_alerts).",
            metadata={"tool": "world_monitor.get_event"},
        )
    return _call("world_monitor.get_event", {
        "event_id": event_id,
        "event_type": _text(args, "event_type"),
    })


def world_monitor_get_sources(args: dict[str, Any]) -> ToolResult:
    """List the data sources and coverage World Monitor exposes (public)."""
    return _call("world_monitor.get_sources", {
        "category": _text(args, "category"),
        "limit": _int(args, "limit", 20),
    })


def world_monitor_world_brief(args: dict[str, Any]) -> ToolResult:
    """Global snapshot of what is happening right now."""
    return _call("world_monitor.world_brief", {
        "region": _text(args, "region"),
        "limit": _int(args, "limit", 15),
    })
