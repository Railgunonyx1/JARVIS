"""Safe execution utilities for consistent error handling across JARVIS MK-X.

Provides :func:`safe_execute` — a reusable wrapper that handles exceptions
with configurable fallback, logging, and optional re-raise. This eliminates
the proliferation of bare ``except Exception`` blocks that mask critical errors.

Also provides :func:`sync_retry` — a simple retry utility for operational
loops (e.g., executor error decision loops).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger("jarvis.async_utils")


def safe_execute(
    fn: Callable[[], Any],
    *,
    fallback: Optional[Any] = None,
    reraise: bool = False,
    log_level: str = "warning",
    reraise_msg: str = "Operation failed",
) -> Any:
    """Safely execute a function with consistent error handling.

    Args:
        fn: Callable with no arguments to execute.
        fallback: Value to return if *fn* raises an exception (``None`` by default).
        reraise: Whether to re-raise the exception after logging.
        log_level: Logging level for the error message (``"warning"``, ``"error"``,
            or ``"critical"``).
        reraise_msg: Message to include when re-raising the exception.

    Returns:
        The return value of *fn*, or *fallback* if an exception occurred and
        ``reraise`` is ``False``.

    Raises:
        RuntimeError: If *reraise* is ``True``, the original exception is
            re-raised wrapped in ``RuntimeError(reraise_msg)`` from the original.
    """
    try:
        return fn()
    except Exception as e:
        log_msg = f"{reraise_msg}: {e}"
        log_fn = getattr(logger, log_level.lower(), logger.warning)
        log_fn(log_msg)
        if reraise:
            raise RuntimeError(f"{reraise_msg}: {e}") from e
        return fallback


def sync_retry(fn, *, max_attempts: int = 3, base_delay: float = 1.0) -> Any:
    """Retry *fn* up to *max_attempts* times with exponential backoff.

    Args:
        fn: Callable with no arguments.
        max_attempts: Number of attempts (including the first).
        base_delay: Initial delay in seconds (doubles each attempt).

    Returns:
        The return value of the first successful call to *fn*.

    Raises:
        The last exception if all attempts fail.
    """
    last_exception: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last_exception = e
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1))
                time.sleep(delay)
    raise last_exception  # type: ignore[return-value]