"""Metrics Collector — ring buffer → async SQLite flush → WebSocket later.

Records metrics with trace_id, service, duration, memory, cpu, provider, cache_status.
Never blocks the hot path: appends to ring buffer, flushes in background.
"""
import asyncio
import json
import logging
import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.metrics")

_RING_BUFFER_MAX = 10000
_FLUSH_INTERVAL_S = 5.0


@dataclass
class MetricPoint:
    name: str
    value: float
    tags: dict[str, str] = field(default_factory=dict)
    trace_id: str = ""
    service: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class MetricsCollector:
    """Thread-safe metrics collector with ring buffer and periodic SQLite flush."""

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            data_dir = Path.home() / ".jarvis" / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "metrics.db")
        self._db_path = db_path
        self._buffer: deque = deque(maxlen=_RING_BUFFER_MAX)
        self._lock = threading.Lock()
        self._flush_task: asyncio.Task | None = None
        self._running = False
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self._db_path, timeout=2.0)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    value REAL NOT NULL,
                    tags TEXT DEFAULT '{}',
                    trace_id TEXT DEFAULT '',
                    service TEXT DEFAULT '',
                    timestamp REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_name_ts
                ON metrics(name, timestamp)
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Metrics DB init failed: %s", e)

    def record(self, name: str, value: float,
               tags: dict[str, str] | None = None,
               trace_id: str = "", service: str = ""):
        point = MetricPoint(
            name=name,
            value=value,
            tags=tags or {},
            trace_id=trace_id,
            service=service,
        )
        with self._lock:
            self._buffer.append(point)

    def start_background_flush(self, loop: asyncio.AbstractEventLoop | None = None):
        if self._running:
            return
        self._running = True
        loop = loop or asyncio.get_event_loop()
        self._flush_task = loop.create_task(self._flush_loop())

    async def _flush_loop(self):
        while self._running:
            await asyncio.sleep(_FLUSH_INTERVAL_S)
            try:
                await asyncio.to_thread(self._flush)
            except Exception as e:
                logger.debug("Metrics flush error: %s", e)

    def _flush(self):
        with self._lock:
            if not self._buffer:
                return
            batch = list(self._buffer)
            self._buffer.clear()
        try:
            conn = sqlite3.connect(self._db_path, timeout=2.0)
            conn.executemany(
                "INSERT INTO metrics(name, value, tags, trace_id, service, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(p.name, p.value, json.dumps(p.tags), p.trace_id, p.service, p.timestamp)
                 for p in batch]
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug("Metrics SQLite flush failed: %s", e)

    def query(self, name: str, limit: int = 100) -> list[MetricPoint]:
        try:
            conn = sqlite3.connect(self._db_path, timeout=2.0)
            rows = conn.execute(
                "SELECT name, value, tags, trace_id, service, timestamp "
                "FROM metrics WHERE name = ? ORDER BY timestamp DESC LIMIT ?",
                (name, limit)
            ).fetchall()
            conn.close()
            return [
                MetricPoint(
                    name=r[0], value=r[1],
                    tags=json.loads(r[2]) if r[2] else {},
                    trace_id=r[3] or "", service=r[4] or "",
                    timestamp=r[5],
                )
                for r in rows
            ]
        except Exception:
            return []

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            buffer_size = len(self._buffer)
        try:
            conn = sqlite3.connect(self._db_path, timeout=2.0)
            total = conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
            conn.close()
        except Exception:
            total = 0
        return {
            "buffer_size": buffer_size,
            "total_stored": total,
            "running": self._running,
        }

    def stop(self):
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None
        try:
            self._flush()
        except Exception:
            pass


# Global singleton accessor (temporary during migration)
_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector
