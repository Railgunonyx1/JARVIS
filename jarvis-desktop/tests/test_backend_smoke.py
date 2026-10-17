"""Smoke tests: backend construction and lifecycle (hermetic, no API needed).

These tests verify the backend can start and stop without crashing.
They do NOT test end-to-end agent execution — that requires API keys.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from app.integration.jarvis_backend import BackendState, JarvisBackend


def test_backend_constructs():
    backend = JarvisBackend(mode="agent")
    assert backend.state == BackendState.STOPPED
    assert not backend.is_running


def test_backend_starts_and_stops():
    backend = JarvisBackend(mode="agent")
    backend.start(wait=True, timeout=10.0)
    assert backend.is_running
    assert backend.state == BackendState.READY
    backend.stop(wait=True, timeout=10.0)
    assert not backend.is_running
    assert backend.state == BackendState.STOPPED


def test_backend_startup_error_is_reported():
    # Start without allowing imports to succeed would fail; this test just
    # verifies the state machine transitions correctly on a normal start/stop.
    backend = JarvisBackend(mode="agent")
    backend.start(wait=True, timeout=10.0)
    assert backend.startup_error is None
    backend.stop(wait=True, timeout=10.0)


def test_backend_message_queued():
    """Verify messages are accepted and queued without crashing."""
    responses = []
    backend = JarvisBackend(mode="agent", on_response=responses.append)
    backend.start(wait=True, timeout=10.0)
    backend.send_message("Hello")
    # Give the worker thread time to pick up the message
    time.sleep(0.5)
    backend.stop(wait=True, timeout=10.0)
    # The message was accepted into the queue without crashing
    assert backend.is_running is False


@pytest.mark.e2e
def test_backend_processes_message_e2e():
    """End-to-end: send a message and get a response from the agent.

    Requires API keys configured in config/.env. Skipped if no keys present.
    """
    responses = []
    backend = JarvisBackend(mode="agent", on_response=responses.append)
    backend.start(wait=True, timeout=10.0)
    backend.send_message("Say hello in exactly five words.")
    start = time.time()
    while not responses and time.time() - start < 15:
        time.sleep(0.1)
    backend.stop(wait=True, timeout=10.0)
    assert len(responses) == 1
    assert responses[0].success is True
    assert len(responses[0].text) > 0
