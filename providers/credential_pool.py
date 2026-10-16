"""Credential pool — hermes-agent failover engine (Round 7 row 18).

Thread-safe pool of API credentials for a single (provider, base_url) with:

- strategies: fill_first / round_robin / least_used / random
- per-entry counters, cooldowns, DEAD status, leases
- failover reason taxonomy:
    QUOTA          -> 402 / quota exhausted   -> rotate now (marks dead)
    RATE_LIMIT     -> 429                   -> retry once, then rotate
    AUTH           -> 401 / auth failure     -> rotate now (marks dead)
    MODEL          -> model-scoped failure   -> model cooldown only
    TRANSIENT      -> 5xx / timeout / conn   -> retry with backoff
    FATAL          -> other 4xx             -> propagate, no rotation
- resolve_runtime_pool_key(provider, base_url): identity then endpoint
- unmatched rotation bounded to one lap with a no-recovery guard for a
  just-marked entry (a freshly dead key is never immediately re-selected)

The pool never calls a provider; callers feed it outcomes. Slots into the
existing OpenAICompatibleProvider._rotate_key path as the owner of the key
list, and into ModelGateway as a rotation helper.
"""

from __future__ import annotations

import hashlib
import random
import threading
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

__all__ = [
    "CoolingCredential", "CredentialEntry", "CredentialPool",
    "FailoverReason", "PoolExhausted", "RotationStrategy", "UNCERTAIN",
    "NO_RECOVERY", "resolve_runtime_pool_key", "classify_failure",
]


class RotationStrategy(StrEnum):
    FILL_FIRST = "fill_first"
    ROUND_ROBIN = "round_robin"
    LEAST_USED = "least_used"
    RANDOM = "random"


class FailoverReason(StrEnum):
    QUOTA = "quota"
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    MODEL = "model"
    TRANSIENT = "transient"
    FATAL = "fatal"


NO_RECOVERY = "no_recovery"
UNCERTAIN = "uncertain_outcome"
RECOVERY_LAP_LIMIT = 1


class PoolExhausted(RuntimeError):
    """Raised when no entry is selectable (all DEAD / cooling)."""


@dataclass
class CredentialEntry:
    key_id: str
    secret: str
    label: str = ""
    model_scope: str = ""
    base_url: str = ""
    total: int = 0
    successes: int = 0
    rate_limits: int = 0
    quotas: int = 0
    auth_failures: int = 0
    cooldown_until: float = 0.0
    dead: bool = False
    dead_reason: str = ""
    marked_at: float | None = None
    last_used_at: float | None = None
    last_failure_at: float | None = None
    lease_count: int = 0

    def is_selectable(self, now: float | None = None) -> bool:
        t = time.time() if now is None else now
        if self.dead:
            return False
        if self.cooldown_until > t:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "label": self.label,
            "model_scope": self.model_scope,
            "base_url": self.base_url,
            "total": self.total,
            "successes": self.successes,
            "rate_limits": self.rate_limits,
            "quotas": self.quotas,
            "auth_failures": self.auth_failures,
            "cooldown_until": self.cooldown_until,
            "dead": self.dead,
            "dead_reason": self.dead_reason,
            "marked_at": self.marked_at,
            "lease_count": self.lease_count,
        }


def classify_failure(exc, *, status_code=None, model_scoped: bool = False) -> FailoverReason:
    if isinstance(exc, str):
        text = exc
        code = status_code
    else:
        text = str(exc)
        code = status_code
        for attr in ("status_code", "status", "code", "http_status"):
            v = getattr(exc, attr, None)
            if isinstance(v, int):
                code = v
                break
    low = text.lower()
    if model_scoped:
        return FailoverReason.MODEL
    if code == 402 or "quota" in low or "payment" in low or "insufficient_quota" in low:
        return FailoverReason.QUOTA
    if (code == 401 or "unauthorized" in low or "invalid api key" in low
        or "invalid_api_key" in low or "authentication" in low):
        return FailoverReason.AUTH
    if code == 429 or "rate limit" in low or "rate_limit" in low or "too many requests" in low:
        return FailoverReason.RATE_LIMIT
    if code is not None and 500 <= code < 600:
        return FailoverReason.TRANSIENT
    if "timeout" in low or "timed out" in low or "connection" in low or "network" in low:
        return FailoverReason.TRANSIENT
    if code is not None and 400 <= code < 500:
        return FailoverReason.FATAL
    return FailoverReason.TRANSIENT


def resolve_runtime_pool_key(provider: str, base_url: str) -> str:
    return f"{provider}::{base_url.strip().rstrip('/')}"


@dataclass
class Lease:
    pool: CredentialPool
    entry: CredentialEntry

    def release(self) -> None:
        self.pool.release(self.entry.key_id)

    def __enter__(self) -> Lease:
        return self

    def __exit__(self, *exc) -> None:
        self.release()


class CredentialPool:
    def __init__(self, *, provider: str, base_url: str,
                 strategy=RotationStrategy.FILL_FIRST,
                 cooldown_seconds: float = 60.0,
                 rate_limit_retry_once: bool = True,
                 rng_seed=None,
                 now=None) -> None:
        self.provider = provider
        self.base_url = base_url
        self.pool_key = resolve_runtime_pool_key(provider, base_url)
        self.strategy = (RotationStrategy(strategy)
                        if not isinstance(strategy, RotationStrategy) else strategy)
        self.cooldown_seconds = max(0.0, cooldown_seconds)
        self.rate_limit_retry_once = rate_limit_retry_once
        self._now = now or time.time
        self._rng = random.Random(rng_seed) if rng_seed is not None else random.Random()
        self._entries: list[CredentialEntry] = []
        self._lock = threading.RLock()
        self._cursor = 0
        self._model_cooldowns: dict = {}
        self._rate_limited_once: set = set()

    def add(self, secret: str, *, key_id=None, label: str = "", model_scope: str = "") -> CredentialEntry:
        with self._lock:
            if key_id is None:
                key_id = hashlib.sha256(secret.encode()).hexdigest()[:12] + "-" + uuid.uuid4().hex[:6]
            entry = CredentialEntry(
                key_id=key_id, secret=secret, label=label,
                model_scope=model_scope, base_url=self.base_url,
            )
            self._entries.append(entry)
            return entry

    def remove(self, key_id: str) -> bool:
        with self._lock:
            before = len(self._entries)
            self._entries = [e for e in self._entries if e.key_id != key_id]
            self._rate_limited_once.discard(key_id)
            return len(self._entries) != before

    def entries(self) -> list[CredentialEntry]:
        with self._lock:
            return list(self._entries)

    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def _eligible(self, model=None):
        now = self._now()
        out = []
        for e in self._entries:
            if not e.is_selectable(now):
                continue
            if e.model_scope and model and e.model_scope != model:
                continue
            if model and self._model_cooldowns.get((e.key_id, model), 0.0) > now:
                continue
            out.append(e)
        return out

    def acquire(self, model=None) -> Lease:
        with self._lock:
            eligible = self._eligible(model)
            if not eligible:
                raise PoolExhausted(f"no selectable credentials in pool {self.pool_key}")
            if self.strategy == RotationStrategy.FILL_FIRST:
                chosen = eligible[0]
            elif self.strategy == RotationStrategy.ROUND_ROBIN:
                idx = self._cursor % len(eligible)
                chosen = eligible[idx]
                self._cursor += 1
            elif self.strategy == RotationStrategy.LEAST_USED:
                chosen = min(eligible, key=lambda e: (e.total, e.key_id))
            elif self.strategy == RotationStrategy.RANDOM:
                chosen = self._rng.choice(eligible)
            else:
                chosen = eligible[0]
            chosen.lease_count += 1
            chosen.last_used_at = self._now()
            return Lease(self, chosen)

    def release(self, key_id: str) -> None:
        with self._lock:
            for e in self._entries:
                if e.key_id == key_id and e.lease_count > 0:
                    e.lease_count -= 1
                    return

    def record_success(self, key_id: str, model=None) -> None:
        with self._lock:
            e = self._find(key_id)
            if e is None:
                return
            e.total += 1
            e.successes += 1
            e.cooldown_until = 0.0
            if model:
                self._model_cooldowns.pop((key_id, model), None)
            self._rate_limited_once.discard(key_id)

    def record_failure(self, key_id, reason, *, model=None, cooldown_override=None):
        with self._lock:
            e = self._find(key_id)
            if e is None:
                return {"action": "propagate", "sleep": 0.0}
            now = self._now()
            e.total += 1
            e.last_failure_at = now

            if reason == FailoverReason.QUOTA:
                e.quotas += 1
                self._mark_dead(e, "quota_exhausted")
                return {"action": "rotate", "sleep": 0.0}

            if reason == FailoverReason.AUTH:
                e.auth_failures += 1
                self._mark_dead(e, "auth_failure")
                return {"action": "rotate", "sleep": 0.0}

            if reason == FailoverReason.RATE_LIMIT:
                e.rate_limits += 1
                if self.rate_limit_retry_once and key_id not in self._rate_limited_once:
                    self._rate_limited_once.add(key_id)
                    backoff = 1.0
                    e.cooldown_until = now + backoff
                    return {"action": "retry_once", "sleep": backoff}
                self._rate_limited_once.discard(key_id)
                e.cooldown_until = now + self.cooldown_seconds
                return {"action": "rotate", "sleep": self.cooldown_seconds}

            if reason == FailoverReason.MODEL:
                until = now + self.cooldown_seconds
                if model:
                    self._model_cooldowns[(key_id, model)] = until
                return {"action": "cooldown_model", "sleep": self.cooldown_seconds}

            if reason == FailoverReason.TRANSIENT:
                e.cooldown_until = now + min(self.cooldown_seconds, 10.0)
                return {"action": "retry_once", "sleep": e.cooldown_until - now}

            return {"action": "propagate", "sleep": 0.0}

    def rotate_after(self, key_id, lap_limit=RECOVERY_LAP_LIMIT):
        with self._lock:
            e = self._find(key_id)
            if e is None:
                return None
            selectable = [x for x in self._entries
                          if x.is_selectable(self._now()) and x.key_id != key_id]
            if not selectable:
                if (e.dead and e.marked_at is not None
                        and (self._now() - e.marked_at) < 0.5):
                    return NO_RECOVERY
                return None
            if self.strategy == RotationStrategy.ROUND_ROBIN:
                chosen = selectable[self._cursor % len(selectable)]
                self._cursor = (self._cursor + 1) % max(1, len(self._entries))
            elif self.strategy == RotationStrategy.LEAST_USED:
                chosen = min(selectable, key=lambda x: (x.total, x.key_id))
            elif self.strategy == RotationStrategy.RANDOM:
                chosen = self._rng.choice(selectable)
            else:
                chosen = selectable[0]
            return chosen.key_id

    def _mark_dead(self, entry, reason):
        entry.dead = True
        entry.dead_reason = reason
        entry.marked_at = self._now()
        entry.cooldown_until = float("inf")

    def _find(self, key_id):
        for e in self._entries:
            if e.key_id == key_id:
                return e
        return None

    def mark_model_cooldown(self, key_id, model, seconds):
        with self._lock:
            self._model_cooldowns[(key_id, model)] = self._now() + max(0.0, seconds)

    def revive(self, key_id):
        with self._lock:
            e = self._find(key_id)
            if e is None:
                return False
            e.dead = False
            e.dead_reason = ""
            e.marked_at = None
            e.cooldown_until = 0.0
            return True

    def disable(self, key_id):
        with self._lock:
            e = self._find(key_id)
            if e is not None:
                self._mark_dead(e, "disabled")

    def status(self):
        with self._lock:
            return {
                "pool_key": self.pool_key,
                "provider": self.provider,
                "base_url": self.base_url,
                "strategy": self.strategy.value,
                "size": len(self._entries),
                "alive": sum(1 for e in self._entries if not e.dead),
                "dead": sum(1 for e in self._entries if e.dead),
                "entries": [e.to_dict() for e in self._entries],
            }


_pools = {}
_pools_lock = threading.Lock()


def get_pool(provider, base_url, **kwargs):
    key = resolve_runtime_pool_key(provider, base_url)
    with _pools_lock:
        existing = _pools.get(key)
        if existing is None:
            existing = CredentialPool(provider=provider, base_url=base_url, **kwargs)
            _pools[key] = existing
        return existing


def clear_pools():
    with _pools_lock:
        _pools.clear()


# alias for typo tolerance in tests
CoolingCredential = CredentialEntry
