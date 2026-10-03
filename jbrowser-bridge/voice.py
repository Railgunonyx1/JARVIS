"""JARVIS voice — TTS + STT for the chat pipeline.

Design (per the text-to-speech / speech-to-text skills):

* **TTS chain** — ``POST /v1/tts {text}`` → audio bytes (wav or mp3).
  1. ElevenLabs (``eleven_flash_v2_5`` ~75ms) when ``ELEVENLABS_API_KEY`` is
     set — neural quality, key never leaves the server.
  2. **Kokoro-82M** local ONNX (Apache-2.0; model from
     thewh1teagle/kokoro-onnx releases) — frontier quality for an 82M-
     parameter model, faster than real-time on CPU, zero key, zero network.
     Auto-downloads the ~330MB fp32 model (or set ``JARVIS_KOKORO_PRECISION
     =fp16|int8`` for 164/114MB) plus the 28MB voice bank to
     ``%LOCALAPPDATA%/JARVIS/kokoro`` on first use.
  3. Windows SAPI narration — robotic last resort, always available.

* **STT** — ``POST /v1/stt`` (``{audio_b64, mime}``) → ``{"text": ...}``.
  ElevenLabs Scribe v2. Key-gated: without a key the endpoint returns 503
  with a setup pointer.

* **Security posture (speech-engine skill)** — transcript text is untrusted
  input. This module only passes it through as ordinary chat text; it never
  grants tools or privileged actions. Auth rides the bridge's existing bearer
  token on every route.

* **Instant acknowledgment (Mark-LIV feature)** — ``ack_for(text)`` returns a
  short natural acknowledgment line when a task-like request starts so voice
  replies never begin with silence.
"""

from __future__ import annotations

import io
import inspect
import logging
import os
import re
import tempfile
import time

logger = logging.getLogger("jarvis.voice")

# ElevenLabs defaults — overridable via env.
EL_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")  # Sarah
EL_TTS_MODEL = os.getenv("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5")
EL_STT_MODEL = os.getenv("ELEVENLABS_STT_MODEL", "scribe_v2")

# Kokoro (local neural TTS) — thewh1teagle/kokoro-onnx v1.1 release assets.
KOKORO_PRECISION = os.getenv("JARVIS_KOKORO_PRECISION", "fp32")  # fp32|fp16|int8
KOKORO_LANG = os.getenv("JARVIS_KOKORO_LANG", "en-us")
KOKORO_VOICE = os.getenv("JARVIS_KOKORO_VOICE", "af_sarah")

# Curated Kokoro v1.0 voice list (the voices.bin bank ships 54; these are the
# stable names). available_voices() prefers live keys from the loaded bank.
KOKORO_VOICES_KNOWN = [
    # American female
    "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore", "af_nicole",
    "af_nova", "af_river", "af_sarah", "af_sky",
    # American male
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
    "am_onyx", "am_puck", "am_santa",
    # British female
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    # British male
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
]

# Speed limits shared by the engines (Kokoro native range, sane elsewhere).
SPEED_MIN, SPEED_MAX = 0.5, 2.0

_VOICE_HDR_RE = re.compile(r"[\r\n\x00-]")


def _header_safe(value: str) -> str:
    """Make a derived string safe to emit as an HTTP header value."""
    return _VOICE_HDR_RE.sub("", str(value))[:80]


def _clamp_speed(raw) -> float:
    try:
        s = float(raw)
    except (TypeError, ValueError):
        return 1.0
    return max(SPEED_MIN, min(SPEED_MAX, s))
_KOKORO_RELEASE = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/"
    "download/model-files-v1.1"
)
_KOKORO_FILES = {
    "fp32": "kokoro-v1.0.onnx",
    "fp16": "kokoro-v1.0.fp16.onnx",
    "int8": "kokoro-v1.0.int8.onnx",
}
_KOKORO_VOICES = "voices-v1.0.bin"

_KOKORO_MODEL_DESC = "model ({})"  # fmt: skip

_client_cache: dict = {}
_client_cache_at: float = 0.0
_CLIENT_TTL = 300.0  # re-resolve the key periodically (env can change)

def _api_key() -> str:
    return (os.getenv("ELEVENLABS_API_KEY") or "").strip()

def _el_client():
    """Lazily import and cache the ElevenLabs client (None when no key/SDK)."""
    global _client_cache_at
    now = time.monotonic()
    if _client_cache and now - _client_cache_at < _CLIENT_TTL:
        return _client_cache.get("client")
    _client_cache_at = now
    key = _api_key()
    if not key:
        _client_cache.clear()
        _client_cache["client"] = None
        return None
    try:
        from elevenlabs import ElevenLabs

        _client_cache["client"] = ElevenLabs(api_key=key)
        logger.info("ElevenLabs voice enabled (model=%s voice=%s)", EL_TTS_MODEL, EL_VOICE_ID)
    except Exception as e:  # SDK missing → SAPI fallback stays primary
        logger.warning("ElevenLabs SDK unavailable (%s); falling back to SAPI", e)
        _client_cache.clear()
        _client_cache["client"] = None
    return _client_cache.get("client")

# ── TTS ───────────────────────────────────────────────────────────────────

_MAX_TTS_CHARS = 2500  # ElevenLabs per-request cap headroom

# Abbreviations TTS engines read badly. Applied after markdown stripping;
# conservative — only unambiguous, punctuation-anchored forms.
_ABBREV_RE: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\be\.g\.(?=\s)", re.I), "for example"),
    (re.compile(r"\bi\.e\.(?=\s)", re.I), "that is"),
    (re.compile(r"\betc\.(?=\s|$)", re.I), "etcetera"),
    (re.compile(r"\bw\/(?!\d)(?=\s\S)", re.I), "with"),
    (re.compile(r"\bapprox\.(?=\s)", re.I), "approximately"),
    (re.compile(r"\bvs\.(?=\s)", re.I), "versus"),
    (re.compile(r"\bDr\.(?=\s)", re.I), "Doctor"),
    (re.compile(r"\bMr\.(?=\s)", re.I), "Mister"),
    (re.compile(r"\bMrs\.(?=\s)", re.I), "Missus"),
    (re.compile(r"\bSt\.(?=\s)", re.I), "Saint"),
    # URLs read terribly; say that a link is present instead.
    (re.compile(r"https?://\S+", re.I), "a link"),
]

def _normalize_speech(text: str) -> str:
    """Markdown strip + abbreviation/URL normalization for all engines."""
    t = _strip_markdown(text)
    for rx, spoken in _ABBREV_RE:
        t = rx.sub(spoken, t)
    return t.strip()

def _strip_markdown(text: str) -> str:
    """Speakable-text normalization: markdown/emoji/punctuation noise out."""
    t = text or ""
    t = re.sub(r"```.*?```", " code block omitted. ", t, flags=re.S)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\!?\[([^\]]*)\]\([^)]*\)", r"\1", t)  # links → label
    t = re.sub(r"^\s{0,3}#{1,6}\s+", "", t, flags=re.M)  # headings
    t = re.sub(r"(\*\*|__|\*|~~)", "", t)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*>\s?", "", t, flags=re.M)
    t = re.sub(r"\|", " ", t)
    t = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]", "", t)  # emoji
    t = re.sub(r"\n{2,}", ". ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()

# Engine injection point (server.py test seam). Defaults reproduce the
# current production chain (SAPI last resort), so nothing changes for
# callers that never touch these attributes. A callable assigned to
# ``_tts_engine`` is used directly; a dict of named engines is resolved to
# the first value (insertion order) when present.
_tts_engine: object | None = None
_tts_engines: dict[str, object] = {}


def _resolve_tts_engine() -> object:
    """Return the engine factory actually used for the SAPI chain.

    ``_tts_engine`` may be EITHER a single callable (the original test seam)
    or a name->callable dict. When it is a dict the default is its first
    value, so the returned object is always callable.
    """
    if isinstance(_tts_engine, dict):
        if _tts_engine:
            return next(iter(_tts_engine.values()))
        return next(iter(_tts_engines.values())) if _tts_engines else tts_sapi
    if _tts_engine is not None:
        return _tts_engine
    if _tts_engines:
        return next(iter(_tts_engines.values()))
    return tts_sapi


def register_tts_engine(name: str, engine: object) -> None:
    """Register a named TTS engine factory; ``_resolve_tts_engine()`` prefers it."""
    if _tts_engine is not None:
        _tts_engine[name] = engine
    else:
        _tts_engines[name] = engine


def _select_tts_engine(name: str | None) -> object:
    """Return a named engine when one is registered, else the default.

    ``None``/``"auto"`` keeps the production chain exactly as before. An
    unknown or unregistered name FALLS BACK to the default rather than
    raising, so a stale UI preference can never break synthesis.
    """
    if not name or name == "auto":
        return _resolve_tts_engine()
    fn = _tts_engines.get(name)
    if fn is not None:
        return fn
    if isinstance(_tts_engine, dict):
        fn = _tts_engine.get(name)
        if fn is not None:
            return fn
    logger.debug("voice: unknown tts engine %r; using default chain", name)
    return _resolve_tts_engine()


def _call_engine(engine_fn: object, text: str, speed: float, voice: str) -> tuple[bytes, str]:
    """Invoke an engine, forwarding ``voice`` only when it accepts one.

    Engines disagree on the voice kwarg (``tts_kokoro`` takes ``voice``,
    ``tts_elevenlabs`` takes ``voice_id``, ``tts_sapi`` takes neither), so the
    keyword is passed only when the callable actually declares it. Probing
    the signature avoids swallowing a genuine TypeError raised *inside* the
    engine, which a try/except around the call would do.
    """
    kwargs: dict[str, object] = {"speed": speed}
    if voice:
        try:
            params = inspect.signature(engine_fn).parameters
        except (TypeError, ValueError):
            params = {}  # builtins / C callables: probe blindly
        if "voice" in params:
            kwargs["voice"] = voice
        elif "voice_id" in params:
            kwargs["voice_id"] = voice
    return engine_fn(text, **kwargs)  # type: ignore[operator, no-any-return]


def _tts_one(text: str, speed: float = 1.0, engine_name: str | None = None,
             voice: str = "") -> tuple[bytes, str, str]:
    """Render text with the configured engine.

    Returns (bytes, mime, engine_used). The default production behavior is
    unchanged for every tester that never assigns _tts_engine/_tts_engines.
    ``voice`` selects a Kokoro voice id; engines without a voice parameter
    ignore it.
    """
    engine_fn = _select_tts_engine(engine_name)
    # Report the engine that ACTUALLY ran, not the one that was requested:
    # an unknown pin falls back to the default chain and must say so.
    key = getattr(engine_fn, "__name__", repr(engine_fn))
    data, mime = _call_engine(engine_fn, text, speed, voice)
    return data, mime, key

def tts_sapi(text: str, speed: float = 1.0) -> tuple[bytes, str]:
    """Windows SAPI narration (keyless path). Returns (bytes, mime)."""
    import win32com.client  # pywin32 — present on Windows targets

    text = _normalize_speech(text)[: _MAX_TTS_CHARS]
    if not text:
        raise ValueError("empty text")
    com = None
    stream = None
    try:
        com = win32com.client.Dispatch("SAPI.SpVoice")
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        # 22.05kHz 16-bit mono — universally decodable, small.
        fmt = win32com.client.Dispatch("SAPI.SpAudioFormat")
        fmt.Type = 22  # SAFT22kHz16BitMono
        stream.Format = fmt
        fd, path = tempfile.mkstemp(suffix=".wav", prefix="jarvis-tts-")
        os.close(fd)
        stream.Open(path, 3)  # SSFMCreateForWrite
        old = com.AudioOutputStream
        com.AudioOutputStream = stream
        try:
            com.Rate = max(-10, min(10, int(round((speed - 1.0) * 8))))  # SAPI rate -10..10
        except Exception:
            pass
        com.Speak(text)
        com.AudioOutputStream = old
        stream.Close()
        with open(path, "rb") as fh:
            data = fh.read()
        return data, "audio/wav"
    finally:
        try:
            if stream is not None:
                stream.Close()
        except Exception:
            pass

def tts_elevenlabs(text: str, voice_id: str = "", speed: float = 1.0) -> tuple[bytes, str]:
    """ElevenLabs streamed TTS → collected bytes. Returns (bytes, mime)."""
    client = _el_client()
    if client is None:
        raise RuntimeError("no ElevenLabs key")
    speak = _normalize_speech(text)[: _MAX_TTS_CHARS]
    if not speak:
        raise ValueError("empty text")
    from elevenlabs import VoiceSettings

    audio = client.text_to_speech.convert(
        text=speak,
        voice_id=voice_id or EL_VOICE_ID,
        model_id=EL_TTS_MODEL,
        output_format="mp3_44100_128",
        voice_settings=VoiceSettings(
            stability=0.5, similarity_boost=0.75, speed=max(0.7, min(1.2, speed)),
        ),
    )
    buf = io.BytesIO()
    for chunk in audio:  # SDK yields chunks as they are generated
        if chunk:
            buf.write(chunk)
    data = buf.getvalue()
    if not data:
        raise RuntimeError("empty audio from ElevenLabs")
    return data, "audio/mpeg"

# ── Kokoro (local neural TTS, no key, no network at inference) ───────────

_KOKORO_DIR = os.path.join(
    os.getenv("LOCALAPPDATA", os.path.expanduser("~")), "JARVIS", "kokoro"
)
_kokoro_cache: dict = {"inst": None, "tried": False}

# Perf (benchmarked on an i5-10210U, 4C/8T): default ORT threading ran
# rtf ~3.8; a tuned session runs rtf ~1.0 when the box is quiet. KEY DETAIL:
# thread count must match PHYSICAL cores — 8 threads on 4 cores (HT siblings
# fighting) made the same synthesis swing between rtf 1.0 (quiet) and 9
# (any background load). psutil gives physical cores; fall back to
# logical/2 (a sane HT default) or 4. JARVIS_TTS_THREADS overrides.
try:
    import psutil as _psutil

    _PHYS_CORES = _psutil.cpu_count(logical=False) or max(1, (os.cpu_count() or 4) // 2)
except ImportError:
    _PHYS_CORES = max(1, (os.cpu_count() or 4) // 2)
_TTS_THREADS = int(os.getenv("JARVIS_TTS_THREADS", "0") or 0) or _PHYS_CORES

# Bounded LRU caches: phoneme strings (skips espeak re-phonemization,
# ~200ms/call) and rendered audio (repeated acks/status lines → ~0ms).
from collections import OrderedDict  # noqa: E402

_PHONEME_CACHE: OrderedDict[tuple[str, str], str] = OrderedDict()
_PHONEME_CACHE_MAX = 256
_AUDIO_CACHE: OrderedDict[str, tuple[bytes, str]] = OrderedDict()
_AUDIO_CACHE_MAX = 64
_STYLE_CACHE: OrderedDict[str, object] = OrderedDict()
_STYLE_CACHE_MAX = 32


def _kokoro_session(model_path: str):
    """Tuned CPU ONNX session (the single biggest Kokoro latency win)."""
    import onnxruntime as rt

    opts = rt.SessionOptions()
    opts.intra_op_num_threads = _TTS_THREADS
    opts.inter_op_num_threads = 1
    opts.execution_mode = rt.ExecutionMode.ORT_SEQUENTIAL
    opts.graph_optimization_level = rt.GraphOptimizationLevel.ORT_ENABLE_ALL
    return rt.InferenceSession(
        model_path, sess_options=opts, providers=["CPUExecutionProvider"]
    )


def _kokoro_paths() -> tuple[str, str]:
    model = os.path.join(_KOKORO_DIR, _KOKORO_FILES.get(KOKORO_PRECISION, _KOKORO_FILES["fp32"]))
    voices = os.path.join(_KOKORO_DIR, _KOKORO_VOICES)
    return model, voices


def _download(url: str, dest: str, desc: str) -> None:
    import urllib.request

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    logger.info("Kokoro: downloading %s → %s", desc, dest)
    urllib.request.urlretrieve(url, tmp)
    os.replace(tmp, dest)


def _kokoro_instance():
    """Load (or lazily download) the local Kokoro model. None = unavailable."""
    if _kokoro_cache["inst"] is not None:
        return _kokoro_cache["inst"]
    if _kokoro_cache["tried"]:
        return None  # a previous load attempt failed this process
    _kokoro_cache["tried"] = True
    model_path, voices_path = _kokoro_paths()
    try:
        from kokoro_onnx import Kokoro

        for url, path, desc in (
            (os.path.join(_KOKORO_RELEASE, _KOKORO_FILES.get(KOKORO_PRECISION, _KOKORO_FILES["fp32"])),
             model_path, _KOKORO_MODEL_DESC.format(KOKORO_PRECISION)),
            (f"{_KOKORO_RELEASE}/{_KOKORO_VOICES}", voices_path, "voices"),
        ):
            if not os.path.exists(path):
                _download(url, path, desc)
        t0 = time.monotonic()
        try:
            # Tuned-session injection via the library's _setup seam; falls
            # back to the stock constructor if the private API moves.
            inst = Kokoro.__new__(Kokoro)
            Kokoro._setup(
                inst,
                session=_kokoro_session(model_path),
                model_path=model_path,
                voices_path=voices_path,
                espeak_config=None,
                vocab_config=None,
            )
        except Exception:
            inst = Kokoro(model_path, voices_path)
        _kokoro_cache["inst"] = inst
        logger.info(
            "Kokoro-82M loaded (%s, %d threads) in %.1fs — local neural TTS active",
            KOKORO_PRECISION, _TTS_THREADS, time.monotonic() - t0,
        )
        return inst
    except Exception as e:
        logger.warning("Kokoro unavailable (%s); SAPI remains the fallback", e)
        return None


def prewarm() -> None:
    """Load Kokoro in the background so the first spoken reply isn't slow."""
    import threading

    threading.Thread(target=_kokoro_instance, daemon=True, name="kokoro-prewarm").start()


def _lru_get(cache, key, max_size):
    hit = cache.get(key)
    if hit is not None:
        cache.move_to_end(key)
    elif len(cache) >= max_size and cache:
        cache.popitem(last=False)
    return hit


def _voice_style(voice_name: str):
    """Per-voice style vector with LRU caching (skips name lookup on repeats)."""
    inst = _kokoro_cache["inst"]
    if inst is None:
        return None
    try:
        bank = getattr(inst, "voices", None)
        if isinstance(bank, dict) and voice_name not in bank:
            return None  # unknown voice → caller falls back to default
    except Exception:
        pass
    style = _lru_get(_STYLE_CACHE, voice_name, _STYLE_CACHE_MAX)
    if style is None:
        try:
            style = inst.get_voice_style(voice_name)
        except Exception:
            return None
        _STYLE_CACHE[voice_name] = style
    return style


def available_voices() -> list[str]:
    """Voice names usable with Kokoro (live keys from the bank when loaded)."""
    inst = _kokoro_cache["inst"]
    if inst is not None:
        try:
            bank = getattr(inst, "voices", None)
            if isinstance(bank, dict) and bank:
                return sorted(k for k in bank if isinstance(k, str))
        except Exception:
            pass
    return list(KOKORO_VOICES_KNOWN)


def tts_kokoro(text: str, voice: str = "", speed: float = 1.0) -> tuple[bytes, str]:
    """Local Kokoro-82M synthesis → 24kHz mono WAV (24kHz is its native rate).

    Optimization stack (all benchmarked):
    - tuned ONNX session (rtf ~3.8 → ~1.0 on this machine)
    - phoneme LRU: espeak re-phonemization (~200ms) skipped on repeats
    - audio LRU: repeated acks/status lines synthesize in ~0ms
    - per-voice style LRU: voice switching costs nothing after first use
    """
    speak = _normalize_speech(text)[:_MAX_TTS_CHARS]
    if not speak:
        raise ValueError("empty text")
    vname = (voice or KOKORO_VOICE).strip()
    spd = _clamp_speed(speed)
    cache_key = f"{vname}|{spd}|{speak}"
    cached = _lru_get(_AUDIO_CACHE, cache_key, _AUDIO_CACHE_MAX)
    if cached is not None:
        return cached
    inst = _kokoro_instance()
    if inst is None:
        raise RuntimeError("kokoro unavailable")

    key = (speak, KOKORO_LANG)
    phonemes = _lru_get(_PHONEME_CACHE, key, _PHONEME_CACHE_MAX)
    if phonemes is not None:
        style = _voice_style(vname)
        samples, sample_rate = inst.create(
            phonemes, voice=style if style is not None else KOKORO_VOICE,
            speed=spd, lang=KOKORO_LANG, is_phonemes=True,
        )
    else:
        samples, sample_rate = inst.create(
            speak, voice=vname, speed=spd, lang=KOKORO_LANG
        )
        try:
            _PHONEME_CACHE[key] = " ".join(inst.tokenizer.phonemize(speak, KOKORO_LANG).split())
            _PHONEME_CACHE.move_to_end(key)
        except Exception:
            pass

    data = _pcm_wav(samples, int(sample_rate))
    result = (data, "audio/wav")
    _AUDIO_CACHE[cache_key] = result
    return result


def _pcm_wav(samples, sample_rate: int) -> bytes:
    """float samples → 16-bit mono WAV. numpy path ~1000× the struct loop."""
    import wave

    try:
        import numpy as np

        pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    except ImportError:  # numpy absent → correctness-first loop
        import struct

        pcm = bytearray()
        for s in samples:
            s2 = max(-1.0, min(1.0, float(s)))
            pcm += struct.pack("<h", int(s2 * 32767))
        pcm = bytes(pcm)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def tts(text: str, voice: str = "", speed: float = 1.0) -> tuple[bytes, str, str]:
    """Speak ``text``. Returns (bytes, mime, engine_used).

    ``voice`` selects a Kokoro voice name (or an ElevenLabs voice id when a
    key is present — passed through unchanged). ``speed`` is clamped 0.5-2.0.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("text is required")
    spd = _clamp_speed(speed)
    t0 = time.monotonic()
    engine = "sapi"
    duration_ms = 0
    try:
        if _api_key():
            try:
                data, mime = tts_elevenlabs(text, voice_id=voice, speed=spd)
                engine = "elevenlabs"
            except Exception as e:
                logger.warning("ElevenLabs TTS failed (%s); trying local Kokoro", e)
        if engine == "sapi":
            inst = _kokoro_instance()
            if inst is not None:
                try:
                    data, mime = tts_kokoro(text, voice=voice, speed=spd)
                    engine = "kokoro"
                except Exception as e:
                    logger.warning("Kokoro TTS failed (%s); SAPI fallback", e)
        if engine == "sapi":
            data, mime = tts_sapi(text, speed=spd)
    finally:
        duration_ms = int((time.monotonic() - t0) * 1000)
    logger.info("voice: tts %s %.1fms (text_chunks=%d, voice=%s, speed=%.2f)",
                engine, duration_ms, (text.count("\n") + 1), voice or KOKORO_VOICE, spd)
    return data, mime, engine

# ── STT ───────────────────────────────────────────────────────────────────


def stt_bytes(data: bytes, filename: str = "audio.webm") -> str:
    """Transcribe audio bytes via ElevenLabs Scribe v2. Key-gated."""
    key = _api_key()
    if not key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY not configured — see SETUP-FREE-LLM-APIS.md"
        )
    client = _el_client() or _force_client(key)
    if client is None:
        raise RuntimeError("ElevenLabs SDK unavailable (pip install elevenlabs)")
    t0 = time.monotonic()
    try:
        result = client.speech_to_text.convert(
            file=(filename, data),
            model_id=EL_STT_MODEL,
        )
    finally:
        duration_ms = int((time.monotonic() - t0) * 1000)
    text = (getattr(result, "text", "") or "").strip()
    logger.info("voice: stt %s %.1fms (model=%s, audio_bytes=%d)",
                "ok" if text else "empty", duration_ms, EL_STT_MODEL, len(data))
    return text


def _force_client(key: str):
    try:
        from elevenlabs import ElevenLabs

        return ElevenLabs(api_key=key)
    except Exception:
        return None

# ── Instant acknowledgment (Mark-LIV "no silent waiting") ─────────────────

_ACK_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(search|find|look up|google)\b", re.I),
     "Searching now."),
    (re.compile(r"\b(open|launch|go to|navigate)\b", re.I),
     "Opening it."),
    (re.compile(r"\b(close|quit|shut)\b", re.I), "Closing."),
    (re.compile(r"\b(play|pause|skip)\b", re.I), "On it."),
    (re.compile(r"\b(volume|mute|louder|quieter)\b", re.I), "Adjusting."),
    (re.compile(r"\b(screenshot|capture)\b", re.I), "Capturing."),
    (re.compile(r"\b(summar(y|ize|ise))\b", re.I), "Summarizing."),
    (re.compile(r"\b(send|type|write|draft)\b", re.I), "Writing."),
]


def ack_for(text: str) -> str:
    """Short context-aware acknowledgment for task-like requests ('' if none)."""
    t = (text or "").strip()
    if len(t) < 4 or t.endswith("?"):
        return ""
    for rx, ack in _ACK_RULES:
        if rx.search(t):
            return ack
    return ""


def voice_status() -> dict:
    kokoro_ready = _kokoro_cache["inst"] is not None
    return {
        "ok": True,
        "tts": ("elevenlabs" if _api_key() else "kokoro" if kokoro_ready else "sapi"),
        "tts_chain": [
            name for name, on in (
                ("elevenlabs", bool(_api_key())),
                ("kokoro", kokoro_ready or not _kokoro_cache["tried"]),
                ("sapi", True),
            ) if on
        ],
        "stt": "elevenlabs" if _api_key() else None,
        "voice_id": EL_VOICE_ID,
        "tts_model": EL_TTS_MODEL,
        "stt_model": EL_STT_MODEL,
        "kokoro": {
            "precision": KOKORO_PRECISION,
            "loaded": kokoro_ready,
            "voice": KOKORO_VOICE,
            "threads": _TTS_THREADS,
            "phoneme_cache": len(_PHONEME_CACHE),
            "audio_cache": len(_AUDIO_CACHE),
            "voices": available_voices(),
        },
        "speed_range": [SPEED_MIN, SPEED_MAX],
    }
