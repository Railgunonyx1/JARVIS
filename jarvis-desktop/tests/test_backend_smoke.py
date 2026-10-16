"""Smoke test: backend constructs and starts without a browser."""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.integration.jarvis_backend import JarvisBackend, AgentResponse


def test_backend_starts():
    responses = []
    backend = JarvisBackend(
        mode="agent",
        on_response=responses.append,
    )
    backend.start()
    assert backend.is_running
    backend.stop()
    assert not backend.is_running


def test_backend_sends_message():
    """Send a trivial message; agent may fail (no API keys) but must not crash."""
    responses = []
    backend = JarvisBackend(
        mode="agent",
        on_response=responses.append,
    )
    backend.start()
    backend.send_message("Hello")
    # Wait up to 15s for a response (agent may error on missing keys)
    start = time.time()
    while not responses and time.time() - start < 15:
        time.sleep(0.1)
    backend.stop()
    # We don't assert success — just that the pipeline didn't crash
    assert True
