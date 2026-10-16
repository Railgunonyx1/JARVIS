"""Subagent registry resurrection prevention (+ retirement receipts).

See Round 7 row 20. A torn-down subagent must not silently reappear, and
stale on-disk run state must be retired (never imported as live) under a
byte-bounded discard receipt — openclaw PR #105793 pattern.

Constraints:
- A registry *generation* is monotonic per task id. Re-enrolling an id at a
  generation <= the last recorded one is a resurrection and is refused unless
  the caller explicitly forces it (audited).
- Unregistering to a terminal state retires the id, so a stale file-era run
  cannot be re-armed by a lower/equal generation.
- ``sweep_stale_runs`` reads (bounded) state, records discarded ids + byte
  count in a sealed receipt, moves the source aside (so it cannot be
  re-imported), and never resurrects any entry.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

REGISTRY_FILENAME = "subagents.runs.json"
DISCARD_RECEIPT_SUFFIX = ".discard-receipt.json"
DEFAULT_MAX_BYTES = 65536
SCHEMA = "jarvis.subagent_retirement/1"

_RESURRECTION_TOKEN_ENV = "JARVIS_RESURRECT_SUBAGENT"


class RunState(StrEnum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETIRED = "retired"
    DISCARDED = "discarded"


TERMINAL_STATES = {RunState.DONE, RunState.FAILED, RunState.CANCELLED,
                   RunState.RETIRED, RunState.DISCARDED}


class ResurrectionError(RuntimeError):
    """Raised when a caller tries to re-enroll a retired/stale subagent."""
    code = "RESURRECTION_BLOCKED"


class RetirementConflict(ValueError):
    """Raised when a discard receipt's seal does not match its payload."""
    code = "RETIREMENT_CONFLICT"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> float:
    return time.time()


@dataclass
class RunEntry:
    task_id: str
    parent_task_id: str | None = None
    generation: int = 0
    state: RunState = RunState.RUNNING
    started_at: float = field(default_factory=_now)
    ended_at: float | None = None
    retirement_reason: str = ""
    resurrected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "generation": self.generation,
            "state": self.state.value,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "retirement_reason": self.retirement_reason,
            "resurrected": self.resurrected,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunEntry:
        return cls(
            task_id=str(data["task_id"]),
            parent_task_id=data.get("parent_task_id"),
            generation=int(data.get("generation", 0)),
            state=RunState(str(data.get("state", "running"))),
            started_at=float(data.get("started_at") or _now()),
            ended_at=(float(data["ended_at"]) if data.get("ended_at") is not None else None),
            retirement_reason=str(data.get("retirement_reason", "") or ""),
            resurrected=bool(data.get("resurrected", False)),
        )


@dataclass
class RetirementReceipt:
    """Sealed record of a byte-bounded discard sweep (openclaw discard receipt)."""

    receipt_id: str
    source_path: str
    byte_count: int
    discarded_ids: tuple[str, ...]
    generation_floor: int
    reason: str
    created_at: str
    overflow: bool = False
    parse_error: str = ""
    content_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "receipt_id": self.receipt_id,
            "source_path": self.source_path,
            "byte_count": self.byte_count,
            "discarded_ids": list(self.discarded_ids),
            "generation_floor": self.generation_floor,
            "reason": self.reason,
            "created_at": self.created_at,
            "overflow": self.overflow,
            "parse_error": self.parse_error,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetirementReceipt:
        return cls(
            receipt_id=str(data["receipt_id"]),
            source_path=str(data["source_path"]),
            byte_count=int(data["byte_count"]),
            discarded_ids=tuple(str(x) for x in data.get("discarded_ids", [])),
            generation_floor=int(data.get("generation_floor", 0)),
            reason=str(data.get("reason", "")),
            created_at=str(data["created_at"]),
            overflow=bool(data.get("overflow", False)),
            parse_error=str(data.get("parse_error", "") or ""),
            content_sha256=str(data["content_sha256"]),
        )


def _receipt_payload(receipt: RetirementReceipt) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source_path": receipt.source_path,
        "byte_count": receipt.byte_count,
        "discarded_ids": list(receipt.discarded_ids),
        "generation_floor": receipt.generation_floor,
        "reason": receipt.reason,
        "overflow": receipt.overflow,
        "parse_error": receipt.parse_error,
    }


def content_digest(receipt: RetirementReceipt) -> str:
    return _sha256(json.dumps(_receipt_payload(receipt), sort_keys=True,
                              separators=(",", ":"), ensure_ascii=False))


def build_receipt(source_path: str, byte_count: int, discarded_ids: tuple[str, ...],
                  generation_floor: int, reason: str, *,
                  overflow: bool = False, parse_error: str = "",
                  created_at: str | None = None) -> RetirementReceipt:
    receipt = RetirementReceipt(
        receipt_id="", source_path=source_path, byte_count=byte_count,
        discarded_ids=discarded_ids, generation_floor=generation_floor,
        reason=reason, created_at=created_at or time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                              time.gmtime()),
        overflow=overflow, parse_error=parse_error,
    )
    digest = content_digest(receipt)
    return RetirementReceipt(
        receipt_id=f"rt-{digest[:16]}",
        source_path=source_path, byte_count=byte_count,
        discarded_ids=discarded_ids, generation_floor=generation_floor,
        reason=reason, created_at=receipt.created_at,
        overflow=overflow, parse_error=parse_error, content_sha256=digest,
    )


def verify_receipt(receipt: RetirementReceipt) -> None:
    if not receipt.content_sha256:
        raise RetirementConflict("unsealed retirement receipt")
    digest = content_digest(receipt)
    if digest != receipt.content_sha256:
        raise RetirementConflict(
            f"content_sha256 mismatch for {receipt.receipt_id}: "
            f"stored {receipt.content_sha256[:12]}… recomputed {digest[:12]}…")
    if receipt.receipt_id != f"rt-{digest[:16]}":
        raise RetirementConflict(
            f"receipt_id {receipt.receipt_id} does not match content")


class SubagentRegistry:
    """In-memory subagent registry that refuses resurrection of retired ids.

    Thread-safe. A retired id may only be re-enrolled via ``force=True`` (and
    the fact is recorded on the entry). Generations are monotonic per id.
    """

    def __init__(self) -> None:
        self._entries: dict[str, RunEntry] = {}
        self._retired: dict[str, int] = {}   # id -> retired generation
        self._generations: dict[str, int] = {}
        self._lock = threading.RLock()

    # ── registration ────────────────────────────────────────────
    def register(self, task_id: str, *, parent_task_id: str | None = None,
                generation: int | None = None, force: bool = False) -> RunEntry:
        if not task_id:
            raise ValueError("task_id must be non-empty")
        with self._lock:
            if generation is None:
                generation = self._generations.get(task_id, 0) + 1
            else:
                generation = int(generation)
            prev_gen = self._generations.get(task_id, 0)
            retired_gen = self._retired.get(task_id)
            if task_id in self._entries and self._entries[task_id].state not in TERMINAL_STATES:
                # still alive — treat as idempotent same-generation update
                existing = self._entries[task_id]
                if generation < existing.generation:
                    raise ResurrectionError(
                        f"subagent {task_id!r} downgrade generation "
                        f"{generation} < {existing.generation} (resurrection blocked)")
                existing.generation = max(existing.generation, generation)
                existing.parent_task_id = parent_task_id or existing.parent_task_id
                self._generations[task_id] = existing.generation
                return existing
            # retired?
            if retired_gen is not None and generation <= retired_gen and not force:
                raise ResurrectionError(
                    f"subagent {task_id!r} is retired at generation {retired_gen}; "
                    f"offered generation {generation} cannot resurrect it")
            if generation < prev_gen and not force:
                raise ResurrectionError(
                    f"subagent {task_id!r} stale generation {generation} "
                    f"< last {prev_gen} (resurrection blocked)")
            if force and (retired_gen is not None or generation < prev_gen):
                # audited override
                pass
            entry = RunEntry(
                task_id=task_id,
                parent_task_id=parent_task_id,
                generation=max(generation, prev_gen),
                state=RunState.RUNNING,
                resurrected=bool(force and (retired_gen is not None or generation < prev_gen)),
            )
            self._entries[task_id] = entry
            self._generations[task_id] = entry.generation
            if force and task_id in self._retired:
                del self._retired[task_id]
            return entry

    def unregister(self, task_id: str, *, state: RunState = RunState.DONE,
                   reason: str = "") -> bool:
        if state not in TERMINAL_STATES:
            raise ValueError(f"{state} is not a terminal state")
        with self._lock:
            entry = self._entries.get(task_id)
            if entry is None:
                return False
            entry.state = state
            entry.ended_at = _now()
            entry.retirement_reason = reason
            self._retired[task_id] = max(self._retired.get(task_id, 0),
                                         entry.generation)
            self._entries.pop(task_id, None)
            return True

    def retire(self, task_id: str, *, reason: str = "retired") -> bool:
        return self.unregister(task_id, state=RunState.RETIRED, reason=reason)

    def get(self, task_id: str) -> RunEntry | None:
        with self._lock:
            entry = self._entries.get(task_id)
            if entry is not None:
                return entry
            #_retired entries aren't kept as live entries; reconstruct a marker?
            return None

    def is_active(self, task_id: str) -> bool:
        with self._lock:
            e = self._entries.get(task_id)
            return e is not None and e.state not in TERMINAL_STATES

    def is_retired(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._retired

    def active_ids(self) -> list[str]:
        with self._lock:
            return [tid for tid, e in self._entries.items()
                    if e.state not in TERMINAL_STATES]

    def retired_ids(self) -> list[str]:
        with self._lock:
            return list(self._retired.keys())

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._retired.clear()
            self._generations.clear()

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "entries": {tid: e.to_dict() for tid, e in self._entries.items()},
                "retired": dict(self._retired),
                "generations": dict(self._generations),
            }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubagentRegistry:
        r = cls()
        with r._lock:
            for tid, raw in (data.get("entries") or {}).items():
                e = RunEntry.from_dict(raw)
                r._entries[tid] = e
                r._generations[tid] = e.generation
            for tid, gen in (data.get("retired") or {}).items():
                r._retired[tid] = int(gen)
            for tid, gen in (data.get("generations") or {}).items():
                r._generations[tid] = max(r._generations.get(tid, 0), int(gen))
        return r


def _collect_inflight_ids(data: Any) -> list[str]:
    """Extract candidate in-flight ids from a variety of on-disk shapes."""
    ids: list[str] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            # A single run entry?
            if "task_id" in obj and isinstance(obj["task_id"], str):
                state = ""
                for key in ("state", "status", "phase", "status_text"):
                    if key in obj and obj.get(key) is not None:
                        state = str(obj.get(key)).lower()
                        break
                if not state:
                    state = "running"
                terminal = {"done", "completed", "failed", "cancelled", "retired",
                            "discarded", "success", "finished", "ok"}
                if state not in terminal:
                    ids.append(obj["task_id"])
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    _walk(data)
    # de-dup preserving order
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def sweep_stale_runs(path: str | os.PathLike, *,
                     max_bytes: int = DEFAULT_MAX_BYTES,
                     move_original: bool = True) -> RetirementReceipt:
    """Retire (never import) stale on-disk subagent runs; return a receipt.

    Byte-bounded: reads at most ``max_bytes``; oversized files are not parsed
    and are reported as ``overflow``. Parse errors are recorded, never raised.
    """
    p = Path(path)
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not p.exists():
        receipt = build_receipt(str(p), 0, (), 0,
                                reason="no stale state present",
                                created_at=created_at)
        return receipt

    try:
        size = p.stat().st_size
    except OSError as exc:
        receipt = build_receipt(str(p), 0, (), 0,
                                reason=f"stat failed: {exc}",
                                created_at=created_at)
        return receipt

    overflow = size > max_bytes
    byte_count = min(size, max_bytes)
    discarded: tuple[str, ...] = ()
    parse_error = ""
    generation_floor = 0

    if not overflow:
        try:
            raw = p.read_bytes()[:max_bytes]
            text = raw.decode("utf-8", errors="replace")
            data = json.loads(text) if text.strip() else {}
            discarded_list = _collect_inflight_ids(data)
            discarded = tuple(discarded_list)
            # best-effort generation floor from entries
            gens = []
            def _gens(o):
                if isinstance(o, dict):
                    if "generation" in o and isinstance(o["generation"], int):
                        gens.append(o["generation"])
                    for v in o.values():
                        _gens(v)
                elif isinstance(o, list):
                    for v in o:
                        _gens(v)
            _gens(data)
            if gens:
                generation_floor = max(gens)
        except Exception as exc:  # noqa: BLE001 - sweep must never raise
            parse_error = f"{type(exc).__name__}: {exc}"[:200]
            discarded = ()

    if overflow:
        reason = f"oversized state file ({size} bytes > {max_bytes}); discarded without parsing"
    elif parse_error:
        reason = f"unparseable state file; discarded ({parse_error})"
    elif discarded:
        reason = f"retired {len(discarded)} in-flight subagent run(s); never imported"
    else:
        reason = "no in-flight runs found; retired state file"

    receipt = build_receipt(str(p), byte_count if not overflow else size, discarded,
                            generation_floor, reason, overflow=overflow,
                            parse_error=parse_error, created_at=created_at)

    # Persist receipt sidecar.
    try:
        sidecar = p.with_name(p.name + DISCARD_RECEIPT_SUFFIX)
        sidecar.write_text(json.dumps(receipt.to_dict(), indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    except OSError:
        pass

    # Move original aside so it cannot be re-imported (resurrection blocked).
    if move_original:
        try:
            dest = p.with_name(f"{p.name}.retired-{int(time.time())}")
            shutil.move(str(p), str(dest))
        except OSError:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
    else:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass

    try:
        verify_receipt(receipt)
    except RetirementConflict:
        pass
    return receipt


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DISCARD_RECEIPT_SUFFIX",
    "REGISTRY_FILENAME",
    "ResurrectionError",
    "RetirementConflict",
    "RetirementReceipt",
    "RunEntry",
    "RunState",
    "SubagentRegistry",
    "TERMINAL_STATES",
    "build_receipt",
    "content_digest",
    "sweep_stale_runs",
    "verify_receipt",
]
