"""Concurrency and lifecycle tests for the desktop agent backend."""

from __future__ import annotations

import asyncio
import queue
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest

from app.integration.jarvis_backend import BackendState, JarvisBackend


class _FakeTask:
    def __init__(self):
        self.cancel_calls = 0

    def done(self):
        return False

    def cancel(self):
        self.cancel_calls += 1


class _ClosedLoop:
    def call_soon_threadsafe(self, *_args):
        raise RuntimeError("event loop is closed")


class _FakeThread:
    def __init__(self, *, alive: bool, ident: int | None = 1):
        self.alive = alive
        self.ident = ident
        self.join_calls = []

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.join_calls.append(timeout)


def test_full_queue_does_not_consume_request_id():
    backend = JarvisBackend()
    backend._state = BackendState.READY
    backend._request_id_counter = 12
    backend._input_queue = queue.Queue(maxsize=1)
    backend._input_queue.put_nowait((99, "already queued"))

    assert backend.send_message("rejected") is None
    assert backend._request_id_counter == 12
    assert backend._input_queue.get_nowait() == (99, "already queued")


def test_cancel_request_never_cancels_task_from_caller_thread():
    backend = JarvisBackend()
    task = _FakeTask()
    backend._tasks_by_id[7] = task
    backend._loop = _ClosedLoop()

    assert backend.cancel_request(7) is False
    assert task.cancel_calls == 0


def test_stop_never_cancels_task_directly_when_loop_is_closed():
    backend = JarvisBackend()
    task = _FakeTask()
    worker = _FakeThread(alive=False)
    backend._state = BackendState.READY
    backend._current_task = task
    backend._loop = _ClosedLoop()
    backend._thread = worker

    assert backend.stop(timeout=0.01) is True
    assert task.cancel_calls == 0
    assert worker.join_calls == [0.01]
    assert backend.state is BackendState.STOPPED


def test_stop_checks_worker_even_if_state_already_says_stopped():
    backend = JarvisBackend()
    worker = _FakeThread(alive=True)
    backend._state = BackendState.STOPPED
    backend._thread = worker

    assert backend.stop(timeout=0.01) is False
    assert backend.state is BackendState.STOPPING
    assert worker.join_calls == [0.01]


def test_set_model_is_applied_on_agent_loop_thread():
    backend = JarvisBackend()
    applied = []
    router = SimpleNamespace(
        set_default_model=lambda model: applied.append(
            (model, threading.get_ident())
        )
    )

    class Loop:
        def call_soon_threadsafe(self, callback):
            self.worker = threading.Thread(target=callback)
            self.worker.start()

    loop = Loop()
    backend._state = BackendState.READY
    backend._loop = loop
    backend._agent_loop = SimpleNamespace(router=router)

    caller_thread = threading.get_ident()
    assert backend.set_model("provider/model") is True
    loop.worker.join(timeout=1.0)

    assert applied == [("provider/model", loop.worker.ident)]
    assert applied[0][1] != caller_thread


def test_set_model_returns_false_when_loop_cannot_schedule():
    backend = JarvisBackend()
    backend._state = BackendState.READY
    backend._loop = _ClosedLoop()
    backend._agent_loop = SimpleNamespace(
        router=SimpleNamespace(set_default_model=lambda _model: None)
    )

    assert backend.set_model("provider/model", timeout=0.01) is False


def test_shutdown_during_kernel_build_does_not_transition_to_ready(monkeypatch):
    backend = JarvisBackend()
    runtime = SimpleNamespace(agent_loop=object())
    closed = []

    runtime_package = ModuleType("runtime")
    runtime_package.__path__ = []
    kernel_module = ModuleType("runtime.kernel")

    def build_kernel(**_kwargs):
        backend._shutdown_event.set()
        return runtime

    kernel_module.build_kernel = build_kernel
    kernel_module.close_kernel = lambda value: closed.append(value)
    monkeypatch.setitem(sys.modules, "runtime", runtime_package)
    monkeypatch.setitem(sys.modules, "runtime.kernel", kernel_module)

    asyncio.run(backend._main())

    assert closed == [runtime]
    assert backend.state is BackendState.STOPPED
    assert backend._runtime is None
    assert backend._agent_loop is None


def test_shutdown_requested_before_kernel_build_skips_build(monkeypatch):
    backend = JarvisBackend()
    backend._shutdown_event.set()
    build_calls = []

    runtime_package = ModuleType("runtime")
    runtime_package.__path__ = []
    kernel_module = ModuleType("runtime.kernel")
    kernel_module.build_kernel = lambda **kwargs: build_calls.append(kwargs)
    kernel_module.close_kernel = lambda _runtime: None
    monkeypatch.setitem(sys.modules, "runtime", runtime_package)
    monkeypatch.setitem(sys.modules, "runtime.kernel", kernel_module)

    asyncio.run(backend._main())

    assert build_calls == []
    assert backend.state is BackendState.STOPPED


def test_start_rejects_a_previous_live_worker():
    backend = JarvisBackend()
    backend._state = BackendState.STOPPED
    backend._thread = _FakeThread(alive=True)

    with pytest.raises(RuntimeError, match="still shutting down"):
        backend.start(wait=False)


def test_start_reports_thread_creation_failure(monkeypatch):
    backend = JarvisBackend()

    class FailedThread:
        ident = None

        def __init__(self, **_kwargs):
            pass

        def is_alive(self):
            return False

        def start(self):
            raise RuntimeError("thread start failed")

    monkeypatch.setattr("app.integration.jarvis_backend.threading.Thread", FailedThread)

    with pytest.raises(RuntimeError, match="thread start failed"):
        backend.start(wait=False)

    assert backend.state is BackendState.ERROR
    assert str(backend.startup_error) == "thread start failed"


def test_restart_clears_stale_backend_state(monkeypatch):
    backend = JarvisBackend()
    backend._state = BackendState.ERROR
    backend._input_queue.put_nowait((5, "stale"))
    backend._tasks_by_id[5] = _FakeTask()
    backend._current_task = _FakeTask()
    backend._current_request_id = 5
    backend._agent_loop = object()
    backend._runtime = object()

    class NotStartedThread:
        ident = None

        def __init__(self, **_kwargs):
            pass

        def is_alive(self):
            return False

        def start(self):
            return None

    monkeypatch.setattr("app.integration.jarvis_backend.threading.Thread", NotStartedThread)

    backend.start(wait=False)

    assert backend.state is BackendState.STARTING
    assert backend._input_queue.empty()
    assert backend._tasks_by_id == {}
    assert backend._current_task is None
    assert backend._current_request_id is None
    assert backend._agent_loop is None
    assert backend._runtime is None
    assert backend._loop is None


def test_event_loop_creation_failure_sets_backend_error(monkeypatch):
    backend = JarvisBackend()
    backend._state = BackendState.STARTING

    def fail_new_loop():
        raise RuntimeError("event loop unavailable")

    monkeypatch.setattr(
        "app.integration.jarvis_backend.asyncio.new_event_loop",
        fail_new_loop,
    )

    backend._run_loop()

    assert backend.state is BackendState.ERROR
    assert str(backend.startup_error) == "event loop unavailable"



def test_queued_request_can_be_cancelled_before_execution():
    backend = JarvisBackend()
    backend._state = BackendState.READY
    cancelled = []
    backend.request_cancelled.connect(cancelled.append)

    request_id = backend.send_message("queued request")
    assert request_id is not None

    assert backend.cancel_request(request_id) is True
    assert cancelled == [request_id]
    assert request_id in backend._cancelled_request_ids
    assert backend._input_queue.get_nowait() == (request_id, "queued request")


def test_unknown_request_cannot_be_cancelled():
    backend = JarvisBackend()
    backend._state = BackendState.READY

    assert backend.cancel_request(9999) is False
