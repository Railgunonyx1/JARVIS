"""Exporters — SQLite persistence + query helpers for performance traces.

The daemon process calls :func:`enable_perf` once at boot. A dedicated writer
thread drains a bounded queue and batches inserts into ``traces``, ``spans``,
and ``counters`` tables, so disk I/O never blocks a request. Reads (from the
``jarvis perf`` CLI in a separate process) open their own connection, which
WAL mode keeps safe against the concurrent writer.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

__all__ = [
    "SqliteExporter",
    "perf_db_path",
    "get_perf_exporter",
    "enable_perf",
    "disable_perf",
    "read_latest",
    "read_slowest",
    "read_summary",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT UNIQUE,
    timestamp REAL,
    command TEXT,
    total_ms REAL,
    meta TEXT
);
CREATE TABLE IF NOT EXISTS spans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT,
    name TEXT,
    duration_ms REAL,
    offset_ms REAL,
    status TEXT,
    parent_id TEXT,
    error TEXT,
    attributes TEXT
);
CREATE TABLE IF NOT EXISTS counters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT,
    name TEXT,
    value REAL,
    timestamp REAL
);
CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_traces_timestamp ON traces(timestamp);
CREATE INDEX IF NOT EXISTS idx_traces_duration ON traces(total_ms);
CREATE INDEX IF NOT EXISTS idx_counters_trace ON counters(trace_id);
"""

_DEFAULT_MAX_QUEUE = 2000


def perf_db_path() -> Path:
    """Path to the performance SQLite database (``JARVIS_OBSERVABILITY_DB`` overrides)."""
    from runtime.observability.config import perf_db_path as _config_db

    return _config_db()


class SqliteExporter:
    """Background-thread writer that persists completed traces."""

    def __init__(self, db_path: Path | None = None, batch_size: int = 50,
                 flush_interval: float = 0.25, max_queue: int = _DEFAULT_MAX_QUEUE) -> None:
        self.db_path = Path(db_path) if db_path else perf_db_path()
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._queue: deque = deque()
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ── lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="jarvis-perf-writer", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _init_schema(self) -> None:
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    # ── sink (tracer callback) ─────────────────────────────────────────────

    def sink(self, trace: dict[str, Any]) -> None:
        """Accept a finished trace; drop silently when the writer isn't running."""
        if self._thread is None:
            return
        with self._cond:
            if len(self._queue) >= _DEFAULT_MAX_QUEUE:
                return
            self._queue.append(trace)
            self._cond.notify()

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._queue and not self._stop.is_set():
                    self._cond.wait(timeout=self.flush_interval)
                batch: list[dict[str, Any]] = []
                while self._queue and len(batch) < self.batch_size:
                    batch.append(self._queue.popleft())
            if not batch:
                if self._stop.is_set():
                    break
                continue
            self._write_batch(batch)
            if self._stop.is_set() and not self._queue:
                break

    def _write_batch(self, batch: list[dict[str, Any]]) -> None:
        conn = sqlite3.connect(self.db_path, timeout=10)
        try:
            now = time.time()
            for trace in batch:
                conn.execute(
                    "INSERT INTO traces (trace_id, timestamp, command, total_ms, meta)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (
                        trace.get("trace_id"),
                        trace.get("timestamp", now),
                        str(trace.get("command", ""))[:200],
                        float(trace.get("total_ms", 0.0)),
                        json.dumps({"status": trace.get("status", "OK")}, default=str),
                    ),
                )
                for span in trace.get("spans", []):
                    conn.execute(
                        "INSERT INTO spans (trace_id, name, duration_ms, offset_ms,"
                        " status, parent_id, error, attributes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            trace.get("trace_id"),
                            str(span.get("name", ""))[:100],
                            float(span.get("duration_ms", 0.0)),
                            float(span.get("offset_ms", 0.0)),
                            str(span.get("status", "OK")),
                            span.get("parent_id"),
                            span.get("error"),
                            json.dumps(span.get("attributes", {}), default=str),
                        ),
                    )
                for name, value in (trace.get("metrics") or {}).items():
                    conn.execute(
                        "INSERT INTO counters (trace_id, name, value, timestamp)"
                        " VALUES (?, ?, ?, ?)",
                        (trace.get("trace_id"), str(name)[:100], float(value), now),
                    )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()


# ── module-level singleton ────────────────────────────────────────────────

_exporter: SqliteExporter | None = None
_exporter_lock = threading.Lock()


def get_perf_exporter(db_path: Path | None = None) -> SqliteExporter:
    """Process-wide SQLite exporter (lazy; not started until :func:`enable_perf`)."""
    global _exporter
    if _exporter is None:
        with _exporter_lock:
            if _exporter is None:
                _exporter = SqliteExporter(db_path)
    return _exporter


def enable_perf(db_path: Path | None = None) -> None:
    """Start the writer and route finished traces to it (daemon boot hook)."""
    exporter = get_perf_exporter(db_path)
    exporter.start()
    from runtime.observability.tracer import get_tracer

    get_tracer().set_sink(exporter.sink)


def disable_perf() -> None:
    """Stop the writer and detach the sink (daemon shutdown hook)."""
    global _exporter
    exporter = _exporter
    _exporter = None
    if exporter is not None:
        exporter.stop()


# ── read helpers (separate process: `jarvis perf`) ───────────────────────

def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _load_trace(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    spans = conn.execute(
        "SELECT name, duration_ms, offset_ms, status, parent_id, error, attributes"
        " FROM spans WHERE trace_id=? ORDER BY offset_ms",
        (row["trace_id"],),
    ).fetchall()
    counters = conn.execute(
        "SELECT name, value FROM counters WHERE trace_id=?",
        (row["trace_id"],),
    ).fetchall()
    meta = json.loads(row["meta"]) if row["meta"] else {}
    return {
        "trace_id": row["trace_id"],
        "timestamp": row["timestamp"],
        "command": row["command"],
        "total_ms": row["total_ms"],
        "status": meta.get("status", "OK"),
        "spans": [
            {
                "name": s["name"],
                "duration_ms": s["duration_ms"],
                "offset_ms": s["offset_ms"],
                "status": s["status"],
                "parent_id": s["parent_id"],
                "error": s["error"],
                "attributes": json.loads(s["attributes"]) if s["attributes"] else {},
            }
            for s in spans
        ],
        "metrics": {c["name"]: c["value"] for c in counters},
    }


def _query_traces(db_path: Path, order: str, limit: int) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT trace_id, timestamp, command, total_ms, meta FROM traces"
            f" ORDER BY {order} LIMIT ?",
            (limit,),
        ).fetchall()
        return [_load_trace(conn, row) for row in rows]
    finally:
        conn.close()


def read_latest(db_path: Path | None = None, limit: int = 10) -> list[dict[str, Any]]:
    return _query_traces(db_path or perf_db_path(), "id DESC", limit)


def read_slowest(db_path: Path | None = None, limit: int = 10) -> list[dict[str, Any]]:
    return _query_traces(db_path or perf_db_path(), "total_ms DESC", limit)


def read_summary(db_path: Path | None = None) -> dict[str, Any]:
    conn = _connect(db_path or perf_db_path())
    try:
        traces = conn.execute(
            "SELECT COUNT(*) AS count, COALESCE(AVG(total_ms), 0) AS avg_ms,"
            " COALESCE(MAX(total_ms), 0) AS max_ms FROM traces"
        ).fetchone()
        phases = conn.execute(
            "SELECT name, COUNT(*) AS count, COALESCE(AVG(duration_ms), 0) AS avg_ms,"
            " COALESCE(MIN(duration_ms), 0) AS min_ms, COALESCE(MAX(duration_ms), 0) AS max_ms"
            " FROM spans GROUP BY name ORDER BY avg_ms DESC"
        ).fetchall()
        counters = conn.execute(
            "SELECT name, COALESCE(SUM(value), 0) AS total FROM counters"
            " GROUP BY name ORDER BY total DESC"
        ).fetchall()
        return {
            "traces": {
                "count": traces["count"],
                "avg_ms": round(traces["avg_ms"], 2),
                "max_ms": round(traces["max_ms"], 2),
            },
            "phases": [
                {
                    "name": p["name"],
                    "count": p["count"],
                    "avg_ms": round(p["avg_ms"], 2),
                    "min_ms": round(p["min_ms"], 2),
                    "max_ms": round(p["max_ms"], 2),
                }
                for p in phases
            ],
            "counters": {c["name"]: c["total"] for c in counters},
        }
    finally:
        conn.close()
