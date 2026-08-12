"""Network Connection Reuse — Persistent HTTP/2 connections.

Maintain persistent connections to frequently used services
instead of reconnecting for each request.
"""
import logging
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("os_optimization.network_reuse")


@dataclass
class PooledConnection:
    """A persistent connection to a host."""
    host: str
    port: int = 443
    protocol: str = "https"
    last_used: float = 0.0
    request_count: int = 0
    total_bytes: int = 0
    avg_latency_ms: float = 0.0
    is_alive: bool = True


class NetworkConnectionPool:
    """Maintain persistent connections to frequently used services.

    Tracks connection usage and avoids reconnection overhead.
    """

    def __init__(self, max_idle_seconds: int = 300):
        self._max_idle = max_idle_seconds
        self._connections: dict[str, PooledConnection] = {}
        self._lock = threading.Lock()
        self._total_requests = 0
        self._connection_reuse = 0

    def get_connection(self, host: str, port: int = 443) -> PooledConnection:
        """Get or create a pooled connection."""
        key = f"{host}:{port}"

        with self._lock:
            conn = self._connections.get(key)
            if conn and conn.is_alive:
                age = time.time() - conn.last_used
                if age < self._max_idle:
                    conn.last_used = time.time()
                    conn.request_count += 1
                    self._connection_reuse += 1
                    self._total_requests += 1
                    return conn

            # Create new connection
            conn = PooledConnection(
                host=host, port=port,
                last_used=time.time(),
            )
            self._connections[key] = conn
            self._total_requests += 1
            return conn

    def fetch(self, url: str, timeout: int = 10) -> dict[str, Any]:
        """Fetch a URL using pooled connection."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        conn = self.get_connection(host, port)

        start = time.time()
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "JARVIS/1.0",
                "Connection": "keep-alive",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                latency_ms = (time.time() - start) * 1000

                # Update stats
                conn.total_bytes += len(data)
                n = conn.request_count
                conn.avg_latency_ms = (conn.avg_latency_ms * (n - 1) + latency_ms) / max(n, 1)

                return {
                    "status": resp.status,
                    "data": data,
                    "bytes": len(data),
                    "latency_ms": round(latency_ms, 1),
                    "reused": conn.request_count > 1,
                }
        except Exception as e:
            conn.is_alive = False
            return {"error": str(e), "latency_ms": round((time.time() - start) * 1000, 1)}

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "pooled_connections": len(self._connections),
                "total_requests": self._total_requests,
                "connection_reuse": self._connection_reuse,
                "reuse_rate": round(self._connection_reuse / max(self._total_requests, 1) * 100, 1),
            }


_network_pool_instance: NetworkConnectionPool | None = None


def get_network_pool() -> NetworkConnectionPool:
    global _network_pool_instance
    if _network_pool_instance is None:
        _network_pool_instance = NetworkConnectionPool()
    return _network_pool_instance
