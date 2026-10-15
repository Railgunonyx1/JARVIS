"""End-to-end check of the bridge voice routes through real HTTP.

Exercises the three routes the Orbit UI actually calls:
  POST /v1/voice/status  -> menu metadata (engines + speed range)
  POST /v1/tts           -> engine pinning (voice_model) + raw/json formats
  POST /v1/stt           -> base64 audio decode + length guard

Uses the injected engine seam (voice._tts_engine) so no TTS backend is
needed, but goes over a real socket through the real handler.
"""

from __future__ import annotations

import base64
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[1] / "jbrowser-bridge"
sys.path.insert(0, str(BRIDGE))

import voice as V  # noqa: E402
from server import serve  # noqa: E402


class FakeEngine:
    """Stand-in TTS engine; ``__name__`` becomes the reported engine id.

    Mirrors ``tts_kokoro``'s signature (accepts a ``voice`` id) and records
    what it was called with, so the route's threading can be asserted.
    """

    def __init__(self, name: str, payload: bytes = b"FAKE-WAV"):
        self.__name__ = name
        self.payload = payload
        self.calls: list[str] = []
        self.voices: list[str] = []

    def __call__(self, text: str, voice: str = "", speed: float = 1.0):
        self.calls.append(text)
        self.voices.append(voice)
        return self.payload, "audio/wav"


class NoVoiceEngine:
    """Engine with NO voice kwarg, like ``tts_sapi`` and the test doubles."""

    __name__ = "plain"

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, text: str, speed: float = 1.0):
        self.calls.append(text)
        return b"PLAIN-BYTES", "audio/wav"


def post(base: str, path: str, payload: dict):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main() -> int:
    sapi = FakeEngine("sapi", b"SAPI-BYTES")
    kokoro = FakeEngine("kokoro", b"KOKORO-BYTES")
    V._tts_engine = {"sapi": sapi, "kokoro": kokoro}
    V._api_key = lambda: ""

    httpd = serve(host="127.0.0.1", port=0, backend_kind="echo")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    failures: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        print(f"  {'PASS' if cond else 'FAIL'}  {label}{(' — ' + detail) if detail else ''}")
        if not cond:
            failures.append(label)

    try:
        print("POST /v1/voice/status")
        st, d = post(base, "/v1/voice/status", {})
        check("status 200", st == 200, f"got {st}")
        menu = d.get("voice_menu") or {}
        check("voice_menu present", bool(menu), json.dumps(menu)[:120])
        check("engines is a list", isinstance(menu.get("engines"), list), repr(menu.get("engines"))[:120])
        check("engine list non-empty", bool(menu.get("engines")), repr(menu.get("engines")))
        check("speed_range is 2 floats",
              isinstance(menu.get("speed_range"), list) and len(menu["speed_range"]) == 2,
              repr(menu.get("speed_range")))
        check("tts_chain intact", isinstance(d.get("tts_chain"), list), repr(d.get("tts_chain")))

        print("\nPOST /v1/tts (default engine)")
        st, d = post(base, "/v1/tts", {"text": "hello there"})
        check("status 200", st == 200, f"got {st} {d}")
        check("engine == sapi", d.get("engine") == "sapi", repr(d.get("engine")))
        check("audio decodes to SAPI-BYTES",
              base64.b64decode(d["audio_b64"]) == b"SAPI-BYTES")

        print("\nPOST /v1/tts (voice_model=kokoro pins the engine)")
        st, d = post(base, "/v1/tts", {"text": "pinned", "voice_model": "kokoro"})
        check("status 200", st == 200, f"got {st} {d}")
        check("engine == kokoro", d.get("engine") == "kokoro", repr(d.get("engine")))
        check("kokoro actually rendered",
              base64.b64decode(d["audio_b64"]) == b"KOKORO-BYTES")
        check("kokoro engine was called", "pinned" in kokoro.calls, repr(kokoro.calls))

        print("\nPOST /v1/tts (unknown voice_model falls back, never 500)")
        st, d = post(base, "/v1/tts", {"text": "fallback", "voice_model": "nope"})
        check("status 200 (no crash)", st == 200, f"got {st} {d}")
        check("reports the REAL engine, not 'nope'", d.get("engine") == "sapi",
              repr(d.get("engine")))

        print("\nPOST /v1/tts (voice_model=auto keeps default chain)")
        st, d = post(base, "/v1/tts", {"text": "auto", "voice_model": "auto"})
        check("status 200", st == 200, f"got {st}")
        check("auto -> default engine", d.get("engine") in ("sapi", "kokoro"), repr(d.get("engine")))

        print("\nPOST /v1/tts (format=raw streams binary)")
        req = urllib.request.Request(
            base + "/v1/tts",
            data=json.dumps({"text": "raw please", "format": "raw"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read()
            check("raw content-type", r.headers.get("Content-Type") == "audio/wav",
                  repr(r.headers.get("Content-Type")))
            check("raw engine header", r.headers.get("X-Voice-Engine") == "sapi",
                  repr(r.headers.get("X-Voice-Engine")))
            check("raw body is bytes", body == b"SAPI-BYTES", repr(body))

        print("\nPOST /v1/tts (speed clamped)")
        st, d = post(base, "/v1/tts", {"text": "fast", "speed": 99})
        check("status 200 with out-of-range speed", st == 200, f"got {st}")

        print("\nPOST /v1/tts (empty text rejected)")
        st, d = post(base, "/v1/tts", {"text": "   "})
        check("status 400", st == 400, f"got {st}")
        check("error mentions text", "text" in str(d.get("error", "")), repr(d.get("error")))

        print("\nPOST /v1/tts (voice id is threaded to the engine)")
        st, d = post(base, "/v1/tts", {"text": "voiced", "voice_model": "kokoro",
                                        "voice": "bm_george"})
        check("status 200", st == 200, f"got {st} {d}")
        check("engine received the voice id", kokoro.voices[-1] == "bm_george",
              repr(kokoro.voices[-3:]))

        print("\nPOST /v1/tts (empty voice uses engine default)")
        st, d = post(base, "/v1/tts", {"text": "novoice", "voice_model": "kokoro"})
        check("status 200", st == 200, f"got {st} {d}")
        check("no voice id invented", kokoro.voices[-1] == "", repr(kokoro.voices[-1:]))

        print("\nPOST /v1/tts (engine WITHOUT a voice kwarg still works)")
        plain = NoVoiceEngine()
        V._tts_engine = plain
        st, d = post(base, "/v1/tts", {"text": "plain", "voice": "af_heart"})
        check("status 200 (voice kwarg not forced)", st == 200, f"got {st} {d}")
        check("plain engine ran", plain.calls == ["plain"], repr(plain.calls))
        V._tts_engine = {"sapi": sapi, "kokoro": kokoro}

        print("\nPOST /v1/stt (short audio rejected)")
        st, d = post(base, "/v1/stt",
                     {"audio_b64": base64.b64encode(b"\x00" * 10).decode()})
        check("status 400", st == 400, f"got {st}")
        check("error mentions short", "short" in str(d.get("error", "")), repr(d.get("error")))
    finally:
        httpd.shutdown()
        httpd.server_close()

    print()
    if failures:
        print(f"FAILED {len(failures)} check(s): {failures}")
        return 1
    print("ALL VOICE ROUTE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())