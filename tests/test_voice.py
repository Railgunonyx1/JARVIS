"""Hermetic tests for the JARVIS voice module and bridge endpoints.

No network, no ElevenLabs key, no model downloads: Kokoro/SAPI are monkey-
patched at the voice module boundary, so only the dispatch chain, text
normalization, ack rules, and HTTP contracts are exercised.
"""

from __future__ import annotations

import base64
import json
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

BRIDGE_DIR = Path(__file__).resolve().parent.parent / "jbrowser-bridge"
sys.path.insert(0, str(BRIDGE_DIR))

import voice as voice_mod  # noqa: E402
from server import serve  # noqa: E402


@pytest.fixture()
def bridge():
    httpd = serve(host="127.0.0.1", port=0, backend_kind="echo")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        yield base
    finally:
        httpd.shutdown()
        httpd.server_close()


def _post(base, path, payload):
    """POST JSON; returns (status, parsed body) including 4xx/5xx responses."""
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:  # error responses still carry JSON
        return e.code, json.loads(e.read())


# ── speakable-text normalization ─────────────────────────────────────────


def test_strip_markdown_code_blocks():
    out = voice_mod._strip_markdown("Run `pip install x` then:\n```py\nprint(1)\n```")
    assert "print(1)" not in out
    assert "code block omitted" in out
    assert "pip install x" in out  # inline code is spoken


def test_strip_markdown_links_headings_bullets():
    out = voice_mod._strip_markdown("## Heading\n- item one\n[link](https://x.com) **bold**")
    assert "#" not in out
    assert "item one" in out
    assert "https://x.com" not in out
    assert "bold" in out


def test_strip_markdown_emoji_and_tables():
    out = voice_mod._strip_markdown("Done ✅ | col1 | col2 |")
    assert "✅" not in out
    assert "|" not in out


# ── TTS dispatch chain ───────────────────────────────────────────────────


def test_tts_chain_empty_text_raises():
    with pytest.raises(ValueError):
        voice_mod.tts("   ")


def test_tts_prefers_elevenlabs_when_keyed(monkeypatch):
    monkeypatch.setattr(voice_mod, "_api_key", lambda: "k-test")
    monkeypatch.setattr(voice_mod, "tts_elevenlabs", lambda t, voice_id="", speed=1.0: (b"el", "audio/mpeg"))
    data, mime, engine = voice_mod.tts("hello")
    assert engine == "elevenlabs" and mime == "audio/mpeg"


def test_tts_falls_to_kokoro_when_elevenlabs_fails(monkeypatch):
    monkeypatch.setattr(voice_mod, "_api_key", lambda: "k-test")

    def _boom(_):
        raise RuntimeError("api down")

    monkeypatch.setattr(voice_mod, "tts_elevenlabs", _boom)
    monkeypatch.setattr(voice_mod, "_kokoro_instance", lambda: object())
    monkeypatch.setattr(voice_mod, "tts_kokoro", lambda t, voice="", speed=1.0: (b"kk", "audio/wav"))
    data, mime, engine = voice_mod.tts("hello")
    assert engine == "kokoro"


def test_tts_falls_to_kokoro_without_key(monkeypatch):
    monkeypatch.setattr(voice_mod, "_api_key", lambda: "")
    monkeypatch.setattr(voice_mod, "_kokoro_instance", lambda: object())
    monkeypatch.setattr(voice_mod, "tts_kokoro", lambda t, voice="", speed=1.0: (b"kk", "audio/wav"))
    _, _, engine = voice_mod.tts("hello")
    assert engine == "kokoro"


def test_tts_sapi_last_resort(monkeypatch):
    monkeypatch.setattr(voice_mod, "_api_key", lambda: "")
    monkeypatch.setattr(voice_mod, "_kokoro_instance", lambda: None)
    monkeypatch.setattr(voice_mod, "tts_sapi", lambda t, speed=1.0: (b"sp", "audio/wav"))
    _, _, engine = voice_mod.tts("hello")
    assert engine == "sapi"


def test_tts_kokoro_writes_wav_header(monkeypatch):
    """kokoro engine produces a parseable 24kHz mono 16-bit WAV."""
    import io
    import struct
    import wave

    class FakeKokoro:
        def create(self, text, voice="af_sarah", speed=1.0, lang="en-us", **kw):
            return [0.0, 0.5, -0.5, 0.25], 24000

    monkeypatch.setattr(voice_mod, "_kokoro_instance", lambda: FakeKokoro())
    voice_mod._AUDIO_CACHE.clear()
    data, mime = voice_mod.tts_kokoro("hello world")
    assert mime == "audio/wav"
    with wave.open(io.BytesIO(data), "rb") as w:
        assert w.getframerate() == 24000
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        frames = w.getnframes()
    assert frames == 4
    sample = struct.unpack("<h", data[-2:])[0]
    assert sample == int(0.25 * 32767)


def test_pcm_wav_numpy_conversion():
    """_pcm_wav converts float samples to little-endian int16 via numpy."""
    import io
    import struct
    import wave

    data = voice_mod._pcm_wav([0.5, -0.5, 1.5, -1.5], 24000)  # clip at ±1.0
    with wave.open(io.BytesIO(data), "rb") as w:
        assert w.getframerate() == 24000
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        raw = w.readframes(4)
    vals = struct.unpack("<4h", raw)
    assert vals == (int(0.5 * 32767), int(-0.5 * 32767), 32767, -32767)


def test_kokoro_audio_cache_hit_skips_synthesis(monkeypatch):
    """Second identical request returns from LRU without calling create()."""
    calls = {"n": 0}

    class Counting:
        def create(self, text, **kw):
            calls["n"] += 1
            return [0.0, 0.1], 24000

    monkeypatch.setattr(voice_mod, "_kokoro_instance", lambda: Counting())
    voice_mod._AUDIO_CACHE.clear()
    voice_mod.tts_kokoro("cache me")
    voice_mod.tts_kokoro("cache me")
    assert calls["n"] == 1


def test_tts_threads_env_override(monkeypatch):
    monkeypatch.setenv("JARVIS_TTS_THREADS", "3")
    import importlib
    importlib.reload(voice_mod)
    assert voice_mod._TTS_THREADS == 3
    monkeypatch.delenv("JARVIS_TTS_THREADS")
    importlib.reload(voice_mod)


# ── Instant acknowledgment (Mark-LIV) ────────────────────────────────────


def test_ack_for_task_like_request():
    assert voice_mod.ack_for("search for quantum computing news") == "Searching now."
    assert voice_mod.ack_for("open github.com") == "Opening it."


def test_ack_skips_questions_and_short_text():
    assert voice_mod.ack_for("what is my name?") == ""
    assert voice_mod.ack_for("hi") == ""


# ── STT key gate ─────────────────────────────────────────────────────────


def test_stt_requires_key(monkeypatch):
    monkeypatch.setattr(voice_mod, "_api_key", lambda: "")
    with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
        voice_mod.stt_bytes(b"x" * 1024)


def test_voice_status_shape(monkeypatch):
    monkeypatch.setattr(voice_mod, "_api_key", lambda: "")
    voice_mod._kokoro_cache["inst"] = None  # ensure kokoro not loaded in tests
    s = voice_mod.voice_status()
    assert s["ok"] is True
    assert s["stt"] is None
    assert "sapi" in s["tts_chain"]


# ── HTTP contracts ───────────────────────────────────────────────────────


class _SapiFake:
    __name__ = "sapi"

    def __call__(self, text, speed=1.0):
        return b"fake-wav-bytes", "audio/wav"


_tts_sapi_fake = _SapiFake()


def test_http_tts_ok(bridge, monkeypatch):
    monkeypatch.setattr(voice_mod, "_api_key", lambda: "")
    monkeypatch.setattr(voice_mod, "_kokoro_instance", lambda: None)
    monkeypatch.setattr(voice_mod, "_tts_engine", _tts_sapi_fake)
    status, d = _post(bridge, "/v1/tts", {"text": "hello"})
    assert status == 200 and d["ok"] is True
    assert d["engine"] == "sapi"
    assert base64.b64decode(d["audio_b64"]) == b"fake-wav-bytes"


def test_http_tts_empty_text_400(bridge):
    status, d = _post(bridge, "/v1/tts", {"text": "  "})
    assert status == 400 and "text is required" in d["error"]


def test_http_tts_engine_failure_500(bridge, monkeypatch):
    class _Boom:
        __name__ = "sapi"

        def __call__(self, text):
            raise RuntimeError("no engine could render this")


    _boom = _Boom()

    monkeypatch.setattr(voice_mod, "_api_key", lambda: "")
    monkeypatch.setattr(voice_mod, "_kokoro_instance", lambda: None)
    monkeypatch.setattr(voice_mod, "_tts_engine", _boom)
    status, d = _post(bridge, "/v1/tts", {"text": "hello"})
    assert status == 500 and "tts failed" in d["error"]


def test_http_stt_too_short_400(bridge):
    status, d = _post(bridge, "/v1/stt", {"audio_b64": base64.b64encode(b"\x00" * 10).decode()})
    assert status == 400 and "too short" in d["error"]


def test_http_stt_no_key_503(bridge, monkeypatch):
    monkeypatch.setattr(voice_mod, "_api_key", lambda: "")
    def _no_key(data, filename="audio.webm"):
        raise RuntimeError("ELEVENLABS_API_KEY not configured")

    monkeypatch.setattr(voice_mod, "stt_bytes", _no_key)
    status, d = _post(bridge, "/v1/stt", {"audio_b64": base64.b64encode(b"\x00" * 4096).decode()})
    assert status == 503 and "ELEVENLABS_API_KEY" in d["error"]


def test_http_voice_status(bridge, monkeypatch):
    monkeypatch.setattr(voice_mod, "_api_key", lambda: "")
    status, d = _post(bridge, "/v1/voice/status", {})
    assert status == 200 and d["ok"] is True
    assert d["tts"] in ("elevenlabs", "kokoro", "sapi")


class _SapiRaw:
    __name__ = "sapi"

    def __call__(self, text, speed=1.0):
        return b"RAW-WAV-DATA", "audio/wav"


_tts_sapi_raw = _SapiRaw()


def test_http_tts_raw_binary_format(bridge, monkeypatch):
    """format=raw streams raw audio bytes with the engine header (no b64)."""
    monkeypatch.setattr(voice_mod, "_api_key", lambda: "")
    monkeypatch.setattr(voice_mod, "_kokoro_instance", lambda: None)
    monkeypatch.setattr(voice_mod, "_tts_engine", _tts_sapi_raw)
    req = urllib.request.Request(
        bridge + "/v1/tts",
        data=json.dumps({"text": "hello", "format": "raw"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.status == 200
        assert r.headers["Content-Type"] == "audio/wav"
        assert r.headers["X-Voice-Engine"] == "sapi"
        assert r.read() == b"RAW-WAV-DATA"
