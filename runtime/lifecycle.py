"""Service lifecycle base for the JARVIS runtime."""

from __future__ import annotations


class Service:
    """Base class for kernel services with an async start/stop lifecycle."""

    async def start(self) -> None:
        """Start the service."""

    async def stop(self) -> None:
        """Stop the service."""
