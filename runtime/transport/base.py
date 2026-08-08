"""Async transport interface for JARVIS daemon IPC.

The terminal client and the daemon only depend on this interface, so the
transport (TCP loopback today, Win32 named pipes later) can be swapped
without touching the protocol or the kernel.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

__all__ = ["Transport"]


class Transport(ABC):
    """Message-oriented duplex transport. Messages are plain dicts (envelopes).

    ``send`` and ``receive`` are safe to call from a single asyncio task;
    the implementation is responsible for framing and backpressure.
    """

    @abstractmethod
    async def send(self, message: Dict[str, Any]) -> None:
        """Write one envelope-dict to the peer."""

    @abstractmethod
    async def receive(self) -> Optional[Dict[str, Any]]:
        """Read one envelope-dict, or ``None`` when the peer closed the stream."""

    @abstractmethod
    async def close(self) -> None:
        """Flush and close the connection idempotently."""

    @property
    @abstractmethod
    def is_closing(self) -> bool:
        """True once the connection has been closed or is closing."""
