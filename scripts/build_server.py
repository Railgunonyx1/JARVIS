"""Assemble the final jbrowser-bridge/server.py from HEAD, inserting the
new TTS/STT/voice-status route methods into BridgeHandler right after
do_OPTIONS."""
import subprocess
import sys

ROOT = "."
HEAD = "jbrowser-bridge/server.py"


def git_show(path):
    out = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        capture_output=True, text=True, cwd=ROOT,
    )
    if out.returncode != 0:
        sys.stderr.write(out.stderr)
        sys.exit(1)
    return out.stdout


def main():
    head = git_show("jbrowser-bridge/server.py").split("\n")

    class_idx = next(i for i, l in enumerate(head) if l.startswith("class BridgeHandler"))
    serve_idx = next(i for i, l in enumerate(head) if l.startswith("def serve("))

    # After the real do_OPTIONS, whose body is the line
    # 'self.send_response(204)', insert the voice route methods.
    voice_methods = VOICE_METHODS

    new_class = []
    inserted = False
    sliced = head[class_idx:serve_idx]
    for local_i, l in enumerate(sliced):
        new_class.append(l)
        if not inserted and l.startswith("    def do_OPTIONS(self) -> None:") \
                and local_i + 1 < len(sliced) and sliced[local_i + 1].strip() == "self.send_response(204)":
            new_class.extend(voice_methods)
            inserted = True
    if not inserted:
        sys.stderr.write("ERROR: real do_OPTIONS not found in class body\n")
        sys.exit(1)

    full = head[:class_idx] + new_class + head[serve_idx:]

    with open(HEAD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(full))

    print("WRITTEN", HEAD, "total lines:", len(full))


VOICE_METHODS = [
    "",
    "    # ── HTTP verbs ─────────────────────────────────────────────────────────",
    "    def _tts(self) -> None:",
    '        """POST /v1/tts — render speech audio from text.',
    "",
    '        Request body: {"text": str, "speed": float} (speed clamped to',
    "        ``SPEED_MIN..SPEED_MAX``, default 1.0).",
    "",
    '        Response: 200 ``audio/wav``; 400 invalid body; 401 unauth; 501 when',
    "        the SAPI engine is unavailable (non-Windows targets).",
    '        """',
    "        if not self._host_ok():",
    '            self._json(403, {"ok": False, "error": "forbidden host"})',
    "            return",
    "        if not self._authorized():",
    '            self._json(401, {"ok": False, "error": "unauthorized", "code": "unauthorized"})',
    "            return",
    "        data = self._read_json()",
    "        if data is None:",
    '            self._json(400, {"ok": False, "error": "invalid json body"})',
    "            return",
    '        text = str(data.get("text") or "").strip()',
    "        if not text:",
    '            self._json(400, {"ok": False, "error": "missing \'text\'"})',
    "            return",
    "        speed = _clamp_speed(data.get(\"speed\", 1.0))",
    "        try:",
    "            data_b, mime, engine_used = _tts_one(text, speed=speed)",
    "        except Exception as exc:  # noqa: BLE001",
    '            logger.exception("tts failed")',
    '            self._json(501, {"ok": False, "error": "tts_unavailable", "code": "tts_unavailable", "engine": "sapi"})',
    "            return",
    "        self.send_response(200)",
    '        self.send_header("Content-Type", mime)',
    '        self.send_header("X-Voice-Engine", _header_safe(engine_used))',
    '        self.send_header("Content-Length", str(len(data_b)))',
    "        self.end_headers()",
    "        try:",
    "            self.wfile.write(data_b)",
    "        except (BrokenPipeError, ConnectionResetError,",
    "                ConnectionAbortedError, TimeoutError, OSError):",
    "            pass",
    "",
    "    def _stt(self) -> None:",
    '        """POST /v1/stt — transcribe audio bytes to text.',
    "",
    '        Request body: raw audio bytes (sent with the correct',
    "        ``Content-Type``); the filename is taken from the",
    "        ``X-Stt-Filename`` header (default ``audio.webm``).",
    "",
    '        Response: 200 JSON {"text": str}; 400 invalid body; 401 unauth;',
    "        501 when STT cannot run (no API key / unavailable engine).",
    '        """',
    "        if not self._host_ok():",
    '            self._json(403, {"ok": False, "error": "forbidden host"})',
    "            return",
    "        if not self._authorized():",
    '            self._json(401, {"ok": False, "error": "unauthorized", "code": "unauthorized"})',
    "            return",
    '        filename = self.headers.get("X-Stt-Filename", "audio.webm")',
    "        try:",
    '            length = int(self.headers.get("Content-Length", "0"))',
    "        except ValueError:",
    "            length = 0",
    "        if length <= 0:",
    '            self._json(400, {"ok": False, "error": "missing audio bytes"})',
    "            return",
    "        try:",
    "            data = self.rfile.read(length)",
    "        except OSError:",
    '            data = b""',
    "        try:",
    "            text = stt_bytes(data, filename=filename)",
    "        except Exception as exc:  # noqa: BLE001",
    '            logger.exception("stt failed")',
    '            self._json(501, {"ok": False, "error": "stt_unavailable", "code": "stt_unavailable"})',
    "            return",
    '        self._json(200, {"ok": True, "text": text})',
    "",
    "    def _voice_status(self) -> None:",
    '        """GET /v1/voice/status — bridge voice subsystem status.',
    "",
    '        Response: 200 JSON status payload from :func:`voice_status`.',
    '        """',
    "        if not self._host_ok():",
    '            self._json(403, {"ok": False, "error": "forbidden host"})',
    "            return",
    '        self._json(200, voice_status())',
    "",
    "    # ── CORS / plumbing",
    "",
]


if __name__ == "__main__":
    main()
