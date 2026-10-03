"""Tests for the cloud TTS/STT engine registry and dispatch.

Covers the pieces a real request exercises but a unit test would miss:
engine inventory shape, availability reasons, STT fallback selection, and
the failure messages that tell a user which env var to set.

No engine ever reaches the network here -- every path under test is either
a missing-key branch or a locally injected stub, which is exactly what
runs on a fresh install.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BRIDGE = Path(__file__).resolve().parent.parent / "jbrowser-bridge"
if str(_BRIDGE) not in sys.path:
    sys.path.insert(0, str(_BRIDGE))

import voice  # noqa: E402
import voice_engines as ve  # noqa: E402


# ── Inventory ───────────────────────────────────────────────────────────

def test_tts_inventory_covers_every_named_engine():
    ids = [e.id for e in ve.tts_engines()]
    for expected in ("elevenlabs", "azure", "polly", "google", "edge", "kokoro", "sapi"):
        assert expected in ids, f"{expected} missing from the TTS inventory: {ids}"


def test_stt_inventory_covers_every_named_engine():
    ids = [e.id for e in ve.stt_engines()]
    for expected in ("elevenlabs", "groq", "deepgram"):
        assert expected in ids, f"{expected} missing from the STT inventory: {ids}"


def test_every_engine_reports_a_reason_when_unavailable():
    """A greyed-out row with no tooltip is worse than no row at all."""
    for info in ve.tts_engines() + ve.stt_engines():
        if not info.available:
            assert info.reason, f"{info.id} is unavailable but gives no reason"


def test_engine_dict_is_json_serialisable():
    info = ve.tts_engines()[0]
    payload = info.to_dict()
    assert set(payload) >= {
        "id", "label", "kind", "available", "reason", "key_env", "note", "needs_key"
    }
    assert payload["kind"] in ("tts", "stt")
    assert isinstance(payload["voices"], list)


def test_free_tier_notes_exist_for_every_engine():
    for info in ve.tts_engines() + ve.stt_engines():
        assert info.id in ve.FREE_TIER_NOTES, f"no free-tier note for {info.id}"
        assert ve.FREE_TIER_NOTES[info.id].strip()


def test_keyless_engines_never_ask_for_a_key(monkeypatch):
    for var in ("ELEVENLABS_API_KEY", "GROQ_API_KEY", "DEEPGRAM_API_KEY",
                "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION", "GOOGLE_API_KEY",
                "GOOGLE_TTS_API_KEY", "GEMINI_API_KEY", "AWS_ACCESS_KEY_ID",
                "AWS_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    for info in ve.tts_engines() + ve.stt_engines():
        if info.id in ("edge", "kokoro", "sapi"):
            assert info.needs_key is False, f"{info.id} must not need a key"


# ── Availability reacts to configuration ───────────────────────────────

def test_edge_is_available_without_any_key(monkeypatch):
    for var in ("ELEVENLABS_API_KEY", "GROQ_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    by_id = {e.id: e for e in ve.tts_engines()}
    assert by_id["edge"].available, "Edge TTS needs no key and must be available"


def test_groq_stt_turns_on_with_a_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    by_id = {e.id: e for e in ve.stt_engines()}
    assert by_id["groq"].available
    assert by_id["groq"].needs_key
    assert by_id["elevenlabs"].available is False, "must not leak between engines"


def test_azure_needs_both_key_and_region(monkeypatch):
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    monkeypatch.setenv("AZURE_SPEECH_KEY", "k")
    by_id = {e.id: e for e in ve.tts_engines()}
    assert by_id["azure"].available is False
    assert "REGION" in by_id["azure"].reason.upper()

    monkeypatch.setenv("AZURE_SPEECH_REGION", "eastus")
    assert {e.id: e for e in ve.tts_engines()}["azure"].available


def test_first_available_stt_prefers_a_configured_engine(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    chosen = ve.first_available_stt()
    assert chosen is not None and chosen.id == "groq"

    monkeypatch.delenv("GROQ_API_KEY")
    assert ve.first_available_stt() is None, "no keys must mean no STT engine"


# ── Dispatch ────────────────────────────────────────────────────────────

def test_stt_auto_selects_the_configured_engine(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    chosen, fn = voice._select_stt_engine(None)
    assert chosen == "groq"
    assert fn is ve.stt_groq


def test_stt_explicit_pin_wins_even_when_unconfigured(monkeypatch):
    """An explicit pick must surface ITS error, not another provider's."""
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    chosen, fn = voice._select_stt_engine("deepgram")
    assert chosen == "deepgram"
    with pytest.raises(RuntimeError, match="DEEPGRAM_API_KEY"):
        fn(b"\x00" * 200, filename="a.webm")


def test_stt_unknown_name_falls_back_instead_of_raising(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    chosen, fn = voice._select_stt_engine("not-a-real-engine")
    assert chosen in ("elevenlabs", "groq", "deepgram")
    assert callable(fn)


def test_stt_auto_without_keys_names_the_env_vars(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as excinfo:
        voice.stt_bytes(b"\x00" * 200, filename="a.webm")
    message = str(excinfo.value)
    assert "GROQ_API_KEY" in message and "DEEPGRAM_API_KEY" in message


def test_stt_dispatches_to_the_pinned_engine(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    seen = {}

    def _fake(data, filename="audio.webm"):
        seen["data"] = data
        seen["filename"] = filename
        return "  hello from groq  "

    monkeypatch.setitem(ve.STT_FUNCTIONS, "groq", _fake)
    out = voice.stt_bytes(b"\x01" * 300, filename="clip.webm", engine_name="groq")
    assert out == "hello from groq", "result must be stripped"
    assert seen["filename"] == "clip.webm"


# ── TTS chain ───────────────────────────────────────────────────────────

def test_tts_chain_ends_with_a_guaranteed_engine(monkeypatch):
    """Whatever else is configured, the chain must always have a last resort."""
    for var in ("ELEVENLABS_API_KEY", "AZURE_SPEECH_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    chain = [name for name, _ in voice._tts_chain()]
    assert chain, "chain must never be empty"
    assert chain[-1] in ("sapi", "kokoro"), f"unsafe tail: {chain}"


def test_tts_chain_prefers_a_keyed_cloud_voice(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el_test")
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    chain = [name for name, _ in voice._tts_chain()]
    assert chain[0] == "elevenlabs", chain


def test_tts_chain_skips_unconfigured_cloud_engines(monkeypatch):
    for var in ("ELEVENLABS_API_KEY", "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION",
                "GOOGLE_API_KEY", "GOOGLE_TTS_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    chain = [name for name, _ in voice._tts_chain()]
    for unkeyed in ("elevenlabs", "azure", "google", "polly"):
        assert unkeyed not in chain, f"{unkeyed} is unconfigured but in chain {chain}"


def test_auto_tts_falls_back_when_the_first_engine_fails(monkeypatch):
    """The regression that motivated the chain: one flaky engine used to mean
    no audio at all, because auto resolved to a single registered callable."""
    monkeypatch.setattr(voice, "_tts_chain", lambda: [
        ("edge", _boom), ("sapi", _good),
    ])
    data, mime, used = voice._tts_one("hello", engine_name="auto")
    assert used == "sapi", "must report the engine that ACTUALLY ran"
    assert data == b"RIFF"


def test_auto_tts_raises_only_when_every_engine_fails(monkeypatch):
    monkeypatch.setattr(voice, "_tts_chain", lambda: [("edge", _boom), ("sapi", _boom)])
    with pytest.raises(RuntimeError, match="every TTS engine failed"):
        voice._tts_one("hello", engine_name="auto")


def test_pinned_tts_engine_does_not_silently_use_another(monkeypatch):
    """Pinning must surface the real failure, not answer from a fallback."""
    monkeypatch.setattr(voice, "_tts_chain", lambda: [("sapi", _good)])
    monkeypatch.setitem(voice._tts_engines, "edge", _boom)
    with pytest.raises(RuntimeError):
        voice._tts_one("hello", engine_name="edge")


def _boom(text, speed=1.0, voice=""):
    raise RuntimeError("engine offline")


def _good(text, speed=1.0, voice=""):
    return b"RIFF", "audio/wav"


# ── Status payload ──────────────────────────────────────────────────────

def test_voice_status_exposes_the_inventory():
    status = voice.voice_status()
    assert status["ok"] is True
    assert len(status["tts_engines"]) >= 7
    assert len(status["stt_engines"]) >= 3
    assert status["stt"] is None or status["stt"] in {
        e["id"] for e in status["stt_engines"]
    }


def test_voice_status_reports_the_configured_stt_engine(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert voice.voice_status()["stt"] == "groq"


# ── Wire format helpers ─────────────────────────────────────────────────

def test_multipart_body_carries_the_blob_and_fields():
    body, content_type = ve._multipart(
        {"model": "whisper-large-v3-turbo"}, "clip.webm", b"\x01\x02\x03", "audio/webm",
    )
    assert content_type.startswith("multipart/form-data; boundary=")
    assert b'name="model"' in body
    assert b"whisper-large-v3-turbo" in body
    assert b'filename="clip.webm"' in body
    assert b"\x01\x02\x03" in body
    assert body.rstrip().endswith(b"--")


def test_mime_guessing_covers_the_browser_recorders():
    assert ve._guess_mime("a.webm") == "audio/webm"
    assert ve._guess_mime("a.OGG") == "audio/ogg"
    assert ve._guess_mime("a.wav") == "audio/wav"
    assert ve._guess_mime("a.bin") == "application/octet-stream"


def test_missing_keys_raise_actionable_errors(monkeypatch):
    for var in ("GROQ_API_KEY", "DEEPGRAM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        ve.stt_groq(b"\x00" * 200)
    with pytest.raises(RuntimeError, match="DEEPGRAM_API_KEY"):
        ve.stt_deepgram(b"\x00" * 200)


def test_google_requires_a_key(monkeypatch):
    for var in ("GOOGLE_TTS_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        ve.tts_google("hello")


def test_azure_requires_both_variables(monkeypatch):
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    with pytest.raises(RuntimeError, match="AZURE_SPEECH_KEY"):
        ve.tts_azure("hello")


def test_polly_requires_boto3(monkeypatch):
    monkeypatch.setattr(ve, "_has_module", lambda name: False)
    with pytest.raises(RuntimeError, match="boto3"):
        ve.tts_polly("hello")


def test_empty_text_is_rejected_before_any_network_call():
    for fn in (ve.tts_google, ve.tts_azure, ve.tts_polly):
        with pytest.raises(ValueError, match="empty text"):
            fn("   ")


def test_speech_normalisation_is_applied_to_cloud_engines(monkeypatch):
    """Emoji/control characters would otherwise reach the vendor verbatim."""
    seen = {}

    def _capture(url, payload, headers, timeout=None):
        seen["input"] = payload["input"]["text"]
        return {"audioContent": "AA=="}

    monkeypatch.setattr(ve, "_post_json", _capture)
    monkeypatch.setenv("GOOGLE_API_KEY", "g_test")
    ve.tts_google("hello \U0001f600 \x07world")
    assert "\x07" not in seen["input"]