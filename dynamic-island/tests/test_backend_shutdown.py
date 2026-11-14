"""Regression tests for bounded JARVIS backend and coordinator shutdown."""

from __future__ import annotations

from app.integration.jarvis_backend import BackendState, JarvisBackend
from app.integration.coordinator import AppCoordinator


class _WorkerThread:
    def __init__(self, *, exits_on_join: bool):
        self.alive = True
        self.exits_on_join = exits_on_join
        self.join_calls: list[float | None] = []

    def join(self, timeout=None):
        self.join_calls.append(timeout)
        if self.exits_on_join:
            self.alive = False

    def is_alive(self) -> bool:
        return self.alive


def test_backend_does_not_emit_shutdown_complete_when_worker_times_out():
    backend = JarvisBackend()
    worker = _WorkerThread(exits_on_join=False)
    backend._state = BackendState.READY
    backend._thread = worker
    emitted = []
    backend.shutdown_complete.connect(lambda: emitted.append(True))

    assert backend.stop(timeout=0.01) is False
    assert backend.state is BackendState.STOPPING
    assert worker.join_calls == [0.01]
    assert emitted == []


def test_backend_emits_shutdown_complete_only_after_worker_exits():
    backend = JarvisBackend()
    worker = _WorkerThread(exits_on_join=True)
    backend._state = BackendState.READY
    backend._thread = worker
    emitted = []
    backend.shutdown_complete.connect(lambda: emitted.append(True))

    assert backend.stop(timeout=0.01) is True
    assert backend.state is BackendState.STOPPED
    assert worker.join_calls == [0.01]
    assert emitted == [True]


def test_coordinator_releases_qt_workspace_on_calling_thread():
    coordinator = AppCoordinator(mode="test")
    called_on = []

    class Workspace:
        def shutdown(self):
            import threading
            called_on.append(threading.current_thread())

    workspace = Workspace()
    coordinator._workspace = workspace
    coordinator._workspace_visible = True

    coordinator.shutdown_ui_resources()

    import threading
    assert called_on == [threading.current_thread()]
    assert coordinator._workspace is None
    assert coordinator._workspace_visible is False



def test_workspace_shutdown_rejects_non_gui_thread():
    import threading

    coordinator = AppCoordinator(mode="test")
    shutdown_calls = []

    class Workspace:
        def shutdown(self):
            shutdown_calls.append(threading.current_thread())

    workspace = Workspace()
    coordinator._workspace = workspace
    errors = []

    def wrong_thread_call():
        try:
            coordinator.shutdown_ui_resources()
        except RuntimeError as exc:
            errors.append(str(exc))

    worker = threading.Thread(target=wrong_thread_call)
    worker.start()
    worker.join(timeout=1.0)

    assert not worker.is_alive()
    assert errors == ["Workspace widgets must be shut down on the GUI thread"]
    assert shutdown_calls == []
    assert coordinator._workspace is workspace
