"""Async log queue for fire-and-forget conversation logging.

Prevents blocking the event loop during streaming while maintaining bounded thread usage.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("jarvis.core.log_queue")


class LogQueue:
    """Async queue for conversation logging with background writer."""
    
    def __init__(self, max_size: int = 1000):
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._worker_task: Optional[asyncio.Task] = None
        self._memory_store = None
    
    async def start(self, memory_store):
        """Start the background writer task."""
        self._memory_store = memory_store
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("Log queue started (max_size=%d)", self._queue.maxsize)
    
    async def _worker(self):
        """Background worker that writes logs to SQLite."""
        while True:
            try:
                session_id, role, content = await self._queue.get()
                try:
                    await asyncio.to_thread(
                        self._memory_store.log_conversation, session_id, role, content
                    )
                except Exception as e:
                    logger.warning("Failed to log conversation: %s", e)
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Log queue worker error: %s", e)
                await asyncio.sleep(0.1)
    
    async def put(self, session_id: str, role: str, content: str):
        """Add a log entry to the queue (non-blocking)."""
        try:
            self._queue.put_nowait((session_id, role, content))
        except asyncio.QueueFull:
            logger.warning("Log queue full, dropping entry")
    
    async def stop(self):
        """Stop the background writer task."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Log queue stopped")


# Global instance
_log_queue: Optional[LogQueue] = None


async def get_log_queue() -> LogQueue:
    """Get or create the global log queue instance."""
    global _log_queue
    if _log_queue is None:
        _log_queue = LogQueue()
    return _log_queue


async def log_conversation_async(session_id: str, role: str, content: str):
    """Fire-and-forget conversation logging."""
    queue = await get_log_queue()
    await queue.put(session_id, role, content)
