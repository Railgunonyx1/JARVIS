"""Telemetry — Latency Tracker + OpenTelemetry-style Tracer + LLM Observability."""

import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.telemetry")


@dataclass
class StageMetrics:
    """Metrics for a single pipeline stage."""
    name: str
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float('inf')
    max_ms: float = 0.0
    errors: int = 0
    last_ms: float = 0.0

    def record(self, ms: float, error: bool = False) -> None:
        self.count += 1
        self.total_ms += ms
        self.min_ms = min(self.min_ms, ms)
        self.max_ms = max(self.max_ms, ms)
        self.last_ms = ms
        if error:
            self.errors += 1

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "count": self.count,
            "avg_ms": round(self.avg_ms, 2),
            "min_ms": round(self.min_ms, 2) if self.min_ms != float('inf') else 0,
            "max_ms": round(self.max_ms, 2),
            "errors": self.errors,
            "last_ms": round(self.last_ms, 2),
        }


class LatencyTracker:
    """Tracks latency across all pipeline stages."""

    def __init__(self, max_history: int = 1000):
        self._stages: dict[str, StageMetrics] = {}
        self._history: list[dict[str, Any]] = []
        self._max_history = max_history
        self._lock = threading.Lock()
        self._current_request: dict[str, float] = {}
        self._request_start: float = 0.0

    def start_request(self) -> None:
        """Mark the start of a new request."""
        with self._lock:
            self._request_start = time.perf_counter()
            self._current_request.clear()

    def mark(self, stage: str) -> None:
        """Mark a stage completion."""
        now = time.perf_counter()
        with self._lock:
            if stage not in self._current_request:
                self._current_request[stage] = now
            else:
                ms = (now - self._current_request[stage]) * 1000
                stage_name = stage.replace("start_", "").replace("end_", "")
                if stage_name not in self._stages:
                    self._stages[stage_name] = StageMetrics(stage_name)
                self._stages[stage_name].record(ms)
                self._current_request[stage] = now

    def mark_error(self, stage: str) -> None:
        """Record an error for a stage."""
        with self._lock:
            stage_name = stage.replace("start_", "").replace("end_", "")
            # Record elapsed time if stage was tracking, otherwise use minimal value
            if stage_name in self._stages:
                # Use existing stage metrics, record error on current interval
                elapsed = time.perf_counter() * 1000  # rough estimate
                self._stages[stage_name].record(elapsed, error=True)
            else:
                # Stage wasn't being tracked; record minimal time with error flag
                self._stages[stage_name] = StageMetrics(stage_name)
                self._stages[stage_name].record(1.0, error=True)  # 1ms minimum

    def end_request(self) -> dict[str, float]:
        """End the current request and return stage timings."""
        now = time.perf_counter()
        with self._lock:
            total_ms = (now - self._request_start) * 1000
            result = {}
            for stage, start_time in self._current_request.items():
                if stage.startswith("start_"):
                    stage_name = stage[6:]
                    ms = (now - start_time) * 1000
                    result[stage_name] = round(ms, 2)
            self._history.append({
                "timestamp": time.time(),
                "total_ms": round(total_ms, 2),
                "stages": result,
            })
            if len(self._history) > self._max_history:
                self._history.pop(0)
            self._current_request.clear()
            return result

    @contextmanager
    def track(self, stage: str):
        """Context manager to track a stage."""
        start = time.perf_counter()
        try:
            yield
        except Exception:
            self.mark_error(stage)
            raise
        finally:
            ms = (time.perf_counter() - start) * 1000
            self._record_stage(stage, ms, error=False)

    def _record_stage(self, stage: str, ms: float, error: bool = False) -> None:
        with self._lock:
            if stage not in self._stages:
                self._stages[stage] = StageMetrics(stage)
            self._stages[stage].record(ms, error=error)

    def get_summary(self) -> dict[str, Any]:
        """Get summary of all tracked stages."""
        with self._lock:
            return {
                "stages": {name: m.to_dict() for name, m in self._stages.items()},
                "recent_requests": self._history[-10:] if self._history else [],
            }

    def print_summary(self) -> None:
        """Print formatted summary to console."""
        summary = self.get_summary()
        print("\n=== LATENCY REPORT ===")
        print(f"{'Stage':<25} {'Count':>6} {'Avg ms':>8} {'Min ms':>8} {'Max ms':>8} {'Errors':>6}")
        print("-" * 70)
        for name, metrics in sorted(summary["stages"].items()):
            print(f"{name:<25} {metrics['count']:>6} {metrics['avg_ms']:>8.1f} "
                  f"{metrics['min_ms']:>8.1f} {metrics['max_ms']:>8.1f} {metrics['errors']:>6}")
        print("-" * 70)

    def save_json(self, path: str | Path) -> None:
        """Save history to JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._history, f, indent=2)


_telemetry: LatencyTracker | None = None


def get_tracker() -> LatencyTracker:
    """Get global latency tracker instance."""
    global _telemetry
    if _telemetry is None:
        _telemetry = LatencyTracker()
    return _telemetry


def reset_tracker() -> LatencyTracker:
    """Reset and get new tracker."""
    global _telemetry
    _telemetry = LatencyTracker()
    return _telemetry


# Stage name constants for consistency
class Stages:
    WAKE_DETECT = "wake_detect"
    VAD_START = "vad_start"
    VAD_END = "vad_end"
    STT = "stt"
    INTENT_ROUTE = "intent_route"
    MEMORY_RETRIEVE = "memory_retrieve"
    PROMPT_BUILD = "prompt_build"
    LLM_FIRST_TOKEN = "llm_first_token"
    LLM_COMPLETE = "llm_complete"
    TOOL_EXECUTE = "tool_execute"
    TTS_START = "tts_start"
    TTS_FIRST_CHUNK = "tts_first_chunk"
    TTS_COMPLETE = "tts_complete"
    UI_UPDATE = "ui_update"
    TOTAL = "total"


# ── OpenTelemetry-style Tracer ───────────────────────────────

@dataclass
class Span:
    """A single span in a trace — analogous to OpenTelemetry Span."""
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    start_time: float = field(default_factory=time.perf_counter)
    end_time: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    status: str = "OK"  # OK | ERROR

    def finish(self):
        self.end_time = time.perf_counter()

    @property
    def duration_ms(self) -> float:
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000

    def add_event(self, name: str, attributes: dict | None = None):
        self.events.append({
            "name": name,
            "timestamp": time.perf_counter(),
            "attributes": attributes or {},
        })

    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events,
        }


class TraceProvider:
    """Creates and manages traces (collections of spans).

    Each trace has a unique trace_id. Spans within a trace form a
    parent-child tree. Thread-safe.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._traces: dict[str, list[Span]] = defaultdict(list)
        self._active_spans: dict[str, Span] = {}  # span_id -> Span (per thread)

    def start_trace(self, name: str, attributes: dict | None = None) -> Span:
        """Begin a new trace with a root span."""
        trace_id = str(uuid.uuid4())[:16]
        span_id = str(uuid.uuid4())[:16]
        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=span_id,
            attributes=attributes or {},
        )
        with self._lock:
            self._traces[trace_id].append(span)
            self._active_spans[span_id] = span
        return span

    def start_span(self, name: str, parent: Span | None = None,
                   attributes: dict | None = None) -> Span:
        """Create a child span. If no parent, starts a new trace."""
        span_id = str(uuid.uuid4())[:16]
        if parent is not None:
            trace_id = parent.trace_id
            parent_span_id = parent.span_id
        else:
            trace_id = str(uuid.uuid4())[:16]
            parent_span_id = None
        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            attributes=attributes or {},
        )
        with self._lock:
            self._traces[trace_id].append(span)
            self._active_spans[span_id] = span
        return span

    def end_span(self, span: Span, status: str = "OK"):
        span.finish()
        span.status = status
        with self._lock:
            self._active_spans.pop(span.span_id, None)

    @contextmanager
    def span(self, name: str, parent: Span | None = None,
             attributes: dict | None = None):
        """Context manager: creates, yields, and auto-finishes a span."""
        s = self.start_span(name, parent=parent, attributes=attributes)
        try:
            yield s
        except Exception as e:
            self.end_span(s, status="ERROR")
            s.set_attribute("error", str(e))
            raise
        else:
            self.end_span(s)

    def get_trace(self, trace_id: str) -> list[Span]:
        with self._lock:
            return list(self._traces.get(trace_id, []))

    def get_all_traces(self) -> dict[str, list[Span]]:
        with self._lock:
            return {tid: list(spans) for tid, spans in self._traces.items()}

    def export_json(self) -> list[dict]:
        with self._lock:
            result = []
            for tid, spans in self._traces.items():
                for s in spans:
                    result.append(s.to_dict())
            return result


# ── LLM Observability (Langfuse-style) ──────────────────────

@dataclass
class LLMCallRecord:
    """Tracks a single LLM call — prompt, response, tokens, latency, cost."""
    model: str
    prompt: str
    completion: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    cost: float = 0.0
    trace_id: str = ""
    span_id: str = ""
    timestamp: float = field(default_factory=time.time)
    status: str = "OK"  # OK | ERROR
    error: str = ""

    COST_PER_1K = {
        "gpt-4": {"prompt": 0.03, "completion": 0.06},
        "gpt-4o": {"prompt": 0.01, "completion": 0.03},
        "gpt-4o-mini": {"prompt": 0.0015, "completion": 0.006},
        "claude-3-haiku": {"prompt": 0.0025, "completion": 0.0125},
        "claude-3.5-sonnet": {"prompt": 0.003, "completion": 0.015},
        "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
        "llama-3": {"prompt": 0.0005, "completion": 0.0008},
        "mixtral": {"prompt": 0.0004, "completion": 0.0006},
    }
    DEFAULT_COST = {"prompt": 0.001, "completion": 0.002}

    def calculate_cost(self):
        rates = self.COST_PER_1K.get(self.model, self.DEFAULT_COST)
        self.cost = (self.prompt_tokens * rates["prompt"]
                     + self.completion_tokens * rates["completion"]) / 1000

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "latency_ms": round(self.latency_ms, 2),
            "cost": round(self.cost, 6),
            "trace_id": self.trace_id,
            "status": self.status,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class LLMObservability:
    """Langfuse-style tracking of LLM calls."""

    def __init__(self, max_records: int = 5000):
        self._records: list[LLMCallRecord] = []
        self._max_records = max_records
        self._lock = threading.Lock()
        self._session_start = time.time()

    def record(self, model: str, prompt: str, completion: str = "",
               prompt_tokens: int = 0, completion_tokens: int = 0,
               latency_ms: float = 0.0, trace_id: str = "",
               span_id: str = "", status: str = "OK", error: str = "") -> LLMCallRecord:
        rec = LLMCallRecord(
            model=model,
            prompt=prompt,
            completion=completion,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            trace_id=trace_id,
            span_id=span_id,
            status=status,
            error=error,
        )
        rec.calculate_cost()
        with self._lock:
            self._records.append(rec)
            if len(self._records) > self._max_records:
                self._records.pop(0)
        return rec

    def get_stats(self) -> dict:
        with self._lock:
            total = len(self._records)
            if total == 0:
                return {"total_calls": 0, "total_tokens": 0, "total_cost": 0.0}
            total_tokens = sum(r.prompt_tokens + r.completion_tokens for r in self._records)
            total_cost = sum(r.cost for r in self._records)
            errors = sum(1 for r in self._records if r.status == "ERROR")
            model_breakdown = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})
            for r in self._records:
                mb = model_breakdown[r.model]
                mb["calls"] += 1
                mb["tokens"] += r.prompt_tokens + r.completion_tokens
                mb["cost"] += r.cost
            return {
                "total_calls": total,
                "total_tokens": total_tokens,
                "total_cost": round(total_cost, 4),
                "errors": errors,
                "avg_latency_ms": round(sum(r.latency_ms for r in self._records) / total, 2),
                "session_duration_s": round(time.time() - self._session_start, 1),
                "model_breakdown": dict(model_breakdown),
            }

    def recent_calls(self, n: int = 10) -> list[dict]:
        with self._lock:
            return [r.to_dict() for r in self._records[-n:]]

    def export_json(self) -> list[dict]:
        with self._lock:
            return [r.to_dict() for r in self._records]


# ── Global instances ─────────────────────────────────────────

_trace_provider: TraceProvider | None = None
_llm_observability: LLMObservability | None = None


def get_trace_provider() -> TraceProvider:
    global _trace_provider
    if _trace_provider is None:
        _trace_provider = TraceProvider()
    return _trace_provider


def get_llm_observability() -> LLMObservability:
    global _llm_observability
    if _llm_observability is None:
        _llm_observability = LLMObservability()
    return _llm_observability
