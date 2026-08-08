"""Startup profiler for JARVIS MK-X (re-export shim).

The implementation moved to ``runtime.startup_profile`` so both the CLI and
the persistent daemon can profile their boot without importing the typer CLI.
This module keeps the old import path working:

    from cli.startup_profile import get_profiler
"""

from __future__ import annotations

from runtime.startup_profile import StartupProfiler, get_profiler, startup_report

__all__ = ["StartupProfiler", "get_profiler", "startup_report"]
