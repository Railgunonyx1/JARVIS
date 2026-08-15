"""JARVIS persistent daemon.

A long-lived kernel per project (memory + tools + providers resident in RAM),
exposed over an authenticated localhost TCP loopback transport. The terminal
client connects instead of booting Python each time, so a warm daemon makes
the prompt effectively instant.

Re-exports are lazy (PEP 562) so ``import daemon`` stays cheap for the CLI
fast path and ``python -m daemon.server`` doesn't double-import the server.
"""

from __future__ import annotations

__all__ = [
    "DaemonClient",
    "DaemonError",
    "DaemonDisconnected",
    "DaemonServer",
    "find_matching",
    "start_daemon",
    "stop_daemon",
]


def __getattr__(name: str):
    if name in ("DaemonClient", "DaemonError", "DaemonDisconnected"):
        from daemon.client import (
            DaemonClient,
            DaemonDisconnected,
            DaemonError,
        )

        return {
            "DaemonClient": DaemonClient,
            "DaemonError": DaemonError,
            "DaemonDisconnected": DaemonDisconnected,
        }[name]
    if name in ("find_matching", "start_daemon", "stop_daemon"):
        from daemon import lifecycle

        return getattr(lifecycle, name)
    if name == "DaemonServer":
        from daemon.server import DaemonServer

        return DaemonServer
    raise AttributeError(f"module 'daemon' has no attribute {name!r}")
