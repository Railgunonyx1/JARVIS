"""
JARVIS MK-X — Web Server
Serves the Arc Reactor HUD dashboard and provides API backend.

Endpoints:
  GET  /                    → Dashboard HTML
  GET  /api/health          → Health check report
  GET  /api/status          → System status
  POST /api/chat            → Send text, get AI response (non-streaming)
  POST /api/chat/stream     → Streaming chat (SSE: tokens + TTS)
  GET  /api/chat/history    → Recent chat history
  POST /api/stt             → Send audio bytes, get transcribed text
  POST /api/tts             → Text to speech (single response)
  POST /api/tts/stream      → Streaming TTS (SSE chunks)
  POST /api/tts/stop        → Interrupt active TTS
  GET  /api/camera/stream   → MJPEG camera stream
  GET  /api/telemetry/stream→ SSE telemetry (CPU/RAM/GPU)
  POST /api/performance     → Set performance mode
  POST /api/mic/start       → Start server-side mic recording
  POST /api/mic/stop        → Stop recording + transcribe
  GET  /api/mic/status      → Mic recording status
  POST /api/shutdown        → Shutdown JARVIS (requires token)
"""

import asyncio
import json
import logging
import os
import secrets
import sys
import threading
import time
from pathlib import Path

from core.config import CALLBACK_WAIT, LONG_CALLBACK_WAIT
from core.utils import async_sleep

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.json_fast import dumps as fast_dumps

from flask import Flask, Response, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logger = logging.getLogger("jarvis.web")

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"

app = Flask(__name__, static_folder=str(PUBLIC_DIR), static_url_path="")
CORS(app, origins=[
    "http://localhost:*",
    "http://127.0.0.1:*",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "tauri://localhost",
])

limiter = Limiter(get_remote_address, app=app, default_limits=["60/minute"], storage_uri="memory://")

# ── Globals ──────────────────────────────────────────────────────────────────
jarvis = None
loop = None
camera = None
hand_tracker = None
_tts_cache = {}  # text_hash -> future(bytes)
_tts_cache_lock = threading.Lock()
_ws_server = None  # hardened WSServer instance (8766)

JARVIS_PORT = int(os.environ.get("JARVIS_PORT", 8765))
_auth_token = secrets.token_urlsafe(32)

# ── Auth Helper ──────────────────────────────────────────────────────────────
def _check_auth():
    """Require auth token on mutating endpoints. Pass via Authorization header or ?token= query."""
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        token = request.args.get("token", "")
    if not _auth_token or token == _auth_token:
        return None
    return jsonify({"ok": False, "error": "Unauthorized"}), 401


@app.before_request
def _auth_middleware():
    """Protect mutating endpoints (POST/DELETE) — skip health, status, static, SSE."""
    if request.method not in ("POST", "DELETE"):
        return None
    # Skip auth for SSE/streaming (browser can't send headers on EventSource)
    if request.path in ("/api/telemetry/stream",):
        return None
    return _check_auth()


@app.after_request
def _security_headers(resp):
    """Hardening headers: CSP + nosniff + framing + referrer policy."""
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' ws://127.0.0.1:8766; "
        "media-src 'self' blob:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'",
    )
    return resp


def init_jarvis():
    """Initialize JarvisMKX and start event loop in a background thread."""
    global jarvis, loop
    from core.jarvis import JarvisMKX
    from python.tracing import init_tracing

    init_tracing()

    jarvis = JarvisMKX()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Run the event loop in a background thread
    def _run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    t = threading.Thread(target=_run_loop, daemon=True)
    t.start()
    logger.info("JarvisMKX + event loop initialized")

    # Warmup (provider clients, system prompt, memory) is deferred to the
    # first request via JarvisMKX._ensure_started() — faster boot.
    logger.info("Startup warmup deferred until first request")


def get_camera():
    """Lazy-init camera."""
    global camera, hand_tracker
    if camera is None:
        try:
            from vision.camera import Camera
            camera = Camera(camera_id=0, width=640, height=480, max_fps=15)
            camera.start()
        except Exception as e:
            logger.warning("Camera init failed: %s", e)
            camera = None
    return camera


# ── Auth Token (for frontend) ────────────────────────────────────────────────
@app.route("/api/auth/token")
def api_auth_token():
    """Return the current auth token (local-only desktop app)."""
    return jsonify({"ok": True, "token": _auth_token})


# ── Static Files ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(str(PUBLIC_DIR), "index.html")


# ── Health Check (async, cached — never blocks the HUD) ─────────────────────
_health_cache = {
    "checked_at": 0.0,
    "report": "pending",
    "checks": [],
    "running": False,
}
_health_lock = threading.Lock()
_HEALTH_TTL = 30.0


def _health_worker():
    """Run all checks once in a background thread and cache the result."""
    from core.health import format_health_report, run_all_checks
    try:
        checks = run_all_checks()
        with _health_lock:
            _health_cache["checked_at"] = time.time()
            _health_cache["report"] = format_health_report(checks)
            _health_cache["checks"] = [
                {"name": c.name, "ok": c.ok, "message": c.message}
                for c in checks
            ]
            _health_cache["running"] = False
    except Exception as e:
        with _health_lock:
            _health_cache["checked_at"] = time.time()
            _health_cache["report"] = f"Health check failed: {e}"
            _health_cache["checks"] = []
            _health_cache["running"] = False


def _ensure_health_refresh():
    """Spawn a worker if cache is stale and no worker is running."""
    with _health_lock:
        if _health_cache["running"]:
            return
        if time.time() - _health_cache["checked_at"] < _HEALTH_TTL:
            return
        _health_cache["running"] = True
    t = threading.Thread(target=_health_worker, daemon=True)
    t.start()


@app.route("/api/health")
def api_health():
    _ensure_health_refresh()
    with _health_lock:
        return jsonify({
            "ok": True,
            "checked_at": _health_cache["checked_at"],
            "pending": _health_cache["running"] or _health_cache["checked_at"] == 0.0,
            "report": _health_cache["report"],
            "checks": _health_cache["checks"],
        })


# ── System Status ────────────────────────────────────────────────────────────
@app.route("/api/status")
def api_status():
    try:
        import psutil
        status = jarvis.get_status() if jarvis else {}
        from core.resource_governor import get_governor
        gov = get_governor()
        return jsonify({
            "ok": True,
            "jarvis": status,
            "system": {
                "cpu_percent": psutil.cpu_percent(interval=None),
                "ram_percent": psutil.virtual_memory().percent,
                "ram_used_gb": round(psutil.virtual_memory().used / (1024**3), 1),
                "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
            },
            "governor": gov.status,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── System Telemetry (for HUD) ──────────────────────────────────────────────
@app.route("/api/system")
def api_system():
    """Real-time system telemetry: CPU, RAM, GPU, VRAM, temperature."""
    try:
        from python.telemetry import get_system_stats
        return jsonify(get_system_stats())
    except Exception:
        return jsonify({
            "cpu": 0, "ram": 0, "gpu": 0, "vram": 0,
            "temperature": 0, "disk": 0, "battery": "N/A", "network": 0,
        })


# ── Vision Status ────────────────────────────────────────────────────────────
@app.route("/api/vision")
def api_vision():
    """Return vision/camera status and detected objects."""
    cam = get_camera()
    if cam is None:
        return jsonify({"active": False, "resolution": "N/A", "fps": 0, "objects": []})

    return jsonify({
        "active": True,
        "resolution": f"{cam.resolution[0]}x{cam.resolution[1]}",
        "fps": cam.fps,
        "objects": [],
    })


# ── Speech-to-Text ───────────────────────────────────────────────────────────
@app.route("/api/stt", methods=["POST"])
@limiter.limit("30/minute")
def api_stt():
    audio_bytes = request.get_data()
    if not audio_bytes:
        return jsonify({"ok": False, "error": "No audio data"}), 400

    if not jarvis:
        return jsonify({"ok": False, "error": "Jarvis not initialized"}), 503

    try:
        # Reuse Jarvis's STT instance (already configured)
        future = asyncio.run_coroutine_threadsafe(
            jarvis.stt.transcribe(audio_bytes), loop
        )
        text = future.result(timeout=15)
        return jsonify({"ok": True, "text": text or ""})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Camera Stream ────────────────────────────────────────────────────────────
def generate_mjpeg():
    """Yield MJPEG frames from camera."""
    cam = get_camera()
    if cam is None:
        return

    while True:
        frame = cam.read()
        if frame is None:
            async_sleep(0.05)  # replaced with SERVER_POLL_INTERVAL
            continue

        try:
            import cv2
            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buffer.tobytes()
                + b"\r\n"
            )
        except Exception:
            async_sleep(CALLBACK_WAIT)  # replaced with CALLBACK_WAIT


@app.route("/api/camera/stream")
def api_camera_stream():
    return Response(
        generate_mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# ── Chat ─────────────────────────────────────────────────────────────────────
@app.route("/api/chat", methods=["POST"])
@limiter.limit("30/minute")
def api_chat():
    """Send a message and get AI response."""
    data = request.get_json(force=True)
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"ok": False, "error": "No text"}), 400

    if not jarvis:
        return jsonify({"ok": False, "error": "Jarvis not initialized"}), 503

    try:
        future = asyncio.run_coroutine_threadsafe(jarvis.process_text(text), loop)
        response = future.result(timeout=30)
        return jsonify({"ok": True, "response": response})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/chat/stream", methods=["POST"])
@limiter.limit("20/minute")
def api_chat_stream():
    """Full streaming pipeline: intent → text tokens → TTS chunks → done.
    Tokens and audio flow as they're generated via a thread-safe queue."""
    data = request.get_json(force=True)
    text = data.get("text", "").strip()
    if not text or not jarvis:
        return jsonify({"ok": False, "error": "No text or not initialized"}), 400

    import base64
    import queue

    def generate():
        q = queue.Queue()

        async def _produce():
            try:
                async for chunk_type, chunk_data in jarvis.process_text_streaming(text):
                    if chunk_type == "tts_chunk":
                        q.put((chunk_type, base64.b64encode(chunk_data).decode()))
                    else:
                        q.put((chunk_type, chunk_data))
            except Exception as e:
                q.put(("error", str(e)))
            finally:
                q.put(None)  # sentinel

        asyncio.run_coroutine_threadsafe(_produce(), loop)

        while True:
            item = q.get(timeout=60)
            if item is None:
                break
            chunk_type, chunk_data = item
            if chunk_type == "text":
                yield f"data: {fast_dumps({'type': 'text', 'token': chunk_data})}\n\n"
            elif chunk_type == "tts_chunk":
                yield f"data: {fast_dumps({'type': 'tts_chunk', 'audio': chunk_data})}\n\n"
            elif chunk_type == "timing":
                yield f"data: {fast_dumps({'type': 'timing', 'timing': chunk_data})}\n\n"
            elif chunk_type == "done":
                yield f"data: {fast_dumps({'type': 'done', 'text': chunk_data})}\n\n"
            elif chunk_type == "error":
                yield f"data: {fast_dumps({'type': 'error', 'error': chunk_data})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _start_tts_prefetch(text: str):
    """Start TTS generation in background so it's ready when browser requests it."""
    key = hash(text)
    with _tts_cache_lock:
        if key in _tts_cache:
            return  # already fetching
    future = asyncio.run_coroutine_threadsafe(jarvis.tts.synthesize(text), loop)
    with _tts_cache_lock:
        _tts_cache[key] = future


@app.route("/api/chat/history")
def api_chat_history():
    """Get recent chat history."""
    if not jarvis:
        return jsonify({"ok": True, "messages": []})

    try:
        messages = jarvis.context.get_messages(max_turns=50)
        return jsonify({"ok": True, "messages": messages})
    except Exception:
        return jsonify({"ok": True, "messages": []})


# ── TTS Interrupt ─────────────────────────────────────────────────────────────
@app.route("/api/tts/stop", methods=["POST"])
def api_tts_stop():
    """Interrupt active TTS synthesis."""
    if jarvis and hasattr(jarvis, "tts"):
        jarvis.tts.stop()
        return jsonify({"ok": True, "message": "Speech synthesis interrupted"})
    return jsonify({"ok": False, "error": "TTS not active"}), 400


# ── Screen Vision Analysis ───────────────────────────────────────────────────
@app.route("/api/screen/analyze", methods=["POST"])
@limiter.limit("10/minute")
def api_screen_analyze():
    """Analyze current screen using multimodal vision."""
    data = request.get_json(force=True) if request.is_json else {}
    prompt = data.get("prompt", "Analyze what is on the screen")
    try:
        from actions.screen_capture import analyze_screen
        api_key = jarvis.config.api_keys.get("gemini", "") if jarvis else ""
        result = analyze_screen(prompt=prompt, api_key=api_key)
        return jsonify({"ok": True, "analysis": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Desktop Automation ───────────────────────────────────────────────────────
@app.route("/api/desktop/action", methods=["POST"])
@limiter.limit("30/minute")
def api_desktop_action():
    """Execute a desktop GUI control action."""
    data = request.get_json(force=True)
    action = data.get("action", "")
    params = data.get("parameters", {})
    try:
        from actions.desktop_automation import execute_desktop_action
        res = execute_desktop_action(action, params)
        return jsonify({"ok": True, "result": res})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Vector Memory Search ─────────────────────────────────────────────────────
@app.route("/api/memory/search", methods=["GET", "POST"])
def api_memory_search():
    """Search vector memory semantically."""
    data = request.get_json(force=True) if request.is_json else {}
    query = data.get("query") or request.args.get("query", "")
    try:
        from memory.vector_store import VectorMemoryStore
        vs = VectorMemoryStore()
        matches = vs.search_similar(query, top_k=5)
        return jsonify({"ok": True, "matches": matches})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Shutdown ─────────────────────────────────────────────────────────────────
_SHUTDOWN_TOKEN = os.environ.get("JARVIS_SHUTDOWN_TOKEN", "")

@app.route("/api/shutdown", methods=["POST"])
@limiter.limit("5/minute")
def api_shutdown():
    """Shutdown JARVIS gracefully."""
    if _SHUTDOWN_TOKEN:
        data = request.get_json(force=True) or {}
        token = data.get("token", "")
        if token != _SHUTDOWN_TOKEN:
            return jsonify({"ok": False, "error": "Invalid shutdown token"}), 403
    if jarvis:
        jarvis.shutdown()
    return jsonify({"ok": True, "message": "JARVIS shutdown complete"})


# ── Server-Side Mic Recording ────────────────────────────────────────────────
_mic_recording = {"active": False, "buffer": [], "thread": None}


@app.route("/api/mic/start", methods=["POST"])
@limiter.limit("10/minute")
def api_mic_start():
    """Start recording audio from the default mic (Python-side)."""
    # Check if STT is available
    if not jarvis or not jarvis.stt:
        return jsonify({"ok": False, "error": "STT not available."})

    if _mic_recording["active"]:
        return jsonify({"ok": True, "message": "Already recording"})

    _mic_recording["active"] = True
    _mic_recording["buffer"] = []

    def record_thread():
        try:
            import sounddevice as sd

            sample_rate = 16000
            chunk_size = 4096

            def audio_callback(indata, frames, time_info, status):
                if _mic_recording["active"]:
                    _mic_recording["buffer"].append(indata.copy())

            with sd.InputStream(
                channels=1,
                samplerate=sample_rate,
                blocksize=chunk_size,
                callback=audio_callback,
            ):
                while _mic_recording["active"]:
                    async_sleep(CALLBACK_WAIT)  # replaced with CALLBACK_WAIT
        except Exception as e:
            logger.error("Mic recording error: %s", e)
            _mic_recording["active"] = False

    t = threading.Thread(target=record_thread, daemon=True)
    t.start()
    _mic_recording["thread"] = t

    return jsonify({"ok": True, "message": "Recording started"})


@app.route("/api/mic/stop", methods=["POST"])
def api_mic_stop():
    """Stop recording and transcribe + process the audio."""
    if not _mic_recording["active"]:
        return jsonify({"ok": True, "text": "", "response": ""})

    _mic_recording["active"] = False
    async_sleep(LONG_CALLBACK_WAIT)  # replaced with LONG_CALLBACK_WAIT  # Let the callback finish

    buffer = _mic_recording["buffer"]
    _mic_recording["buffer"] = []

    if not buffer:
        return jsonify({"ok": True, "text": "(no audio captured)", "response": ""})

    try:
        import numpy as np

        audio_data = np.concatenate(buffer)
        audio_bytes = (audio_data * 32767).astype(np.int16).tobytes()

        # Transcribe
        future = asyncio.run_coroutine_threadsafe(
            jarvis.stt.transcribe(audio_bytes), loop
        )
        text = future.result(timeout=15)

        if not text or not text.strip():
            return jsonify({"ok": True, "text": "(no speech detected)", "response": ""})

        # Process through LLM
        future2 = asyncio.run_coroutine_threadsafe(
            jarvis.process_text(text), loop
        )
        response = future2.result(timeout=30)

        return jsonify({"ok": True, "text": text, "response": response})
    except Exception as e:
        logger.error("Mic stop error: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/mic/status")
def api_mic_status():
    """Check if mic is currently recording."""
    return jsonify({"ok": True, "recording": _mic_recording["active"]})


# ── Text-to-Speech ───────────────────────────────────────────────────────────
_tts_cache_cleanup_interval = 60.0
_tts_cache_last_cleanup = time.time()

@app.route("/api/tts", methods=["POST"])
@limiter.limit("30/minute")
def api_tts():
    """Convert text to speech. Uses prefetched audio if available (near-instant)."""
    data = request.get_json(force=True)
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"ok": False, "error": "No text"}), 400

    if not jarvis or not jarvis.tts:
        return jsonify({"ok": False, "error": "TTS not available"}), 503

    try:
        # Periodic cleanup of stale TTS cache entries
        global _tts_cache_last_cleanup
        if time.time() - _tts_cache_last_cleanup > _tts_cache_cleanup_interval:
            with _tts_cache_lock:
                _tts_cache_last_cleanup = time.time()
                _tts_cache.clear()

        # Check if TTS was prefetched (from chat stream)
        key = hash(text)
        audio_bytes = None
        with _tts_cache_lock:
            future = _tts_cache.pop(key, None)
        if future:
            audio_bytes = future.result(timeout=15)

        # Fallback: generate now
        if not audio_bytes:
            future = asyncio.run_coroutine_threadsafe(
                jarvis.tts.synthesize(text), loop
            )
            audio_bytes = future.result(timeout=15)

        if not audio_bytes:
            return jsonify({"ok": False, "error": "TTS returned no audio"}), 500
        return Response(audio_bytes, mimetype="audio/mpeg")
    except Exception as e:
        logger.error("TTS error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/tts/stream", methods=["POST"])
@limiter.limit("20/minute")
def api_tts_stream():
    """Stream TTS as sentence-level WAV chunks via SSE.
    Each sentence is generated with Piper independently, sent as base64.
    Yields chunks incrementally (does NOT wait for all sentences)."""
    data = request.get_json(force=True)
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"ok": False, "error": "No text"}), 400
    if not jarvis or not jarvis.tts:
        return jsonify({"ok": False, "error": "TTS not available"}), 503

    import base64
    import queue as _queue

    def generate():
        q = _queue.Queue()

        async def _produce():
            try:
                async for wav_chunk in jarvis.tts.synthesize_streaming(text):
                    q.put(("chunk", base64.b64encode(wav_chunk).decode()))
            except Exception as e:
                q.put(("error", str(e)))
            finally:
                q.put(None)

        asyncio.run_coroutine_threadsafe(_produce(), loop)

        while True:
            item = q.get(timeout=30)
            if item is None:
                break
            if item[0] == "chunk":
                yield f"data: {fast_dumps({'type': 'tts_chunk', 'audio': item[1]})}\n\n"
            elif item[0] == "error":
                yield f"data: {fast_dumps({'type': 'tts_error', 'error': item[1]})}\n\n"

        yield f"data: {fast_dumps({'type': 'tts_done', 'audio': ''})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Performance Governor ─────────────────────────────────────────────────────
_performance_mode = "balanced"  # eco | balanced | performance

_PERF_INTERVALS = {"eco": 2.0, "balanced": 1.0, "performance": 0.5}
_PERF_TTS = {"eco": False, "balanced": True, "performance": True}
_PERF_CAMERA_FPS = {"eco": 1, "balanced": 2, "performance": 5}

# Single-producer telemetry: one background thread collects, SSE clients read snapshot
_telemetry_snapshot = {
    "cpu": 0, "ram": 0, "gpu": 0, "vram": 0,
    "temperature": 0, "disk": 0, "battery": "N/A", "network": 0,
    "performance_mode": "balanced",
}
_telemetry_event = threading.Event()

def _telemetry_producer():
    """Background thread: collect system stats once per interval, store snapshot."""
    global _telemetry_snapshot
    try:
        from python.telemetry import get_system_stats
    except Exception:
        get_system_stats = None

    while True:
        interval = _PERF_INTERVALS.get(_performance_mode, 1.0)
        try:
            data = get_system_stats() if get_system_stats else {
                "cpu": 0, "ram": 0, "gpu": 0, "vram": 0,
                "temperature": 0, "disk": 0, "battery": "N/A", "network": 0,
            }
            data["performance_mode"] = _performance_mode
            _telemetry_snapshot = data
        except Exception:
            _telemetry_snapshot = {
                "error": "telemetry unavailable",
                "performance_mode": _performance_mode,
            }
        _telemetry_event.set()
        _telemetry_event.clear()
        # Mirror the snapshot to WebSocket clients (thread-safe publish)
        global _ws_server
        if _ws_server is not None:
            _ws_server.publish("telemetry", payload=_telemetry_snapshot)
        time.sleep(interval)

# Telemetry producer thread is started in run_server() (not at import time)
# to avoid side effects when this module is imported by other code.
def _start_telemetry():
    t = threading.Thread(target=_telemetry_producer, daemon=True)
    t.start()

@app.route("/api/performance", methods=["GET", "POST"])
def api_performance():
    """Get or set performance mode."""
    global _performance_mode
    if request.method == "POST":
        data = request.get_json(force=True)
        mode = data.get("mode", "balanced")
        if mode in _PERF_INTERVALS:
            _performance_mode = mode
            logger.info("Performance mode → %s", mode)
            return jsonify({"ok": True, "mode": mode,
                            "telemetry_interval": _PERF_INTERVALS[mode],
                            "tts_enabled": _PERF_TTS[mode],
                            "camera_fps": _PERF_CAMERA_FPS[mode]})
        return jsonify({"ok": False, "error": f"Invalid mode: {mode}"}), 400
    return jsonify({"ok": True, "mode": _performance_mode,
                    "telemetry_interval": _PERF_INTERVALS[_performance_mode],
                    "tts_enabled": _PERF_TTS[_performance_mode],
                    "camera_fps": _PERF_CAMERA_FPS[_performance_mode]})


# ── SSE Telemetry Stream ────────────────────────────────────────────────────
@app.route("/api/telemetry/stream")
def api_telemetry_stream():
    """Server-Sent Events stream — reads from shared snapshot (single producer)."""
    def generate():
        while True:
            # Wait for next producer tick (max 500ms to avoid stale connections)
            _telemetry_event.wait(timeout=0.5)
            yield f"data: {fast_dumps(_telemetry_snapshot)}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ── OpenTelemetry Traces ──────────────────────────────────────────────────
@app.route("/api/traces")
def api_traces():
    """Return recent OTel span traces for latency debugging."""
    from python.tracing import get_trace_history
    limit = request.args.get("limit", 50, type=int)
    return jsonify({"ok": True, "traces": get_trace_history(limit=limit)})


# ── Audit & Replay ────────────────────────────────────────────────────────
@app.route("/api/audit/recent")
def api_audit_recent():
    """Recent decision traces (newest first)."""
    from core.event_store import get_event_store
    limit = request.args.get("limit", 20, type=int)
    return jsonify({"ok": True, "traces": get_event_store().recent_traces(limit=limit)})


@app.route("/api/audit/task/<trace_id>")
def api_audit_task(trace_id):
    """Full event timeline for one trace."""
    from core.event_store import get_event_store
    events = get_event_store().query(trace_id=trace_id, limit=500)
    return jsonify({"ok": True, "trace_id": trace_id, "events": [
        {"name": e.name, "data": e.data, "source": e.source, "timestamp": e.timestamp}
        for e in events
    ]})


@app.route("/api/audit/stats")
def api_audit_stats():
    """Aggregate stats across recent traces."""
    from core.event_store import get_event_store
    from security.audit import get_audit_log
    store = get_event_store()
    recent = store.recent_traces(limit=100)
    stats = {"trace_count": len(recent)}
    for evt_name in ("request.received", "task.completed", "task.failed", "tool.executed", "intent.classified"):
        try:
            stats[evt_name] = len(store.query(name=evt_name, limit=100000))
        except Exception:
            stats[evt_name] = 0
    try:
        stats["audit"] = get_audit_log().get_stats()
    except Exception:
        stats["audit"] = {}
    return jsonify({"ok": True, "stats": stats})


@app.route("/api/audit/replay/<trace_id>")
def api_audit_replay(trace_id):
    """Replay engine: chronological timeline for one trace."""
    from core.replay_engine import ReplayEngine
    timeline = ReplayEngine().replay(trace_id)
    return jsonify({"ok": True, "trace_id": trace_id, "timeline": timeline})


@app.route("/api/audit/failure/<trace_id>")
def api_audit_failure(trace_id):
    """Failure analyzer: root-cause attribution for a failed trace."""
    from core.failure_analyzer import FailureAnalyzer
    analysis = FailureAnalyzer().analyze(trace_id)
    return jsonify({"ok": True, **analysis})


# ── Server ───────────────────────────────────────────────────────────────────
def run_server(port=None):
    """Start the web server."""
    port = port or JARVIS_PORT

    init_jarvis()
    _start_telemetry()

    try:
        from api.ws_server import start_ws_server
        global _ws_server
        _ws_server = start_ws_server(host="127.0.0.1", port=8766, auth_token=_auth_token)
        logger.info("WebSocket server started on ws://127.0.0.1:8766 (auth required)")
    except Exception as e:
        logger.warning("WebSocket server failed to start: %s", e)

    print("\nJARVIS MK-X — Web Dashboard")
    print(f"http://localhost:{port}")
    print("Press Ctrl+C to stop\n")

    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    run_server()
