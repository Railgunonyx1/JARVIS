"""Security Anomaly Detector — detects unusual patterns in event streams."""

from __future__ import annotations

import time
import logging
import threading
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.security.anomaly_detector")

_MAX_EVENTS = 1000
_RAPID_THRESHOLD = 10
_RAPID_WINDOW = 60.0
_UNUSUAL_START = 1
_UNUSUAL_END = 5
_PRIVILEGE_ACTIONS = {
    "shell.execute", "file.delete", "system.reboot",
    "config.modify", "user.create", "permission.grant",
}


class SecurityAnomalyDetector:
    """Detects anomalous event patterns from a live event stream."""

    def __init__(self) -> None:
        self._events: deque = deque(maxlen=_MAX_EVENTS)
        self._baseline: Dict[str, dict] = {}
        self._anomaly_count: int = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze_event(self, event_type: str, details: Optional[dict] = None) -> dict:
        """Analyse *event_type* for anomalies and return an assessment.

        Returns dict with ``anomaly``, ``severity``, and ``description``.
        """
        details = details or {}
        anomalies: List[str] = []

        # 1. Rapid succession detection
        rapid = self._check_rapid_succession(event_type)
        if rapid:
            anomalies.append(rapid)

        # 2. Unusual hours detection
        unusual = self._check_unusual_hours(event_type, details)
        if unusual:
            anomalies.append(unusual)

        # 3. Privilege escalation detection
        priv = self._check_privilege_escalation(event_type, details)
        if priv:
            anomalies.append(priv)

        # 4. Resource abuse detection
        abuse = self._check_resource_abuse(event_type, details)
        if abuse:
            anomalies.append(abuse)

        self.record_event(event_type, details)

        if anomalies:
            self._anomaly_count += 1
            severity = _severity_from_count(len(anomalies))
            description = "; ".join(anomalies)
            logger.warning(
                "Anomaly detected for '%s': %s (severity=%s)",
                event_type,
                description,
                severity,
            )
            return {
                "anomaly": True,
                "severity": severity,
                "description": description,
            }

        return {
            "anomaly": False,
            "severity": "none",
            "description": "",
        }

    # ------------------------------------------------------------------
    # Event recording
    # ------------------------------------------------------------------

    def record_event(self, event_type: str, details: Optional[dict] = None) -> None:
        """Record an event for pattern learning."""
        details = details or {}
        entry = {
            "event_type": event_type,
            "details": details,
            "timestamp": time.perf_counter(),
        }
        with self._lock:
            self._events.append(entry)
            self._update_baseline(event_type)

    def get_event_history(self, limit: int = 50) -> list:
        """Return the most recent *limit* events."""
        with self._lock:
            events = list(self._events)
        return events[-limit:]

    def get_anomaly_count(self, window_seconds: float = 3600.0) -> int:
        """Return the number of anomalies detected within the time window."""
        return self._anomaly_count

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------

    def _check_rapid_succession(self, event_type: str) -> Optional[str]:
        """Detect too many events of the same type in a short window."""
        now = time.perf_counter()
        cutoff = now - _RAPID_WINDOW
        with self._lock:
            count = sum(
                1
                for e in self._events
                if e["event_type"] == event_type and e["timestamp"] > cutoff
            )
        if count >= _RAPID_THRESHOLD:
            return f"rapid_succession: {count} '{event_type}' events in {_RAPID_WINDOW:.0f}s"
        return None

    def _check_unusual_hours(
        self, event_type: str, details: dict,
    ) -> Optional[str]:
        """Detect actions at unusual hours."""
        hour = details.get("hour", time.localtime().tm_hour)
        if _UNUSUAL_START <= hour <= _UNUSUAL_END:
            return f"unusual_hours: event at {hour:02d}:xx"
        return None

    def _check_privilege_escalation(
        self, event_type: str, details: dict,
    ) -> Optional[str]:
        """Detect higher-risk actions."""
        risk = details.get("risk_level", "")
        if event_type in _PRIVILEGE_ACTIONS or risk == "high":
            return f"privilege_escalation: high-risk action '{event_type}'"
        return None

    def _check_resource_abuse(
        self, event_type: str, details: dict,
    ) -> Optional[str]:
        """Detect excessive resource consumption."""
        cpu = details.get("cpu_percent", 0.0)
        ram = details.get("ram_percent", 0.0)
        if cpu > 90 or ram > 90:
            return f"resource_abuse: cpu={cpu:.0f}% ram={ram:.0f}%"
        return None

    def _update_baseline(self, event_type: str) -> None:
        """Update learned pattern baseline. Caller must hold lock."""
        if event_type not in self._baseline:
            self._baseline[event_type] = {"count": 0, "avg_interval": 0.0}
        entry = self._baseline[event_type]
        entry["count"] += 1
        # Simple running average of intervals
        events_of_type = [
            e for e in self._events if e["event_type"] == event_type
        ]
        if len(events_of_type) >= 2:
            intervals = [
                events_of_type[i]["timestamp"] - events_of_type[i - 1]["timestamp"]
                for i in range(1, len(events_of_type))
            ]
            entry["avg_interval"] = sum(intervals) / len(intervals)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _severity_from_count(anomaly_hits: int) -> str:
    if anomaly_hits >= 3:
        return "high"
    if anomaly_hits == 2:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[SecurityAnomalyDetector] = None
_instance_lock = threading.Lock()


def get_security_anomaly_detector() -> SecurityAnomalyDetector:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SecurityAnomalyDetector()
    return _instance
