"""Custom exception hierarchy for JARVIS MK-X.

Consistent exception types enable targeted error handling and better stack
traces. All JARVIS-specific exceptions inherit from ``JARVISError`` so they
can be caught with a single ``except JARVISError`` if desired.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("jarvis.exceptions")


class JARVISError(Exception):
    """Base exception for all JARVIS-specific errors.

    Attributes:
        component: Name of the component where the error occurred.
        original_error: The original exception that caused this error, if any.
    """

    def __init__(
        self,
        message: str,
        component: str | None = None,
        original_error: Exception | None = None,
    ):
        self.component = component
        self.original_error = original_error
        super().__init__(message)

    def __str__(self) -> str:
        if self.component:
            return f"[{self.component}] {super().__str__()}"
        return super().__str__()


class ConfigurationError(JARVISError):
    """Raised when configuration is invalid or missing."""


class ResourceExhaustedError(JARVISError):
    """Raised when system resources are exhausted (memory, connections, etc.)."""


class ModelSelectionError(JARVISError):
    """Raised when no suitable model can be selected for a task."""


class ProviderError(JARVISError):
    """Raised when an LLM provider fails or is unavailable."""


class RecoveryError(JARVISError):
    """Raised when a recovery strategy fails after all attempts."""


class TimeoutErrorJARVIS(JARVISError):
    """Raised when an operation times out."""

    def __init__(self, message: str, timeout_seconds: float | None = None, **kwargs):
        self.timeout_seconds = timeout_seconds
        super().__init__(message, **kwargs)
