"""Shared pooled HTTP client — persistent connections with keep-alive.

Replaces per-call `urllib.request.urlopen` (which opens a fresh TCP/TLS
connection every request) with a single reusable connection pool.

Synchronous (thread-safe) for use from Flask request threads and async
services. Fallback to urllib if httpx is unavailable.
"""

import asyncio
import json
import logging
import random
import threading
import time
from typing import Optional

logger = logging.getLogger("jarvis.core.http_pool")

_lock = threading.Lock()
_client = None
_async_client = None

_RETRY_ATTEMPTS = 2
_RETRY_BACKOFF_BASE = 0.5


def _retryable(exc: Exception) -> bool:
    """True only for transient failures: 429/5xx responses and connect errors."""
    import httpx
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 408 or code == 429 or code >= 500
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return True
    return False


def _build_client():
    import httpx
    return httpx.Client(
        headers={"User-Agent": "JARVIS/1.0"},
        timeout=10.0,
        limits=httpx.Limits(
            max_connections=32,
            max_keepalive_connections=16,
            keepalive_expiry=30.0,
        ),
    )


def get_client():
    """Return the shared thread-safe httpx.Client (lazy init)."""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                try:
                    _client = _build_client()
                except Exception:
                    _client = None
    return _client


def get_async_client():
    """Return the shared httpx.AsyncClient (lazy init).

    Note: an AsyncClient is bound to the event loop that created it. This
    is only safe to reuse from a single running loop (JARVIS's backend loop).
    """
    global _async_client
    if _async_client is None:
        with _lock:
            if _async_client is None:
                try:
                    import httpx
                    _async_client = httpx.AsyncClient(
                        headers={"User-Agent": "JARVIS/1.0"},
                        timeout=10.0,
                        limits=httpx.Limits(
                            max_connections=32,
                            max_keepalive_connections=16,
                            keepalive_expiry=30.0,
                        ),
                    )
                except Exception:
                    _async_client = None
    return _async_client


def fetch(url: str, timeout: Optional[float] = None, as_json: bool = False):
    """GET a URL through the pooled client with bounded retry.

    Retries transient failures (connect errors, 408/429/5xx) with exponential
    backoff + jitter. Returns raw text, parsed JSON (if as_json=True), or None
    on failure.
    """
    timeout = timeout or 10.0
    last_exc: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS + 1):
        try:
            text = _fetch_once(url, timeout)
            return json.loads(text) if as_json else text
        except Exception as e:
            last_exc = e
            if attempt < _RETRY_ATTEMPTS and _retryable(e):
                delay = _RETRY_BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 0.25)  # nosec B311
                time.sleep(delay)
                continue
            break
    logger.debug("HTTP fetch failed for %s: %s", url, last_exc)
    return None


def _fetch_once(url: str, timeout: float) -> str:
    client = get_client()
    if client is not None:
        resp = client.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode()


async def fetch_async(url: str, timeout: Optional[float] = None, as_json: bool = False):
    """Async GET through the pooled async client (same event loop only).

    Retries transient failures (connect errors, 408/429/5xx) with exponential
    backoff + jitter.
    """
    timeout = timeout or 10.0
    last_exc: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS + 1):
        try:
            text = await _fetch_once_async(url, timeout)
            return json.loads(text) if as_json else text
        except Exception as e:
            last_exc = e
            if attempt < _RETRY_ATTEMPTS and _retryable(e):
                delay = _RETRY_BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 0.25)  # nosec B311
                await asyncio.sleep(delay)
                continue
            break
    logger.debug("Async HTTP fetch failed for %s: %s", url, last_exc)
    return None


async def _fetch_once_async(url: str, timeout: float) -> str:
    client = get_async_client()
    if client is not None:
        resp = await client.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    return await _urllib_fallback_async(url, timeout)


async def _urllib_fallback_async(url: str, timeout: Optional[float]):
    import asyncio
    import urllib.request
    def _get():
        req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1.0"})
        with urllib.request.urlopen(req, timeout=timeout or 10.0) as resp:
            return resp.read().decode()
    return await asyncio.to_thread(_get)
