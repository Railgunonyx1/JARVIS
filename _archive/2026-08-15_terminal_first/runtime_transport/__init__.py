"""Transport layer for the JARVIS daemon IPC.

The terminal client and the persistent daemon talk over an async
``Transport`` interface. TCP loopback is the first implementation; a Win32
named-pipe transport can be added later behind the same interface without
touching the protocol or the kernel.
"""

from runtime.transport.base import Transport
from runtime.transport.protocol import Envelope, make_envelope
from runtime.transport.tcp import TCPTransport

__all__ = ["Transport", "Envelope", "make_envelope", "TCPTransport"]
