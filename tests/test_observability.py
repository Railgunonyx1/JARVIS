"""Observability core tests (Sprint 0 — instrument first).

Prove the span/trace engine, contextvar propagation across asyncio task
boundaries, the bounded recent ring, metric accumulation, and the SQLite
exporter round-trip (WAL writer thread → read helpers). All writes go to
temp dirs via an explicit ``db_path`` so the user's ``~/.jarvis/perf.db``
is never touched.
"""

import asyncio
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.base import LLMProvider
from runtime.observability import (
    SqliteExporter,
    perf_db_path,
    read_latest,
    read_slowest,
    read_summary,
    reset_tracer,
)
from runtime.observability.spans import Span


@pytest.fixture(autouse=True)
def _clean_tracer():
    tracer = reset_tracer()
    yield tracer
    reset_tracer()


def _wait_for(condition, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


# ── tracer: trace lifecycle ──────────────────────────────────────────────


def test_begin_end_snapshot_shape(_clean_tracer):
    tracer = _clean_tracer
    root = tracer.begin("run: fix the bug", {"goal": "g"})
    assert root is not None
    assert root.name == "request"
    assert root.attributes["command"] == "run: fix the bug"
    assert root.parent_id is None

    trace = tracer.end(root)
    assert trace is not None
    assert trace["command"] == "run: fix the bug"
    assert trace["status"] == "OK"
    assert trace["total_ms"] >= 0.0
    assert [s["name"] for s in trace["spans"]] == ["request"]


def test_end_idempotent(_clean_tracer):
    tracer = _clean_tracer
    root = tracer.begin("cmd")
    assert tracer.end(root) is not None
    assert tracer.end(root) is None


def test_span_tree_and_parent_links(_clean_tracer):
    tracer = _clean_tracer
    root = tracer.begin("cmd")
    with tracer.span("memory.retrieve"):
        with tracer.span("provider.complete") as span:
            span.set_attribute("provider", "groq")
    trace = tracer.end(root)
    spans = {s["name"]: s for s in trace["spans"]}
    assert spans["memory.retrieve"]["parent_id"] == spans["request"]["span_id"]
    assert spans["provider.complete"]["parent_id"] == spans["memory.retrieve"]["span_id"]
    assert spans["provider.complete"]["attributes"]["provider"] == "groq"


def test_span_error_status(_clean_tracer):
    tracer = _clean_tracer
    root = tracer.begin("cmd")
    with pytest.raises(RuntimeError):
        with tracer.span("tool.execute"):
            raise RuntimeError("boom")
    trace = tracer.end(root)
    spans = {s["name"]: s for s in trace["spans"]}
    assert spans["tool.execute"]["status"] == "ERROR"
    assert "boom" in (spans["tool.execute"]["error"] or "")
    assert trace["status"] == "OK"


def test_trace_context_manager_error(_clean_tracer):
    tracer = _clean_tracer
    with pytest.raises(ValueError):
        with tracer.trace("cmd"):
            raise ValueError("nope")
    recent = tracer.recent(1)
    assert recent and recent[0]["status"] == "ERROR"


def test_metrics_accumulate(_clean_tracer):
    tracer = _clean_tracer
    root = tracer.begin("cmd")
    tracer.add_metric("tokens", 123)
    tracer.add_metric("tokens", 77)
    trace = tracer.end(root)
    assert trace["metrics"] == {"tokens": 200}


def test_recent_ring_bounded(_clean_tracer):
    tracer = _clean_tracer
    for i in range(30):
        tracer.end(tracer.begin(f"cmd{i}"))
    assert len(tracer.recent(100)) == 30
    assert tracer.recent(5)[0]["command"] == "cmd25"


def test_disabled_tracer_records_nothing():
    from runtime.observability.tracer import Tracer

    tracer = Tracer(enabled=False)
    assert tracer.begin("cmd") is None
    with tracer.span("phase") as span:
        assert span is None
    assert tracer.recent(10) == []


def test_trace_enabled_config_gating(monkeypatch):
    from runtime.observability.config import trace_enabled

    monkeypatch.setenv("JARVIS_TRACE", "0")
    assert trace_enabled() is False
    monkeypatch.delenv("JARVIS_TRACE")
    assert trace_enabled() is True


def test_perf_db_path_override(monkeypatch, tmp_path):
    custom = tmp_path / "custom" / "perf.db"
    monkeypatch.setenv("JARVIS_OBSERVABILITY_DB", str(custom))
    assert perf_db_path() == custom


# ── tracer: asyncio context propagation ──────────────────────────────────


def test_span_crosses_asyncio_task_boundaries():
    tracer = reset_tracer()

    async def inner():
        with tracer.span("provider.complete"):
            await asyncio.sleep(0.01)

    async def main():
        root = tracer.begin("cmd")
        task = asyncio.create_task(inner())
        await task
        return tracer.end(root)

    trace = asyncio.run(main())
    spans = {s["name"]: s for s in trace["spans"]}
    assert spans["provider.complete"]["parent_id"] == spans["request"]["span_id"]


# ── provider KPIs: TTFT + token metrics ──────────────────────────────────


class _FakeStreamProvider(LLMProvider):
    """In-memory provider that streams two chunks after a small delay."""

    def __init__(self):
        super().__init__("fake", {"model": "fake-model"})

    async def complete(self, messages, system_prompt=None, max_tokens=None,
                       temperature=None, tools=None, model=None):
        from providers.types import LLMResponse

        return LLMResponse(text="hi", model="fake-model", provider="fake", tokens_used=1)

    async def complete_stream(self, messages, system_prompt=None, max_tokens=None,
                              temperature=None, tools=None):
        await asyncio.sleep(0.01)
        yield "Hello"
        yield " world"


@pytest.fixture()
def stream_router():
    from providers.router import ProviderRouter

    router = ProviderRouter(config={}, api_keys={})
    router._providers["fake"] = _FakeStreamProvider()
    router._chain = ["fake"]
    return router


def test_router_stream_ttft_and_token_kpis(stream_router):
    tracer = reset_tracer()

    async def consume():
        root = tracer.begin("run: stream")
        chunks = []
        async for chunk in stream_router.complete_stream([{"role": "user", "content": "hi"}]):
            chunks.append(chunk)
        return tracer.end(root), chunks

    trace, chunks = asyncio.run(consume())
    assert "".join(chunks) == "Hello world"
    spans = {s["name"]: s for s in trace["spans"]}
    llm = spans["llm.request"]
    assert llm["status"] == "OK"
    assert llm["attributes"]["provider"] == "fake"
    assert llm["attributes"]["model"] == "fake-model"
    assert llm["attributes"]["ttft_ms"] >= 0.0
    assert llm["attributes"]["tokens_estimated"] == max(1, len("Hello world") // 4)
    assert llm["attributes"]["tokens_per_second"] >= 0.0
    assert trace["metrics"]["llm.tokens_generated"] >= 1
    assert trace["metrics"]["llm.ttft_ms"] >= 0.0
    events = {e["name"] for e in llm.get("events", [])}
    assert "first_token" in events


def test_router_complete_records_tokens(stream_router):
    tracer = reset_tracer()

    async def call():
        root = tracer.begin("run: complete")
        response = await stream_router.complete([{"role": "user", "content": "hi"}])
        return tracer.end(root), response

    trace, response = asyncio.run(call())
    assert response.text == "hi"
    spans = {s["name"]: s for s in trace["spans"]}
    assert spans["router.complete"]["attributes"]["tokens"] == 1
    assert trace["metrics"]["llm.tokens_generated"] == 1


def test_router_stream_marks_failed_attempt_error(stream_router):
    tracer = reset_tracer()

    async def _raise_runtime(*a, **k):
        raise RuntimeError("stream boom")
        yield  # pragma: no cover

    stream_router._providers["fake"].complete_stream = _raise_runtime

    async def consume():
        root = tracer.begin("run: fail")
        with pytest.raises(RuntimeError):
            async for _ in stream_router.complete_stream([{"role": "user", "content": "hi"}]):
                pass
        return tracer.end(root)

    trace = asyncio.run(consume())
    spans = {s["name"]: s for s in trace["spans"]}
    assert spans["llm.request"]["status"] == "ERROR"
    assert "boom" in (spans["llm.request"]["error"] or "")


# ── exporter: SQLite round-trip ──────────────────────────────────────────


def test_sqlite_exporter_round_trip(tmp_path):
    db = tmp_path / "perf.db"
    exporter = SqliteExporter(db_path=db, flush_interval=0.05)
    tracer = reset_tracer()
    tracer.set_sink(exporter.sink)
    exporter.start()

    root = tracer.begin("run: round trip")
    with tracer.span("memory.retrieve"):
        time.sleep(0.01)
    tracer.add_metric("tokens", 42)
    trace = tracer.end(root)
    assert trace is not None

    exporter.stop()
    assert db.exists()

    latest = read_latest(db, limit=5)
    assert len(latest) == 1
    got = latest[0]
    assert got["trace_id"] == trace["trace_id"]
    assert got["command"] == "run: round trip"
    assert got["status"] == "OK"
    names = [s["name"] for s in got["spans"]]
    assert names == ["request", "memory.retrieve"]
    assert got["metrics"]["tokens"] == 42.0


def test_sqlite_exporter_multiple_traces_order(tmp_path):
    db = tmp_path / "perf.db"
    exporter = SqliteExporter(db_path=db, flush_interval=0.05)
    tracer = reset_tracer()
    tracer.set_sink(exporter.sink)
    exporter.start()
    for i in range(3):
        tracer.end(tracer.begin(f"cmd{i}"))
    exporter.stop()

    latest = read_latest(db, limit=5)
    assert [t["command"] for t in latest] == ["cmd2", "cmd1", "cmd0"]
    slowest = read_slowest(db, limit=5)
    assert set(t["command"] for t in slowest) == {"cmd0", "cmd1", "cmd2"}


def test_sqlite_exporter_summary(tmp_path):
    db = tmp_path / "perf.db"
    exporter = SqliteExporter(db_path=db, flush_interval=0.05)
    tracer = reset_tracer()
    tracer.set_sink(exporter.sink)
    exporter.start()
    for i in range(2):
        root = tracer.begin(f"cmd{i}")
        with tracer.span("memory.retrieve"):
            time.sleep(0.005)
        tracer.end(root)
    exporter.stop()

    summary = read_summary(db)
    assert summary["traces"]["count"] == 2
    assert summary["traces"]["avg_ms"] >= 0.0
    phases = {p["name"]: p for p in summary["phases"]}
    assert "memory.retrieve" in phases
    assert phases["memory.retrieve"]["count"] == 2


def test_exporter_drop_when_not_started(tmp_path):
    exporter = SqliteExporter(db_path=tmp_path / "perf.db")
    exporter.sink({"trace_id": "t"})  # writer not running → must not raise


def test_enable_disable_perf_singleton(tmp_path):
    db = tmp_path / "perf.db"
    from runtime.observability import disable_perf, enable_perf

    try:
        enable_perf(db_path=db)
        assert db.exists()
    finally:
        disable_perf()


def test_span_data_model():
    span = Span(
        name="phase",
        span_id="s1",
        trace_id="t1",
        parent_id="r1",
        start_ns=time.perf_counter_ns(),
        thread_id=threading.get_ident(),
        process_id=1,
    )
    span.finish()
    assert span.finished is True
    assert span.duration_ms() >= 0.0
    d = span.to_dict(span.start_ns)
    assert d["offset_ms"] == 0.0
    assert d["thread_id"] == threading.get_ident()
    span.record_event("started", {"x": 1})
    assert span.events[0]["name"] == "started"
