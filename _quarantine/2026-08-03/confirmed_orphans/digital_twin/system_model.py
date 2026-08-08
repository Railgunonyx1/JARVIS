"""System Model - Digital twin of the host system for JARVIS MK-X.

Captures system state as snapshots, stores them in SQLite with a rolling
window of 1000 entries, and provides prediction, anomaly detection, trend
analysis, and optimization suggestions.
"""

import json
import time
import math
import sqlite3
import logging
import threading
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.digital_twin")

try:
    import psutil
    _psutil_ok = True
except ImportError:
    _psutil_ok = False

_MAX_SNAPSHOTS = 1000


class ComponentType(str, Enum):
    CPU = "cpu"
    GPU = "gpu"
    RAM = "ram"
    DISK = "disk"
    NETWORK = "network"
    PROCESS = "process"
    BATTERY = "battery"
    OTHER = "other"


class ComponentStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class SystemComponent:
    name: str
    component_type: ComponentType = ComponentType.OTHER
    status: ComponentStatus = ComponentStatus.UNKNOWN
    metrics: Dict[str, Any] = field(default_factory=dict)
    last_updated: float = field(default_factory=time.time)


@dataclass
class SystemSnapshot:
    timestamp: float = field(default_factory=time.time)
    components: Dict[str, SystemComponent] = field(default_factory=dict)
    cpu_usage: float = 0.0
    ram_usage: float = 0.0
    ram_total_gb: float = 0.0
    ram_used_gb: float = 0.0
    disk_io_read_bytes: int = 0
    disk_io_write_bytes: int = 0
    net_io_sent_bytes: int = 0
    net_io_recv_bytes: int = 0
    process_count: int = 0
    top_processes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        components = {}
        for k, v in self.components.items():
            components[k] = {
                "name": v.name,
                "type": v.component_type.value,
                "status": v.status.value,
                "metrics": v.metrics,
                "last_updated": v.last_updated,
            }
        return {
            "timestamp": self.timestamp,
            "cpu_usage": self.cpu_usage,
            "ram_usage": self.ram_usage,
            "ram_total_gb": self.ram_total_gb,
            "ram_used_gb": self.ram_used_gb,
            "disk_io_read_bytes": self.disk_io_read_bytes,
            "disk_io_write_bytes": self.disk_io_write_bytes,
            "net_io_sent_bytes": self.net_io_sent_bytes,
            "net_io_recv_bytes": self.net_io_recv_bytes,
            "process_count": self.process_count,
            "top_processes": self.top_processes,
            "components": components,
        }


class SystemModel:
    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or (Path.home() / ".jarvis" / "data" / "digital_twin.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        self._last_snapshot: Optional[SystemSnapshot] = None
        self._collector_thread: Optional[threading.Thread] = None
        self._running = False
        self._collect_interval: float = 10.0
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                conn = sqlite3.connect(
                    str(self._db_path),
                    check_same_thread=False,
                    timeout=10.0,
                )
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.row_factory = sqlite3.Row
                self._conn = conn
            return self._conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                data TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(timestamp);
        """)
        conn.commit()
        self._prune_old()

    def _prune_old(self):
        conn = self._get_conn()
        count = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        if count > _MAX_SNAPSHOTS:
            excess = count - _MAX_SNAPSHOTS
            conn.execute(
                "DELETE FROM snapshots WHERE id IN "
                "(SELECT id FROM snapshots ORDER BY timestamp ASC LIMIT ?)",
                (excess,),
            )
            conn.commit()

    def take_snapshot(self) -> SystemSnapshot:
        now = time.time()
        snap = SystemSnapshot(timestamp=now)

        if not _psutil_ok:
            logger.warning("psutil unavailable — snapshot will be empty")
            self._store_snapshot(snap)
            return snap

        try:
            snap.cpu_usage = psutil.cpu_percent(interval=0.1)
        except Exception:
            snap.cpu_usage = 0.0

        try:
            mem = psutil.virtual_memory()
            snap.ram_usage = mem.percent
            snap.ram_total_gb = round(mem.total / (1024 ** 3), 2)
            snap.ram_used_gb = round(mem.used / (1024 ** 3), 2)
        except Exception:
            pass

        try:
            disk_io = psutil.disk_io_counters()
            if disk_io:
                snap.disk_io_read_bytes = disk_io.read_bytes
                snap.disk_io_write_bytes = disk_io.write_bytes
        except Exception:
            pass

        try:
            net_io = psutil.net_io_counters()
            if net_io:
                snap.net_io_sent_bytes = net_io.bytes_sent
                snap.net_io_recv_bytes = net_io.bytes_recv
        except Exception:
            pass

        try:
            procs = list(psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]))
            snap.process_count = len(procs)
            valid = [
                p for p in procs
                if p.info.get("cpu_percent") is not None
            ]
            valid.sort(key=lambda p: p.info.get("cpu_percent", 0) or 0, reverse=True)
            snap.top_processes = [
                {
                    "pid": p.info["pid"],
                    "name": p.info.get("name", ""),
                    "cpu_percent": round(p.info.get("cpu_percent", 0) or 0, 1),
                    "memory_percent": round(p.info.get("memory_percent", 0) or 0, 1),
                }
                for p in valid[:10]
            ]
        except Exception:
            pass

        self._build_components(snap)
        self._store_snapshot(snap)
        self._last_snapshot = snap
        return snap

    def _build_components(self, snap: SystemSnapshot):
        cpu_health = ComponentStatus.HEALTHY
        if snap.cpu_usage > 90:
            cpu_health = ComponentStatus.CRITICAL
        elif snap.cpu_usage > 70:
            cpu_health = ComponentStatus.DEGRADED

        snap.components["cpu"] = SystemComponent(
            name="CPU",
            component_type=ComponentType.CPU,
            status=cpu_health,
            metrics={"usage_percent": snap.cpu_usage},
        )

        ram_health = ComponentStatus.HEALTHY
        if snap.ram_usage > 90:
            ram_health = ComponentStatus.CRITICAL
        elif snap.ram_usage > 75:
            ram_health = ComponentStatus.DEGRADED

        snap.components["ram"] = SystemComponent(
            name="RAM",
            component_type=ComponentType.RAM,
            status=ram_health,
            metrics={
                "usage_percent": snap.ram_usage,
                "total_gb": snap.ram_total_gb,
                "used_gb": snap.ram_used_gb,
            },
        )

        snap.components["disk_io"] = SystemComponent(
            name="Disk I/O",
            component_type=ComponentType.DISK,
            status=ComponentStatus.HEALTHY,
            metrics={
                "read_bytes": snap.disk_io_read_bytes,
                "write_bytes": snap.disk_io_write_bytes,
            },
        )

        snap.components["network"] = SystemComponent(
            name="Network",
            component_type=ComponentType.NETWORK,
            status=ComponentStatus.HEALTHY,
            metrics={
                "sent_bytes": snap.net_io_sent_bytes,
                "recv_bytes": snap.net_io_recv_bytes,
            },
        )

        if _psutil_ok:
            try:
                battery = psutil.sensors_battery()
                if battery:
                    bat_health = ComponentStatus.HEALTHY
                    if battery.percent < 15 and not battery.power_plugged:
                        bat_health = ComponentStatus.CRITICAL
                    elif battery.percent < 30 and not battery.power_plugged:
                        bat_health = ComponentStatus.DEGRADED
                    snap.components["battery"] = SystemComponent(
                        name="Battery",
                        component_type=ComponentType.BATTERY,
                        status=bat_health,
                        metrics={
                            "percent": battery.percent,
                            "plugged": battery.power_plugged,
                            "secs_left": battery.secsleft if battery.secsleft > 0 else None,
                        },
                    )
            except Exception:
                pass

        snap.components["processes"] = SystemComponent(
            name="Processes",
            component_type=ComponentType.PROCESS,
            status=ComponentStatus.HEALTHY,
            metrics={
                "count": snap.process_count,
                "top_count": len(snap.top_processes),
            },
        )

    def _store_snapshot(self, snap: SystemSnapshot):
        data_json = json.dumps(snap.to_dict())
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO snapshots (timestamp, data) VALUES (?, ?)",
                (snap.timestamp, data_json),
            )
            conn.commit()
        self._prune_old()

    def get_snapshot_history(self, limit: int = 100, hours: Optional[float] = None) -> List[SystemSnapshot]:
        cutoff = time.time() - (hours * 3600) if hours else 0
        with self._lock:
            conn = self._get_conn()
            if cutoff:
                rows = conn.execute(
                    "SELECT data FROM snapshots WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
                    (cutoff, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT data FROM snapshots ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        snapshots = []
        for row in rows:
            snapshots.append(self._row_to_snapshot(row["data"]))
        return snapshots

    def _row_to_snapshot(self, data_json: str) -> SystemSnapshot:
        d = json.loads(data_json)
        components = {}
        for k, v in d.get("components", {}).items():
            components[k] = SystemComponent(
                name=v["name"],
                component_type=ComponentType(v["type"]),
                status=ComponentStatus(v["status"]),
                metrics=v.get("metrics", {}),
                last_updated=v.get("last_updated", 0),
            )
        return SystemSnapshot(
            timestamp=d["timestamp"],
            components=components,
            cpu_usage=d.get("cpu_usage", 0),
            ram_usage=d.get("ram_usage", 0),
            ram_total_gb=d.get("ram_total_gb", 0),
            ram_used_gb=d.get("ram_used_gb", 0),
            disk_io_read_bytes=d.get("disk_io_read_bytes", 0),
            disk_io_write_bytes=d.get("disk_io_write_bytes", 0),
            net_io_sent_bytes=d.get("net_io_sent_bytes", 0),
            net_io_recv_bytes=d.get("net_io_recv_bytes", 0),
            process_count=d.get("process_count", 0),
            top_processes=d.get("top_processes", []),
        )

    def predict_resource_usage(self, minutes_ahead: int = 30) -> Dict[str, Any]:
        history = self.get_snapshot_history(limit=200, hours=6)
        if len(history) < 3:
            return {
                "cpu_usage": self._last_snapshot.cpu_usage if self._last_snapshot else 0,
                "ram_usage": self._last_snapshot.ram_usage if self._last_snapshot else 0,
                "confidence": "low",
                "message": "Insufficient data for prediction",
            }

        timestamps = [s.timestamp for s in history]
        cpu_values = [s.cpu_usage for s in history]
        ram_values = [s.ram_usage for s in history]

        target_time = timestamps[0] + (minutes_ahead * 60)

        cpu_pred = self._linear_extrapolate(timestamps, cpu_values, target_time)
        ram_pred = self._linear_extrapolate(timestamps, ram_values, target_time)

        cpu_pred = max(0.0, min(100.0, cpu_pred))
        ram_pred = max(0.0, min(100.0, ram_pred))

        residuals_cpu = self._compute_residuals(timestamps, cpu_values)
        residuals_ram = self._compute_residuals(timestamps, ram_values)

        confidence = "high"
        if residuals_cpu > 15 or residuals_ram > 15:
            confidence = "low"
        elif residuals_cpu > 8 or residuals_ram > 8:
            confidence = "medium"

        return {
            "cpu_usage": round(cpu_pred, 1),
            "ram_usage": round(ram_pred, 1),
            "confidence": confidence,
            "minutes_ahead": minutes_ahead,
            "data_points": len(history),
        }

    def _linear_extrapolate(
        self, xs: List[float], ys: List[float], target: float
    ) -> float:
        n = len(xs)
        if n < 2:
            return ys[0] if ys else 0.0
        x_mean = sum(xs) / n
        y_mean = sum(ys) / n
        numerator = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
        denominator = sum((xs[i] - x_mean) ** 2 for i in range(n))
        if abs(denominator) < 1e-12:
            return y_mean
        slope = numerator / denominator
        intercept = y_mean - slope * x_mean
        return slope * target + intercept

    def _compute_residuals(self, xs: List[float], ys: List[float]) -> float:
        n = len(xs)
        if n < 2:
            return 0.0
        x_mean = sum(xs) / n
        y_mean = sum(ys) / n
        num = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
        den = sum((xs[i] - x_mean) ** 2 for i in range(n))
        if abs(den) < 1e-12:
            return 0.0
        slope = num / den
        intercept = y_mean - slope * x_mean
        sse = sum((ys[i] - (slope * xs[i] + intercept)) ** 2 for i in range(n))
        return math.sqrt(sse / n)

    def detect_anomalies(self, snapshot: Optional[SystemSnapshot] = None) -> List[str]:
        snap = snapshot or self._last_snapshot
        if not snap:
            return ["No snapshot available"]

        alerts: List[str] = []
        history = self.get_snapshot_history(limit=100, hours=2)
        if len(history) < 5:
            return alerts

        cpu_vals = [s.cpu_usage for s in history]
        ram_vals = [s.ram_usage for s in history]

        cpu_z = self._z_score(snap.cpu_usage, cpu_vals)
        ram_z = self._z_score(snap.ram_usage, ram_vals)

        if abs(cpu_z) > 2.5:
            direction = "spike" if cpu_z > 0 else "drop"
            alerts.append(f"CPU {direction} detected (z={cpu_z:.1f}, current={snap.cpu_usage:.1f}%)")
        if abs(ram_z) > 2.5:
            direction = "spike" if ram_z > 0 else "drop"
            alerts.append(f"RAM {direction} detected (z={ram_z:.1f}, current={snap.ram_usage:.1f}%)")

        if snap.process_count > 500:
            alerts.append(f"High process count: {snap.process_count}")

        if len(history) >= 2:
            prev = history[1]
            if prev.disk_io_read_bytes > 0:
                read_delta = snap.disk_io_read_bytes - prev.disk_io_read_bytes
                prev_read_rate = prev.disk_io_read_bytes / max(prev.timestamp, 1)
                curr_read_rate = read_delta / max(snap.timestamp - prev.timestamp, 1)
                if prev_read_rate > 0 and curr_read_rate > prev_read_rate * 5:
                    alerts.append("Unusual disk I/O spike detected")

            if prev.net_io_recv_bytes > 0:
                recv_delta = snap.net_io_recv_bytes - prev.net_io_recv_bytes
                prev_recv_rate = prev.net_io_recv_bytes / max(prev.timestamp, 1)
                curr_recv_rate = recv_delta / max(snap.timestamp - prev.timestamp, 1)
                if prev_recv_rate > 0 and curr_recv_rate > prev_recv_rate * 10:
                    alerts.append("Unusual network traffic spike detected")

        for name, comp in snap.components.items():
            if comp.status == ComponentStatus.CRITICAL:
                alerts.append(f"{comp.name} is in critical state")

        return alerts

    def _z_score(self, value: float, values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance)
        if std < 1e-12:
            return 0.0
        return (value - mean) / std

    def get_component_health(self, name: str) -> Dict[str, Any]:
        snap = self._last_snapshot
        if not snap:
            snap = self.take_snapshot()

        comp = snap.components.get(name)
        if not comp:
            return {
                "name": name,
                "status": "not_found",
                "message": f"Component '{name}' not found in latest snapshot",
            }

        return {
            "name": comp.name,
            "type": comp.component_type.value,
            "status": comp.status.value,
            "metrics": comp.metrics,
            "last_updated": comp.last_updated,
            "age_seconds": round(time.time() - comp.last_updated, 1),
        }

    def get_trend(self, metric: str, window_hours: float = 1.0) -> Dict[str, Any]:
        history = self.get_snapshot_history(limit=500, hours=window_hours)
        if len(history) < 3:
            return {
                "metric": metric,
                "trend": "insufficient_data",
                "data_points": len(history),
            }

        values = self._extract_metric(history, metric)
        if not values:
            return {
                "metric": metric,
                "trend": "unknown_metric",
                "available": ["cpu_usage", "ram_usage", "process_count",
                              "disk_io_read_bytes", "disk_io_write_bytes",
                              "net_io_sent_bytes", "net_io_recv_bytes"],
            }

        timestamps = [s.timestamp for s in history]
        n = len(values)
        x_mean = sum(timestamps) / n
        y_mean = sum(values) / n
        num = sum((timestamps[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        den = sum((timestamps[i] - x_mean) ** 2 for i in range(n))

        if abs(den) < 1e-12:
            slope = 0.0
        else:
            slope = num / den

        y_range = max(values) - min(values)
        if y_range < 1e-6:
            normalized_slope = 0.0
        else:
            normalized_slope = slope / y_range

        if abs(normalized_slope) < 0.001:
            trend = "stable"
        elif normalized_slope > 0:
            trend = "increasing"
        else:
            trend = "decreasing"

        return {
            "metric": metric,
            "trend": trend,
            "slope": round(slope, 6),
            "current_value": round(values[0], 2),
            "min_value": round(min(values), 2),
            "max_value": round(max(values), 2),
            "mean_value": round(y_mean, 2),
            "data_points": n,
            "window_hours": window_hours,
        }

    def _extract_metric(self, history: List[SystemSnapshot], metric: str) -> List[float]:
        accessors = {
            "cpu_usage": lambda s: s.cpu_usage,
            "ram_usage": lambda s: s.ram_usage,
            "process_count": lambda s: float(s.process_count),
            "disk_io_read_bytes": lambda s: float(s.disk_io_read_bytes),
            "disk_io_write_bytes": lambda s: float(s.disk_io_write_bytes),
            "net_io_sent_bytes": lambda s: float(s.net_io_sent_bytes),
            "net_io_recv_bytes": lambda s: float(s.net_io_recv_bytes),
        }
        accessor = accessors.get(metric)
        if not accessor:
            return []
        return [accessor(s) for s in history]

    def suggest_optimization(self) -> List[str]:
        snap = self._last_snapshot or self.take_snapshot()
        suggestions: List[str] = []

        cpu_trend = self.get_trend("cpu_usage", window_hours=2.0)
        if cpu_trend.get("trend") == "increasing":
            suggestions.append(
                f"CPU usage is trending upward (current={snap.cpu_usage:.1f}%). "
                "Consider closing resource-heavy applications or scheduling intensive tasks during off-hours."
            )
        elif snap.cpu_usage > 85:
            suggestions.append(
                f"CPU usage is critically high ({snap.cpu_usage:.1f}%). "
                "Identify and terminate unnecessary processes."
            )

        ram_trend = self.get_trend("ram_usage", window_hours=2.0)
        if ram_trend.get("trend") == "increasing":
            suggestions.append(
                f"RAM usage is trending upward ({snap.ram_usage:.1f}%). "
                "Check for memory leaks or consider increasing physical memory."
            )
        elif snap.ram_usage > 85:
            suggestions.append(
                f"RAM usage is critically high ({snap.ram_usage:.1f}%). "
                "Close memory-intensive applications or add more RAM."
            )

        if snap.top_processes:
            top_cpu = [p for p in snap.top_processes if p.get("cpu_percent", 0) > 30]
            if top_cpu:
                names = ", ".join(p["name"] for p in top_cpu[:3])
                suggestions.append(
                    f"High CPU processes detected: {names}. "
                    "Review if these processes are necessary."
                )

            top_mem = [p for p in snap.top_processes if p.get("memory_percent", 0) > 10]
            if top_mem:
                names = ", ".join(p["name"] for p in top_mem[:3])
                suggestions.append(
                    f"High memory processes detected: {names}. "
                    "Consider restarting or replacing with lighter alternatives."
                )

        disk_trend = self.get_trend("disk_io_read_bytes", window_hours=1.0)
        if disk_trend.get("trend") == "increasing":
            suggestions.append(
                "Disk I/O is increasing. Check for excessive logging, "
                "large file operations, or runaway processes."
            )

        net_trend = self.get_trend("net_io_recv_bytes", window_hours=1.0)
        if net_trend.get("trend") == "increasing":
            suggestions.append(
                "Network receive traffic is increasing. "
                "Check for background updates or unusual network activity."
            )

        if not suggestions:
            suggestions.append("System is operating within normal parameters. No optimizations needed.")

        return suggestions

    def start_background_collection(self, interval: float = 10.0):
        if self._running:
            return
        self._collect_interval = interval
        self._running = True
        if _psutil_ok:
            psutil.cpu_percent(interval=None)
        self._collector_thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._collector_thread.start()
        logger.info("Background collection started (interval=%.0fs)", interval)

    def stop_background_collection(self):
        self._running = False
        if self._collector_thread and self._collector_thread.is_alive():
            self._collector_thread.join(timeout=5)
        self._collector_thread = None
        logger.info("Background collection stopped")

    def _collect_loop(self):
        while self._running:
            try:
                self.take_snapshot()
            except Exception as exc:
                logger.error("Snapshot collection failed: %s", exc)
            time.sleep(self._collect_interval)

    def get_latest_snapshot(self) -> Optional[SystemSnapshot]:
        if self._last_snapshot:
            return self._last_snapshot
        with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT data FROM snapshots ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        if row:
            return self._row_to_snapshot(row["data"])
        return None

    def get_model_stats(self) -> Dict[str, Any]:
        with self._lock:
            conn = self._get_conn()
            count = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            oldest = conn.execute(
                "SELECT MIN(timestamp) FROM snapshots"
            ).fetchone()[0]
            newest = conn.execute(
                "SELECT MAX(timestamp) FROM snapshots"
            ).fetchone()[0]
        return {
            "snapshot_count": count,
            "max_snapshots": _MAX_SNAPSHOTS,
            "oldest_timestamp": oldest,
            "newest_timestamp": newest,
            "background_collecting": self._running,
            "collect_interval": self._collect_interval,
            "db_path": str(self._db_path),
        }

    def close(self):
        self.stop_background_collection()
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
