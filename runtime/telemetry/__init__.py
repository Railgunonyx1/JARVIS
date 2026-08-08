"""Telemetry package initialization.
Provides a global Telemetry instance for the runtime.
"""

from .telemetry import Telemetry

# Global telemetry instance – will be started by the kernel.
telemetry = Telemetry()
