"""TUI data backend — live daemon with mock/offline fallback.

The dashboard is a *client* of the existing daemon (``daemon/client.py``
over the TCP loopback transport). There is deliberately no second transport
here — no IPC module, no named pipes, no second server. When no daemon is
reachable the UI stays usable with local ``psutil`` stats and clearly
marked mock rows, and it reconnects in the background the moment a daemon
appears (e.g. ``jarvis daemon start`` in another terminal).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psutil

from ui.providers import (
    MOCK_MCP,
    MOCK_PLAN,
    MOCK_PROVIDERS,
    MOCK_SKILL_RECORDS,
    MOCK_TASKS,
    provider_rows,
)

__all__ = ["TuiDataSource"]

EventCallback = Callable[[str, dict], None]


class TuiDataSource:
    """Owns the daemon connection, live samples, and mock fallback state."""

    def __init__(self, project_dir: str | None = None,
                 mock: bool = False, url: str | None = None) -> None:
        self.project_dir = str(
            Path(project_dir).resolve() if project_dir else Path.cwd().resolve())
        self._force_mock = mock
        self._url_override = url
        self._auto_start = True
        self._client: Any = None
        self._connected = False
        self._last_error = ""
        self._status: dict = {"mode": "smart"}
        self._models: dict = {}
        self._provider_rows: list[tuple[str, str, str, str, str]] = list(MOCK_PROVIDERS)
        self._mock_providers = True
        self._mock_tasks = True
        self._was_ever_real = False
        self._skills: list[dict] = []
        self._skill_rows: list[tuple[str, str, str]] = self._build_skill_rows([])
        self._mock_skills = True
        self._cpu_history = [0.0] * 60
        self._ram_history = [0.0] * 60
        self._token_history = [5.0] * 48
        psutil.cpu_percent(interval=None)

    # ── connection ──────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Resolve the project daemon entry and authenticate to it."""
        if self._force_mock:
            self._mark_offline("forced mock mode (--mock)")
            return
        from daemon.client import DaemonClient

        if self._url_override:
            client, err = self._client_from_url(self._url_override)
            if err:
                self._mark_offline(err)
                return
        else:
            entry = await asyncio.to_thread(self._resolve_entry)
            if entry is None and self._auto_start:
                entry = await asyncio.to_thread(self._start_entry)
            if entry is None:
                self._mark_offline("no daemon for this project (run `jarvis daemon start`)")
                return
            client = DaemonClient(
                host="127.0.0.1",
                port=int(entry["port"]),
                token=str(entry.get("token", "")),
                project_id=entry.get("project_id", ""),
            )
        try:
            await client.connect()
        except Exception as exc:
            self._mark_offline(str(exc))
            return
        self._client = client
        self._connected = True
        self._last_error = ""
        self._was_ever_real = True
        await self.refresh()

    def _start_entry(self) -> dict | None:
        from daemon.lifecycle import start_daemon

        return start_daemon(self.project_dir)

    @staticmethod
    def _client_from_url(url: str) -> tuple[Any, str]:
        from urllib.parse import parse_qs, urlparse

        from daemon.client import DaemonClient

        parsed = urlparse(url)
        if parsed.scheme not in ("tcp", "http"):
            return None, f"unsupported daemon url scheme: {parsed.scheme!r}"
        qs = parse_qs(parsed.query)
        return DaemonClient(
            host=parsed.hostname or "127.0.0.1",
            port=int(parsed.port or 0),
            token=qs.get("token", [""])[0],
            project_id=qs.get("project_id", [""])[0],
        ), ""

    def _resolve_entry(self) -> dict | None:
        from daemon.lifecycle import find_matching

        return find_matching(self.project_dir)

    def _mark_offline(self, reason: str) -> None:
        self._connected = False
        self._client = None
        self._last_error = reason
        # Preserve mock/real state across transient network blips.
        # Only reset status if we've never had a successful daemon connection.
        if not self._was_ever_real:
            self._status = {}

    async def refresh(self) -> None:
        """Pull status + provider health + skill registry from the daemon.

        Distinguishes actual connection loss from transient data errors:
        - ``ConnectionError`` → go offline (user must reconnect)
        - Any other error → log but stay connected with previous data.
        """
        if not self._connected or self._client is None:
            return
        try:
            self._status = await self._client.status()
            self._models = await self._client.models()
            rows = provider_rows(self._models)
            self._provider_rows = rows if rows else list(MOCK_PROVIDERS)
            self._mock_providers = not bool(rows)
            self._skills = (await self._client.skills()).get("skills", [])
            self._skill_rows = self._build_skill_rows(self._skills)
            self._mock_skills = not bool(self._skills)
        except ConnectionError:
            # Actual network / daemon-down scenario
            self._mark_offline("daemon connection lost")
        except Exception as exc:
            # Transient data error — keep previous state, stay connected
            logger.warning("Refresh data error (staying connected): %s", exc)

    def _build_skill_rows(self, records: list[dict]) -> list[tuple[str, str, str]]:
        """Map registry records to ``(name, version, STATUS)`` rows.

        A skill is READY when the daemon's current mode is among its
        ``supported_modes``; otherwise it is shown LOCKED (dim) so the panel
        surfaces what this mode can actually call. With no registry records
        (offline/mock) the same heuristic runs over :data:`MOCK_SKILL_RECORDS`,
        whose entries carry ``supported_modes`` so mock rows stay mode-aware.
        """
        mode = self._status.get("mode", "")
        rows = []
        for record in sorted(records or MOCK_SKILL_RECORDS,
                             key=lambda r: r.get("name", "").lower()):
            name = record.get("name", "?")
            version = record.get("version", "-")
            modes = record.get("supported_modes") or []
            ready = (not mode) or mode in modes
            rows.append((name, version, "READY" if ready else "LOCKED"))
        return rows

    async def try_reconnect(self) -> None:
        """Best-effort background reconnect when currently offline."""
        if not self._connected:
            await self.connect()

    # ── commands ────────────────────────────────────────────────────────

async def run_goal(self, goal: str,
                   on_event: EventCallback | None = None) -> dict:
        """Submit a goal; stream observer events; return the result dict."""
        if self._client is None:
            return {"success": False,
                    "error": self._last_error or "daemon not initialized"}
        try:
            return await self._client.run(goal, on_event=on_event)
        except Exception as exc:
            # Let daemon.client.run() handle bounded retries (max 3, exponential backoff).
            # Only mark disconnected if the outer caller needs to know.
            return {"success": False, "error": str(exc)}

    async def set_mode(self, mode: str) -> dict:
        """Switch the daemon's permission mode; returns ``{"success": ...}``."""
        if not self._connected or self._client is None:
            return {"success": False,
                    "error": self._last_error or "daemon not connected"}
        try:
            result = await self._client.set_mode(mode)
            self._status["mode"] = result.get("mode", mode)
            self.recompute_skill_rows()
            return {"success": True, "mode": result.get("mode", mode)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def recompute_skill_rows(self) -> None:
        """Rebuild ``skill_rows`` from the cached registry + current mode.

        Called after a mode switch so READY/LOCKED reflects the new mode.
        """
        self._skill_rows = self._build_skill_rows(self._skills)

    async def memory_search(self, query: str) -> list[dict]:
        """Search daemon memory; returns a list of hits (possibly empty)."""
        if not self._connected or self._client is None:
            return []
        try:
            return await self._client.memory_search(query)
        except Exception:
            return []

    async def search_skills(self, query: str) -> dict:
        """Discovery query against the daemon's skill registry.

        Returns the raw response ``{total, catalog, skills, ...}`` or a
        ``{"skills": [...]}`` fallback over :data:`MOCK_SKILL_RECORDS` when the
        daemon is offline, so discovery/detail stays usable without it.
        """
        if not self._connected or self._client is None:
            q = query.strip().lower()
            skills = MOCK_SKILL_RECORDS
            if q:
                skills = [
                    r for r in skills
                    if q in r.get("name", "").lower()
                    or q in r.get("description", "").lower()
                ]
            return {"total": len(skills), "catalog": len(MOCK_SKILL_RECORDS),
                    "query": query, "skills": skills}
        try:
            return await self._client.skills(query=query,
                                              mode=self._status.get("mode", ""))
        except Exception:
            return {"total": 0, "catalog": 0, "query": query, "skills": []}

    async def history(self, limit: int = 10, task_id: str = "") -> dict:
        """Fetch the audit log from the daemon event store.

        With no ``task_id`` returns ``{"traces": [...]}`` (recent sessions,
        newest first); with one returns ``{"events": [...]}`` for that task.
        Falls back to an empty ``{"traces": []}`` when offline.
        """
        if not self._connected or self._client is None:
            return {"traces": []}
        try:
            return await self._client.history(task_id=task_id, limit=limit)
        except Exception:
            return {"traces": []}

    # ── live samples (local psutil, no daemon needed) ───────────────────

    def snapshot(self) -> dict[str, Any]:
        cpu = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        du = psutil.disk_usage(Path(self.project_dir).anchor or "/")
        self._cpu_history = self._cpu_history[1:] + [cpu]
        self._ram_history = self._ram_history[1:] + [vm.percent]
        return {
            "cpu_percent": cpu,
            "ram_percent": vm.percent,
            "ram_used_gb": vm.used / (1024 ** 3),
            "ram_total_gb": vm.total / (1024 ** 3),
            "disk_used_gb": du.used / (1024 ** 3),
            "disk_total_gb": du.total / (1024 ** 3),
            "uptime_s": time.time() - psutil.boot_time(),
            "active_tasks": 1 if self._status.get("busy") else 0,
        }

    def token_history(self) -> list[float]:
        # MOCK — real per-hour token counts would come from perf.db.
        self._token_history = self._token_history[1:] + [
            max(0, self._token_history[-1] + 1.5)
        ]
        return self._token_history

    def token_usage(self) -> tuple[int, int]:
        """Mock ``(current, total)`` token figures for the usage readout."""
        total = 128_000
        current = int(self._token_history[-1] * 1000) if self._token_history else 0
        return min(current, total), total

    # ── state for the UI ────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def status(self) -> dict:
        return self._status

    @property
    def provider_rows(self) -> list[tuple[str, str, str, str, str]]:
        return self._provider_rows

    @property
    def using_mock_providers(self) -> bool:
        return self._mock_providers

    @property
    def task_rows(self) -> list[tuple[str, str, str, int, str]]:
        return list(MOCK_TASKS)  # mock — daemon has no task endpoint yet

    @property
    def using_mock_tasks(self) -> bool:
        return self._mock_tasks

    @property
    def plan_rows(self) -> list[tuple[str, str, str]]:
        return list(MOCK_PLAN)  # mock — daemon has no plan endpoint yet

    @property
    def using_mock_plan(self) -> bool:
        return True

    @property
    def mcp_rows(self) -> list[tuple[str, str, str]]:
        return list(MOCK_MCP)  # mock — daemon has no MCP registry endpoint yet

    @property
    def using_mock_mcp(self) -> bool:
        return True

    @property
    def skill_rows(self) -> list[tuple[str, str, str]]:
        """Registry rows: ``(name, version, STATUS)`` — real when connected."""
        return self._skill_rows

    @property
    def using_mock_skills(self) -> bool:
        return self._mock_skills

    @property
    def skills(self) -> list[dict]:
        return self._skills

    @property
    def cpu_history(self) -> list[float]:
        return self._cpu_history

    @property
    def ram_history(self) -> list[float]:
        return self._ram_history
