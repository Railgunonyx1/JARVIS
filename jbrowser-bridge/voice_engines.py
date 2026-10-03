"""Cloud TTS / STT engines and their availability descriptors.

Kept separate from :mod:`voice` so the bridge's local-voice machinery (SAPI,
Kokoro, ElevenLabs) does not grow another few hundred lines.

Every engine here speaks plain HTTP through :mod:`urllib.request` — the same
stdlib path ``core/http_pool.py`` already uses — so adding Google, Azure,
Polly, Groq and Deepgram costs **no new dependency**. The only optional
import is ``boto3`` (Polly); its absence downgrades that one engine instead
of the module.

Engine contract (must match what :func:`voice._call_engine` probes for):

* TTS   ``fn(text: str, speed: float = 1.0, voice: str = "") -> (bytes, mime)``
* STT   ``fn(data: bytes, filename: str = "audio.webm") -> str``

Free-tier allowances are documented in :data:`FREE_TIER_NOTES` and are the
numbers published by each vendor as of 2026-09. They are NOT contractual —
recheck before depending on them.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field

# Shared house rules so cloud engines clip the same way the local ones do.
from voice import _MAX_TTS_CHARS, _normalize_speech

_HTTP_TIMEOUT_S = 20
_STT_TIMEOUT_S = 45

# User agent: several vendors reject the default urllib string outright.
_UA = "JARVIS/1.0 (+https://github.com/Railgunonyx1/JARVIS)"


def _env(*names: str) -> str:
    """First non-empty environment variable among ``names``."""
    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _has_module(name: str) -> bool:
    """Cheap, import-free dependency probe (never imports the package)."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _post(url: str, *, data: bytes, headers: dict[str, str],
          timeout: int = _HTTP_TIMEOUT_S) -> tuple[int, bytes]:
    """POST and return (status, body). HTTP errors return their status, not raise."""
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("User-Agent", _UA)
    for key, value in headers.items():
        if value:
            request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:  # 4xx/5xx carry the useful message
        return exc.code, exc.read()


def _post_json(url: str, payload: dict, headers: dict[str, str],
               timeout: int = _HTTP_TIMEOUT_S) -> dict:
    body = json.dumps(payload).encode("utf-8")
    merged = {"Content-Type": "application/json", **headers}
    _status, raw = _post(url, data=body, headers=merged, timeout=timeout)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError("unreadable response from provider") from None
    return parsed if isinstance(parsed, dict) else {"result": parsed}


def _get_json(url: str, headers: dict[str, str], timeout: int = _HTTP_TIMEOUT_S) -> dict:
    request = urllib.request.Request(url, method="GET")
    request.add_header("User-Agent", _UA)
    for key, value in headers.items():
        if value:
            request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"provider returned HTTP {exc.code}") from None
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError("unreadable response from provider") from None


def _provider_error(payload: dict, default: str) -> str:
    """Pull the human-readable message out of a vendor error envelope."""
    err = payload.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or default)
    if isinstance(err, str):
        return err
    return str(payload.get("message") or default)


def _clip(text: str) -> str:
    speak = _normalize_speech(text)[:_MAX_TTS_CHARS]
    if not speak:
        raise ValueError("empty text")
    return speak


# ── Free-tier notes (published vendor numbers, 2026-09) ───────────────────
# Surfaced by voice_status() so the UI can explain WHY an engine is dimmed
# and what configuring it would cost the user.
FREE_TIER_NOTES: dict[str, str] = {
    "elevenlabs": "10k credits/mo; free plan is non-commercial",
    "azure": "F0: 500k TTS chars/mo + 5 STT hours/mo (card required)",
    "polly": "12mo of 5M std / 1M neural chars per mo for AWS accounts "
             "created before 15 Jul 2025; newer accounts get $200 credit",
    "google": "1M chars/mo Chirp 3 HD, 4M WaveNet/Standard (billing enabled)",
    "edge": "unlimited, no key, unofficial Microsoft endpoint",
    "kokoro": "unlimited, local, no network",
    "sapi": "unlimited, local, Windows only",
    "groq": "free plan: 20 req/min, 2k/day, 28.8k audio-sec/day, 25MB",
    "deepgram": "$200 account credit on signup",
}


# ═══════════════════════════════════════════════════════════════════════
# TTS engines
# ═══════════════════════════════════════════════════════════════════════

def tts_edge(text: str, voice: str = "", speed: float = 1.0) -> tuple[bytes, str]:
    """Microsoft Edge neural voices via the ``edge-tts`` package.

    No API key, no signup, and far more natural than Windows SAPI. The
    endpoint is unofficial (it is the one Edge's own read-aloud uses), so it
    can break without notice -- which is why it is never the sole chain head.
    """
    import asyncio

    import edge_tts

    speak = _clip(text)
    voice_id = voice or "en-US-AriaNeural"
    rate = f"{int(round(max(0.5, min(2.0, speed)) * 100)) - 100:+d}%"

    async def _run() -> bytes:
        comm = edge_tts.Communicate(speak, voice_id, rate=rate)
        buf = bytearray()
        async for chunk in comm.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                buf.extend(chunk["data"])
        return bytes(buf)

    try:
        data = asyncio.run(_run())
    except RuntimeError as exc:
        raise RuntimeError(f"Edge TTS failed: {exc}") from None
    if not data:
        raise RuntimeError("Edge TTS returned no audio")
    return data, "audio/mpeg"


def tts_google(text: str, voice: str = "", speed: float = 1.0) -> tuple[bytes, str]:
    """Google Cloud Text-to-Speech (v1 REST, LINEAR16 24 kHz mono)."""
    speak = _clip(text)  # validate locally before touching the network
    key = _env("GOOGLE_TTS_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_API_KEY not configured")
    payload = {
        "input": {"text": speak},
        "voice": {
            "languageCode": "en-US",
            "name": voice or "en-US-Chirp3-HD-Achernar",
        },
        "audioConfig": {
            "audioEncoding": "LINEAR16",
            "sampleRateHertz": 24000,
            # Google expresses rate as a percentage delta over normal.
            "speakingRate": round(max(0.25, min(4.0, speed)), 2),
        },
    }
    result = _post_json(
        f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}",
        payload, {},
    )
    audio_b64 = result.get("audioContent")
    if not audio_b64:
        raise RuntimeError(_provider_error(result, "Google TTS returned no audio"))
    try:
        return base64.b64decode(audio_b64), "audio/L16"
    except (ValueError, TypeError):
        raise RuntimeError("Google TTS returned undecodable audio") from None


def tts_azure(text: str, voice: str = "", speed: float = 1.0) -> tuple[bytes, str]:
    """Azure AI Speech (REST SSML, 24 kHz 48 kbps mono MP3)."""
    speak = _clip(text)  # validate locally before touching the network
    key = _env("AZURE_SPEECH_KEY")
    region = _env("AZURE_SPEECH_REGION")
    if not key or not region:
        raise RuntimeError("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION are both required")
    # SSML escapes, then a prosody-rate wrapper for speed.
    escaped = (
        speak.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    percent = f"{int(round(max(0.5, min(2.0, speed)) * 100))}%"
    ssml = (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="en-US"><voice name="{voice or "en-US-JennyNeural"}">'
        f'<prosody rate="{percent}">{escaped}</prosody></voice></speak>'
    )
    url = (
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        f"?language=en-US"
    )
    status, raw = _post(
        url,
        data=ssml.encode("utf-8"),
        headers={
            "Content-Type": "application/ssml+xml",
            "Ocp-Apim-Subscription-Key": key,
            "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            "User-Agent": _UA,
        },
    )
    if status >= 400 or not raw:
        detail = raw[:200].decode("utf-8", "replace")
        raise RuntimeError(f"Azure Speech returned HTTP {status}: {detail}")
    return raw, "audio/mpeg"


def tts_polly(text: str, voice: str = "", speed: float = 1.0) -> tuple[bytes, str]:
    """Amazon Polly neural/standard voices (boto3, optional dependency)."""
    speak = _clip(text)  # validate locally before touching the network
    if not _has_module("boto3"):
        raise RuntimeError("Amazon Polly needs boto3 (pip install boto3)")
    import boto3  # noqa: PLC0415 - optional dependency, gated by the check above
    client = boto3.client("polly", region_name=os.getenv("AWS_REGION") or "us-east-1")
    # Polly clamps SSML prosody rate to 0.5x-2x.
    percent = f"{int(round(max(0.5, min(2.0, speed)) * 100))}%"
    escaped = (
        speak.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    try:
        response = client.synthesize_speech(
            Text=f"<prosody rate=\"{percent}\">{escaped}</prosody>",
            TextType="ssml",
            OutputFormat="mp3",
            VoiceId=voice or "Joanna",
        )
    except Exception as exc:  # noqa: BLE001 - botocore raises many shapes
        raise RuntimeError(f"Amazon Polly failed: {exc}") from None
    stream = response.get("AudioStream")
    data = stream.read() if stream is not None else b""
    if not data:
        raise RuntimeError("Amazon Polly returned no audio")
    return data, "audio/mpeg"


# ═══════════════════════════════════════════════════════════════════════
# STT engines
# ═══════════════════════════════════════════════════════════════════════

def _multipart(fields: dict[str, str], filename: str, blob: bytes,
               mime: str) -> tuple[bytes, str]:
    """Build a multipart/form-data body. Returns (body, content_type)."""
    boundary = "----jarvis" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'
            .encode("utf-8")
        )
    chunks.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n".encode("utf-8")
    )
    chunks.append(blob)
    chunks.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


_GUESSES = (
    (".webm", "audio/webm"), (".ogg", "audio/ogg"), (".oga", "audio/ogg"),
    (".mp3", "audio/mpeg"), (".wav", "audio/wav"), (".m4a", "audio/mp4"),
    (".mp4", "audio/mp4"), (".flac", "audio/flac"), (".aac", "audio/aac"),
)


def _guess_mime(filename: str) -> str:
    lowered = (filename or "").lower()
    for suffix, mime in _GUESSES:
        if lowered.endswith(suffix):
            return mime
    return "application/octet-stream"


def stt_groq(data: bytes, filename: str = "audio.webm") -> str:
    """Groq-hosted Whisper (OpenAI-compatible /audio/transcriptions).

    ``GROQ_API_KEY`` is already a first-class key in this project (it heads the
    provider router's default fallback chain), so this is usually the cheapest
    way to make push-to-talk work with no new signup.
    """
    key = _env("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not configured")
    body, content_type = _multipart(
        {"model": "whisper-large-v3-turbo", "response_format": "json", "language": "en"},
        filename or "audio.webm", data, _guess_mime(filename),
    )
    # The body is multipart, not JSON, so it is posted directly rather than
    # through _post_json.
    status, raw = _post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": content_type},
        timeout=_STT_TIMEOUT_S,
    )
    if status >= 400:
        detail = raw[:200].decode("utf-8", "replace")
        raise RuntimeError(f"Groq returned HTTP {status}: {detail}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError("Groq returned unreadable JSON") from None
    text = str(payload.get("text") or "").strip()
    if not text:
        raise RuntimeError("Groq returned an empty transcript")
    return text


def stt_deepgram(data: bytes, filename: str = "audio.webm") -> str:
    """Deepgram Nova-3 (raw-body REST, no SDK, $200 signup credit)."""
    key = _env("DEEPGRAM_API_KEY")
    if not key:
        raise RuntimeError("DEEPGRAM_API_KEY not configured")
    url = (
        "https://api.deepgram.com/v1/listen"
        "?model=nova-3&smart_format=true&punctuate=true&language=en"
    )
    status, raw = _post(
        url,
        data=data,
        headers={
            "Authorization": f"Token {key}",
            "Content-Type": _guess_mime(filename),
        },
        timeout=_STT_TIMEOUT_S,
    )
    if status >= 400:
        detail = raw[:200].decode("utf-8", "replace")
        raise RuntimeError(f"Deepgram returned HTTP {status}: {detail}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError("Deepgram returned unreadable JSON") from None
    try:
        text = str(
            payload["results"]["channels"][0]["alternatives"][0]["transcript"]
        ).strip()
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Deepgram response had no transcript") from None
    if not text:
        raise RuntimeError("Deepgram returned an empty transcript")
    return text


# ═══════════════════════════════════════════════════════════════════════
# Availability
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class EngineInfo:
    """One selectable engine and whether it can actually serve right now."""

    id: str
    label: str
    kind: str                      # "tts" | "stt"
    available: bool
    reason: str = ""               # why not, when unavailable
    key_env: str = ""              # the env var that unlocks it
    note: str = ""                 # free-tier allowance
    needs_key: bool = False
    voices: tuple[str, ...] = field(default=())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "available": self.available,
            "reason": self.reason,
            "key_env": self.key_env,
            "note": self.note,
            "needs_key": self.needs_key,
            "voices": list(self.voices),
        }


# A few well-known voices per engine, offered to the picker so the user can
# pick something better than the default without leaving the window.
_EDGE_VOICES = (
    "en-US-AriaNeural", "en-US-GuyNeural", "en-US-JennyNeural",
    "en-GB-SoniaNeural", "en-GB-RyanNeural", "en-AU-NatashaNeural",
)
_GOOGLE_VOICES = (
    "en-US-Chirp3-HD-Achernar", "en-US-Chirp3-HD-Charon",
    "en-US-Chirp3-HD-Kore", "en-US-Studio-NaturalNeural",
)
_AZURE_VOICES = (
    "en-US-JennyNeural", "en-US-GuyNeural", "en-US-AriaNeural",
    "en-GB-SoniaNeural",
)
_POLLY_VOICES = ("Joanna", "Matthew", "Ivy", "Salli", "Kevin", "Amy")


def _tts_registry() -> list[EngineInfo]:
    """Every TTS engine JARVIS can name, best-quality-first when configured."""
    from voice import _api_key, _kokoro_cache  # local import: circular by design

    out: list[EngineInfo] = []

    el_key = bool(_api_key())
    out.append(EngineInfo(
        "elevenlabs", "ElevenLabs", "tts", el_key,
        reason="" if el_key else "ELEVENLABS_API_KEY not set",
        key_env="ELEVENLABS_API_KEY", note=FREE_TIER_NOTES["elevenlabs"],
        needs_key=True,
    ))

    az_key, az_region = _env("AZURE_SPEECH_KEY"), _env("AZURE_SPEECH_REGION")
    az_ok = bool(az_key and az_region)
    out.append(EngineInfo(
        "azure", "Azure Speech", "tts", az_ok,
        reason="" if az_ok else (
            "AZURE_SPEECH_REGION not set" if az_key and not az_region
            else "AZURE_SPEECH_KEY not set" if az_region
            else "AZURE_SPEECH_KEY + AZURE_SPEECH_REGION not set"
        ),
        key_env="AZURE_SPEECH_KEY", note=FREE_TIER_NOTES["azure"],
        needs_key=True, voices=_AZURE_VOICES,
    ))

    polly_ok = _has_module("boto3") and bool(
        _env("AWS_ACCESS_KEY_ID", "AWS_PROFILE", "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")
    )
    out.append(EngineInfo(
        "polly", "Amazon Polly", "tts", polly_ok,
        reason="" if polly_ok else (
            "boto3 not installed (pip install boto3)" if not _has_module("boto3")
            else "no AWS credentials in the environment"
        ),
        key_env="AWS_ACCESS_KEY_ID", note=FREE_TIER_NOTES["polly"],
        needs_key=True, voices=_POLLY_VOICES,
    ))

    gg_ok = bool(_env("GOOGLE_TTS_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"))
    out.append(EngineInfo(
        "google", "Google Cloud TTS", "tts", gg_ok,
        reason="" if gg_ok else "GOOGLE_API_KEY not set",
        key_env="GOOGLE_API_KEY", note=FREE_TIER_NOTES["google"],
        needs_key=True, voices=_GOOGLE_VOICES,
    ))

    edge_ok = _has_module("edge_tts")
    out.append(EngineInfo(
        "edge", "Edge Neural (free)", "tts", edge_ok,
        reason="" if edge_ok else "edge-tts not installed (pip install edge-tts)",
        key_env="", note=FREE_TIER_NOTES["edge"], voices=_EDGE_VOICES,
    ))

    # Kokoro reports "not tried yet" as available: the first synthesis is what
    # loads it, so it is optimistically offered and degrades on failure.
    kokoro_tried = bool(_kokoro_cache.get("tried"))
    kokoro_ok = _kokoro_cache.get("inst") is not None or not kokoro_tried
    out.append(EngineInfo(
        "kokoro", "Kokoro (local)", "tts", kokoro_ok,
        reason="" if kokoro_ok else "Kokoro model failed to load",
        key_env="", note=FREE_TIER_NOTES["kokoro"],
    ))

    out.append(EngineInfo(
        "sapi", "SAPI (Windows)", "tts", os.name == "nt",
        reason="" if os.name == "nt" else "SAPI is Windows-only",
        key_env="", note=FREE_TIER_NOTES["sapi"],
    ))
    return out


def _stt_registry() -> list[EngineInfo]:
    from voice import _api_key  # local import: circular by design

    el_key = bool(_api_key())
    groq_key = bool(_env("GROQ_API_KEY"))
    dg_key = bool(_env("DEEPGRAM_API_KEY"))
    return [
        EngineInfo(
            "elevenlabs", "ElevenLabs Scribe", "stt", el_key,
            reason="" if el_key else "ELEVENLABS_API_KEY not set",
            key_env="ELEVENLABS_API_KEY", note=FREE_TIER_NOTES["elevenlabs"],
            needs_key=True,
        ),
        EngineInfo(
            "groq", "Groq Whisper Turbo", "stt", groq_key,
            reason="" if groq_key else "GROQ_API_KEY not set",
            key_env="GROQ_API_KEY", note=FREE_TIER_NOTES["groq"], needs_key=True,
        ),
        EngineInfo(
            "deepgram", "Deepgram Nova-3", "stt", dg_key,
            reason="" if dg_key else "DEEPGRAM_API_KEY not set",
            key_env="DEEPGRAM_API_KEY", note=FREE_TIER_NOTES["deepgram"],
            needs_key=True,
        ),
    ]


def tts_engines() -> list[EngineInfo]:
    """All TTS engines with live availability (cached per call, cheap)."""
    return _tts_registry()


def stt_engines() -> list[EngineInfo]:
    """All STT engines with live availability."""
    return _stt_registry()


# Registry of callable engines, keyed by the same ids reported above.
TTS_FUNCTIONS = {
    "edge": tts_edge,
    "google": tts_google,
    "azure": tts_azure,
    "polly": tts_polly,
}
STT_FUNCTIONS = {
    "groq": stt_groq,
    "deepgram": stt_deepgram,
}


def first_available_stt() -> EngineInfo | None:
    """The STT engine the server picks when the client does not choose."""
    for info in _stt_registry():
        if info.available:
            return info
    return None