"""Tests for the recycled system.status tool (psutil-backed, read-only)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.system_monitor as sm  # noqa: E402
from tools import build_default_registry  # noqa: E402
from tools.schema import ToolResult  # noqa: E402


def test_system_status_registered():
    registry = build_default_registry()
    tool = registry.get("system.status")
    assert tool is not None
    assert tool.category == "system"
    assert tool.permission == "system.query"
    assert tool.handler is not None
    assert tool.parameters.get("required") == []


def test_system_status_success():
    result = sm.system_status({})
    assert isinstance(result, ToolResult)
    assert result.success is True
    assert "CPU:" in result.output
    assert "RAM:" in result.output
    assert result.metadata["cpu_percent"] is not None
    assert result.metadata["ram_total_gb"] > 0


def test_system_status_cached(monkeypatch):
    monkeypatch.setattr(sm, "_cache", {})
    monkeypatch.setattr(sm, "_cache_time", 0.0)

    import psutil

    calls = {"n": 0}

    def fake_percent(interval=None):
        calls["n"] += 1
        return 50.0

    monkeypatch.setattr(psutil, "cpu_percent", fake_percent)
    sm.system_status({})
    sm.system_status({})
    assert calls["n"] == 1


def test_system_status_handles_missing_optional_fields(monkeypatch):
    monkeypatch.setattr(sm, "_get_cpu_temp", lambda: -1.0)
    monkeypatch.setattr(sm, "_get_gpu", lambda: -1.0)
    result = sm.system_status({})
    assert result.metadata["cpu_temp_c"] is None
    assert result.metadata["gpu_percent"] is None
