"""Phase 3 — voice system tests (hermetic, no audio hardware)."""

import sys
import os
import time
import threading

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)


def test_tts_engine_constructs():
    from app.voice.tts import TTSEngine
    tts = TTSEngine(voice="af_sarah", speed=1.0)
    assert tts.engine_name == "none"  # not warmed up yet


def test_tts_engine_fallback():
    """TTS should return empty bytes when no engine available (no crash)."""
    from app.voice.tts import TTSEngine
    tts = TTSEngine(use_kokoro=False)
    # speak() should not raise even if all engines fail
    result = tts.speak("Hello")
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_stt_manager_constructs():
    from app.voice.stt import STTManager
    mgr = STTManager(prefer_local=False)
    assert mgr.active_engine == "none"


def test_stt_result_bool():
    from app.voice.stt import STTResult
    assert STTResult("hello")
    assert not STTResult("")
    assert not STTResult("   ")


def test_voice_manager_constructs():
    from app.voice.voice_manager import VoiceManager, VoiceState
    vm = VoiceManager(prefer_local_stt=False, use_kokoro_tts=False)
    assert vm.state == VoiceState.IDLE
    assert not vm.is_listening
    assert not vm.is_speaking


def test_voice_manager_state_transitions():
    from app.voice.voice_manager import VoiceManager, VoiceState
    states = []
    vm = VoiceManager(
        prefer_local_stt=False,
        use_kokoro_tts=False,
        on_state_change=lambda s: states.append(s),
    )
    vm._set_state(VoiceState.LISTENING)
    assert vm.state == VoiceState.LISTENING
    assert vm.is_listening
    vm._set_state(VoiceState.IDLE)
    assert vm.state == VoiceState.IDLE
    assert VoiceState.LISTENING in states


def test_voice_manager_toggle():
    from app.voice.voice_manager import VoiceManager, VoiceState
    vm = VoiceManager(prefer_local_stt=False, use_kokoro_tts=False)
    # toggle from idle starts listening (in a thread)
    vm.toggle_listening()
    # state should be listening (thread may have finished quickly)
    assert vm.state in (VoiceState.LISTENING, VoiceState.TRANSCRIBING, VoiceState.IDLE)


def test_voice_manager_stop_speaking():
    from app.voice.voice_manager import VoiceManager, VoiceState
    vm = VoiceManager(prefer_local_stt=False, use_kokoro_tts=False)
    vm._set_state(VoiceState.SPEAKING)
    assert vm.is_speaking
    vm.stop_speaking()
    assert vm.state == VoiceState.IDLE
    assert not vm.is_speaking


def test_voice_manager_status():
    from app.voice.voice_manager import VoiceManager
    vm = VoiceManager(prefer_local_stt=False, use_kokoro_tts=False)
    status = vm.get_status()
    assert "state" in status
    assert "stt_engine" in status
    assert "tts_engine" in status
    assert status["state"] == "idle"


def test_voice_manager_with_mock_backend():
    """Voice manager should send transcribed text to backend."""
    from app.voice.voice_manager import VoiceManager, VoiceState

    sent = []
    class MockBackend:
        def send_message(self, text):
            sent.append(text)

    vm = VoiceManager(
        agent_backend=MockBackend(),
        prefer_local_stt=False,
        use_kokoro_tts=False,
    )
    vm._send_to_agent("Hello JARVIS")
    time.sleep(0.5)
    assert "Hello JARVIS" in sent
