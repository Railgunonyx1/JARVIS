"""Coordinator tests — hermetic, no API needed."""

import os
import sys
import time

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.join(_REPO_ROOT, "jarvis-desktop")
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)

from app.integration.coordinator import AppCoordinator
from app.integration.jarvis_backend import JarvisBackend
from app.voice.voice_manager import VoiceState


class _DummyVoice:
    """Minimal voice stand-in for state-transition tests."""
    def __init__(self):
        self.state = VoiceState.IDLE
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)
        self.state = VoiceState.SPEAKING

    def _set_state(self, state):
        self.state = state


def test_coordinator_voice_thinking_to_speaking():
    """When voice is THINKING and backend responds, coordinator should
    transition voice to SPEAKING and speak the response."""
    coord = AppCoordinator(mode="agent")
    # Manually inject backend and voice without starting threads
    backend = JarvisBackend(mode="agent")
    coord._backend = backend
    coord._backend.start(wait=False, timeout=5.0)

    voice = _DummyVoice()
    coord._voice = voice
    coord._voice_turn_active = True

    # Simulate voice being in THINKING state (as set by _send_to_agent)
    voice.state = VoiceState.THINKING

    # Simulate backend response
    from app.integration.jarvis_backend import AgentResponse
    resp = AgentResponse(success=True, text="Hello back!", trace_id="t1")
    coord._on_backend_response(resp)

    time.sleep(0.3)
    assert voice.state == VoiceState.SPEAKING
    assert "Hello back!" in voice.spoken
    assert coord._voice_turn_active is False
    backend.stop(wait=True, timeout=5.0)


def test_typed_chat_does_not_trigger_tts():
    """Typed chat responses must not trigger TTS even when voice is IDLE."""
    coord = AppCoordinator(mode="agent")
    backend = JarvisBackend(mode="agent")
    coord._backend = backend
    coord._backend.start(wait=False, timeout=5.0)

    voice = _DummyVoice()
    coord._voice = voice
    coord._voice_turn_active = False
    voice.state = VoiceState.IDLE

    from app.integration.jarvis_backend import AgentResponse
    resp = AgentResponse(success=True, text="typed response", trace_id="t2")
    coord._on_backend_response(resp)

    assert voice.spoken == []
    assert coord._voice_turn_active is False
    backend.stop(wait=True, timeout=5.0)


def test_coordinator_voice_error_resets_turn_flag():
    """Failed voice request must clear _voice_turn_active."""
    coord = AppCoordinator(mode="agent")
    backend = JarvisBackend(mode="agent")
    coord._backend = backend
    coord._backend.start(wait=False, timeout=5.0)

    voice = _DummyVoice()
    coord._voice = voice
    coord._voice_turn_active = True
    voice.state = VoiceState.THINKING

    from app.integration.jarvis_backend import AgentResponse
    resp = AgentResponse(success=False, text="", error="API key missing")
    coord._on_backend_response(resp)

    assert coord._voice_turn_active is False
    assert voice.state == VoiceState.IDLE
    backend.stop(wait=True, timeout=5.0)


def test_set_voice_enabled():
    """set_voice_enabled(True) creates voice, False destroys it."""
    coord = AppCoordinator(mode="agent")
    backend = JarvisBackend(mode="agent")
    coord._backend = backend
    coord._backend.start(wait=False, timeout=5.0)

    coord.set_voice_enabled(True)
    assert coord._voice is not None

    coord.set_voice_enabled(False)
    assert coord._voice is None
    backend.stop(wait=True, timeout=5.0)


def test_set_model_applies_to_backend():
    """set_model propagates to the backend."""
    coord = AppCoordinator(mode="agent")
    backend = JarvisBackend(mode="agent")
    coord._backend = backend
    backend.start(wait=True, timeout=10.0)

    coord.set_model("test-model")
    assert backend._agent_loop is not None
    assert backend._agent_loop.router.preferred_model == "test-model"
    backend.stop(wait=True, timeout=5.0)
