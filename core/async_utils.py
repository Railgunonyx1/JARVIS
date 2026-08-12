"""Async utilities — non-blocking sleep, retry, backoff."""

import asyncio
import random
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


async def async_sleep(seconds: float) -> None:
    """Non-blocking sleep."""
    await asyncio.sleep(seconds)


async def async_retry(
    func: Callable[..., T],
    *args,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    jitter: bool = True,
    exceptions: tuple = (Exception,),
    **kwargs,
) -> T:
    """Execute async function with exponential backoff retry."""
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            last_error = e
            if attempt == max_attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            if jitter:
                delay *= random.uniform(0.5, 1.5)
            await asyncio.sleep(delay)
    raise last_error


def sync_retry(
    func: Callable[..., T],
    *args,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    jitter: bool = True,
    exceptions: tuple = (Exception,),
    **kwargs,
) -> T:
    """Execute sync function with exponential backoff retry (blocking)."""
    import random
    import time
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            last_error = e
            if attempt == max_attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            if jitter:
                delay *= random.uniform(0.5, 1.5)
            time.sleep(delay)
    raise last_error


async def gather_with_concurrency(
    max_concurrent: int,
    *coros,
) -> list:
    """Run coroutines with limited concurrency."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded(coro):
        async with semaphore:
            return await coro

    return await asyncio.gather(*[bounded(c) for c in coros])


def run_async(coro):
    """Run async coroutine in sync context (creates new event loop if needed)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        return loop.run_until_complete(coro)
