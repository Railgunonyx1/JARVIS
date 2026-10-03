"""Live check of the new voice-engine surface over a real socket.

Spins up the bridge exactly as the Orbit renderer would talk to it and
asserts the shapes the UI depends on:
  - GET  /v1/voice/status reports the full TTS + STT inventory
  - every engine row carries available/reason so the picker can grey it out
  - POST /v1/stt accepts an engine pin and 503s with an actionable message

Run: python scripts/voice_engines_e2e.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "jbrowser-bridge"))

import server as S  # noqa: E402
import voice as V  # noqa: E402
import voice_engines as VE  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  PASS  {label}" + (f" — {detail}" if detail else ""))
    else:
        FAILURES.append(label)
        print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))


def post(base: str, path: str, payload: dict):
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main() -> int:
    # Isolate from ambient keys: this asserts the NO-CONFIG path, which is
    # what a fresh clone actually does.
    for var in ("ELEVENLABS_API_KEY", "GROQ_API_KEY", "DEEPGRAM_API_KEY",
                "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION", "GOOGLE_API_KEY",
                "GOOGLE_TTS_API_KEY", "GEMINI_API_KEY", "AWS_ACCESS_KEY_ID"):
        os.environ.pop(var, None)
    V._api_key = lambda: ""
    VE._env = lambda *names: ""          # noqa: SLF001 - deliberate isolation

    httpd = S.serve(host="127.0.0.1", port=0, backend_kind="echo")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    try:
        print("GET /v1/voice/status")
        status, d = post(base, "/v1/voice/status", {})
        check("status 200", status == 200, f"got {status}")
        menu = d.get("voice_menu") or {}
        tts = menu.get("tts_engines") or []
        stt = menu.get("stt_engines") or []

        check("tts inventory present", len(tts) >= 7, f"{len(tts)} engines")
        check("stt inventory present", len(stt) >= 3, f"{len(stt)} engines")
        check("stt default reported", "stt" in menu, repr(menu.get("stt")))

        ids = [e["id"] for e in tts]
        for want in ("edge", "kokoro", "sapi", "google", "azure", "polly", "elevenlabs"):
            check(f"tts engine '{want}' listed", want in ids, str(ids))

        check("every row has an id/label/kind",
              all(e.get("id") and e.get("label") and e.get("kind") for e in tts + stt))
        check("every row reports availability",
              all(isinstance(e.get("available"), bool) for e in tts + stt))
        dark = [e for e in tts + stt if not e["available"]]
        check("dimmed rows explain why", all(e.get("reason") for e in dark),
              f"{len(dark)} dimmed rows")
        check("every row carries its free-tier note",
              all(e.get("note") for e in tts + stt))
        edge = next((e for e in tts if e["id"] == "edge"), None)
        check("edge available with no key at all", bool(edge and edge["available"]),
              repr(edge))
        check("edge offers voices", bool(edge and edge["voices"]),
              repr(edge and edge["voices"]))

        print("\nPOST /v1/stt (no engine configured)")
        import base64
        status, d = post(base, "/v1/stt", {
            "audio_b64": base64.b64encode(b"\x00" * 500).decode(),
            "filename": "clip.webm",
        })
        check("status 503", status == 503, f"got {status}")
        msg = (d.get("error") or "")
        check("error names a settable env var",
              "GROQ_API_KEY" in msg or "DEEPGRAM_API_KEY" in msg, msg[:90])
        check("error is not pinned to one provider",
              "GROQ_API_KEY" in msg and "DEEPGRAM_API_KEY" in msg, msg[:90])

        print("\nPOST /v1/stt (explicit pin to an unconfigured engine)")
        status, d = post(base, "/v1/stt", {
            "audio_b64": base64.b64encode(b"\x00" * 500).decode(),
            "filename": "clip.webm", "engine": "deepgram",
        })
        check("status 503", status == 503, f"got {status}")
        check("names the PINNED engine's key, not another",
              "DEEPGRAM_API_KEY" in (d.get("error") or ""), (d.get("error") or "")[:90])
        check("echoes the requested engine", d.get("engine") == "deepgram",
              repr(d.get("engine")))

        print("\nPOST /v1/stt (unknown engine never 500s)")
        status, d = post(base, "/v1/stt", {
            "audio_b64": base64.b64encode(b"\x00" * 500).decode(),
            "engine": "not-a-real-engine",
        })
        check("status 503 not 500", status == 503, f"got {status}")

        print("\nPOST /v1/tts (new engine ids resolve)")
        for engine in ("edge", "google", "azure", "polly"):
            status, d = post(base, "/v1/tts", {"text": "hi", "voice_model": engine})
            # Any status is fine; what matters is that it is NOT a routing 404
            # and that a failure names the engine's own configuration gap.
            check(f"'{engine}' is a known engine (no 404)",
                  status in (200, 500), f"got {status}")
            if status == 500:
                check(f"'{engine}' failure is actionable, not generic",
                      "API_KEY" in (d.get("error") or "") or "REGION" in (d.get("error") or "")
                      or "boto3" in (d.get("error") or ""), (d.get("error") or "")[:80])
    finally:
        httpd.shutdown()

    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} passed")
    if FAILURES:
        print("FAILED: " + ", ".join(FAILURES))
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())