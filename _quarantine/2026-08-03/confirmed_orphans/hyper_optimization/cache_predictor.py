"""Cache Predictor: Intelligent cache with adaptive eviction and access prediction."""

import fnmatch
import logging
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.hyper_opt.cache_predictor")


class CachePredictor:
    """Intelligent cache with adaptive eviction and access prediction."""

    def __init__(self, max_size: int = 2000):
        self._max_size = max_size
        self._cache: Dict[str, Dict] = {}
        self._access_history: deque = deque(maxlen=10000)
        self._prediction_model: Dict[str, Dict] = {}
        self._lock = threading.RLock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "predictions_correct": 0,
            "predictions_total": 0,
        }

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats["misses"] += 1
                return None
            if time.time() > entry["ttl"]:
                del self._cache[key]
                self._stats["misses"] += 1
                return None
            entry["access_count"] += 1
            entry["last_access"] = time.perf_counter()
            self._stats["hits"] += 1
            self._record_access(key)
            return entry["value"]

    def put(self, key: str, value: Any, ttl_seconds: float = 300, priority: int = 5):
        with self._lock:
            now = time.perf_counter()
            self._cache[key] = {
                "value": value,
                "created_at": now,
                "access_count": 1,
                "last_access": now,
                "ttl": time.time() + ttl_seconds,
                "priority": priority,
            }
            self._record_access(key)
            if len(self._cache) > self._max_size:
                self.adaptive_evict()

    def _record_access(self, key: str):
        now = time.time()
        self._access_history.append((key, now))
        if len(self._access_history) >= 2:
            prev_key = self._access_history[-2][0]
            if prev_key not in self._prediction_model:
                self._prediction_model[prev_key] = {"next_keys": {}, "total": 0}
            model = self._prediction_model[prev_key]
            model["next_keys"][key] = model["next_keys"].get(key, 0) + 1
            model["total"] += 1

    def predict_next(self, current_key: str, top_n: int = 3) -> List[str]:
        with self._lock:
            model = self._prediction_model.get(current_key)
            if model is None or model["total"] == 0:
                return []
            scored = []
            total = model["total"]
            for next_key, count in model["next_keys"].items():
                confidence = count / total
                scored.append((next_key, confidence))
            scored.sort(key=lambda x: x[1], reverse=True)
            return [k for k, _ in scored[:top_n]]

    def validate_prediction(self, predicted_keys: List[str], actual_key: str):
        with self._lock:
            self._stats["predictions_total"] += len(predicted_keys)
            if actual_key in predicted_keys:
                self._stats["predictions_correct"] += 1

    def _compute_score(self, entry: Dict, now: float) -> float:
        age = now - entry["created_at"]
        recency = now - entry["last_access"]
        access_score = entry["access_count"] / (1.0 + age)
        recency_score = 1.0 / (1.0 + recency)
        priority_score = entry["priority"] / 10.0
        return access_score * 0.4 + recency_score * 0.4 + priority_score * 0.2

    def adaptive_evict(self):
        with self._lock:
            now_perf = time.perf_counter()
            now_time = time.time()
            expired = [k for k, e in self._cache.items() if now_time > e["ttl"]]
            for k in expired:
                del self._cache[k]
                self._stats["evictions"] += 1

            if len(self._cache) <= self._max_size:
                return

            scored = []
            for k, e in self._cache.items():
                score = self._compute_score(e, now_perf)
                scored.append((k, score))
            scored.sort(key=lambda x: x[1])

            while len(self._cache) > self._max_size and scored:
                weakest_key, _ = scored.pop(0)
                if weakest_key in self._cache:
                    del self._cache[weakest_key]
                    self._stats["evictions"] += 1

    def get_stats(self) -> dict:
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total if total > 0 else 0.0
            pred_total = self._stats["predictions_total"]
            pred_accuracy = (
                self._stats["predictions_correct"] / pred_total if pred_total > 0 else 0.0
            )
            return {
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": round(hit_rate, 4),
                "evictions": self._stats["evictions"],
                "size": len(self._cache),
                "max_size": self._max_size,
                "prediction_accuracy": round(pred_accuracy, 4),
                "predictions_total": pred_total,
            }

    def invalidate_pattern(self, pattern: str):
        with self._lock:
            keys_to_remove = [k for k in self._cache if fnmatch.fnmatch(k, pattern)]
            for k in keys_to_remove:
                del self._cache[k]
            logger.info("Invalidated %d keys matching pattern '%s'", len(keys_to_remove), pattern)

    def get_hot_keys(self, top_n: int = 10) -> List[str]:
        with self._lock:
            scored = []
            for key, entry in self._cache.items():
                scored.append((key, entry["access_count"]))
            scored.sort(key=lambda x: x[1], reverse=True)
            return [k for k, _ in scored[:top_n]]

    def clear(self):
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._access_history.clear()
            self._prediction_model.clear()
            logger.info("Cleared cache (%d entries)", count)


_instance: Optional[CachePredictor] = None
_instance_lock = threading.RLock()


def get_cache_predictor() -> CachePredictor:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = CachePredictor()
            logger.info("Created CachePredictor singleton")
        return _instance
