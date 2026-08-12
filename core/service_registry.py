"""Service Registry — domain.service pattern for discovery and lifecycle.

Pattern:
  register("voice.tts", tts_instance)
  register("voice.stt", stt_instance)
  resolve("voice.tts") → TTSProvider
  resolve_all("voice") → [TTSProvider, STTProvider]
"""
import logging
import threading
from collections import defaultdict
from typing import Any

logger = logging.getLogger("jarvis.service_registry")


class ServiceRegistry:
    def __init__(self):
        self._services: dict[str, Any] = {}
        self._by_domain: dict[str, set[str]] = defaultdict(set)
        self._lock = threading.Lock()

    def register(self, name: str, instance: Any):
        with self._lock:
            self._services[name] = instance
            domain = name.split(".")[0] if "." in name else name
            self._by_domain[domain].add(name)
            logger.debug("Registered service '%s'", name)

    def unregister(self, name: str):
        with self._lock:
            self._services.pop(name, None)
            domain = name.split(".")[0] if "." in name else name
            self._by_domain.get(domain, set()).discard(name)

    def resolve(self, name: str) -> Any:
        return self._services.get(name)

    def resolve_all(self, domain: str) -> list[Any]:
        with self._lock:
            return [self._services[n] for n in self._by_domain.get(domain, set()) if n in self._services]

    def get_names(self, domain: str | None = None) -> list[str]:
        with self._lock:
            if domain:
                return sorted(self._by_domain.get(domain, set()))
            return sorted(self._services.keys())

    def get_domains(self) -> list[str]:
        with self._lock:
            return sorted(self._by_domain.keys())

    def get_all_health(self) -> dict[str, str]:
        result = {}
        with self._lock:
            for name, svc in self._services.items():
                try:
                    health_fn = getattr(svc, "health", None)
                    if callable(health_fn):
                        result[name] = "ok" if health_fn() else "degraded"
                    else:
                        result[name] = "unknown"
                except Exception:
                    result[name] = "error"
        return result
