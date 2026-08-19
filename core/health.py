"""Health check system — validates all subsystems at startup."""

import json
import os
import threading
import time
from dataclasses import dataclass

from core.async_utils import safe_execute


@dataclass
class HealthCheck:
    name: str
    ok: bool
    message: str
    details: str | None = None


def check_python() -> HealthCheck:
    import sys
    v = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 10)
    return HealthCheck("Python", ok, f"v{v}", "Need 3.10+" if not ok else None)


def check_ollama() -> HealthCheck:
    """Check Ollama via its HTTP API (fast, no subprocess)."""

    def _check() -> HealthCheck:
        from core.http_pool import get_client

        url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
        client = get_client()
        if client is not None:

            resp = client.get(f"{url}/api/tags", timeout=1.5)
            status = resp.status_code
            text = resp.text
        else:
            import urllib.request
            with urllib.request.urlopen(f"{url}/api/tags", timeout=1.5) as resp:
                status = resp.status
                text = resp.read().decode()
        if status != 200:
            raise ValueError(f"HTTP {status}")
        data = json.loads(text)
        models = data.get("models", [])
        return HealthCheck("Ollama", True, f"{len(models)} models available", url)

    return safe_execute(_check, fallback=HealthCheck("Ollama", False, "Not running"))


def check_piper() -> HealthCheck:
    try:
        import importlib.util
        spec = importlib.util.find_spec("piper")
        if spec:
            return HealthCheck("Piper TTS", True, "Module available")
        return HealthCheck("Piper TTS", False, "Not installed")
    except Exception:
        return HealthCheck("Piper TTS", False, "Not installed")


def check_edge_tts() -> HealthCheck:
    """Check Edge TTS module availability."""
    def _check() -> HealthCheck:
        import importlib.util
        spec = importlib.util.find_spec("edge_tts")
        if spec:
            return HealthCheck("Edge TTS", True, "Module available")
        return HealthCheck("Edge TTS", False, "Not installed")

    return safe_execute(_check, fallback=HealthCheck("Edge TTS", False, "Not installed"))


def check_sounddevice() -> HealthCheck:
    """Check audio I/O via sounddevice."""
    def _check() -> HealthCheck:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devs = [d for d in devices if d["max_input_channels"] > 0]
        output_devs = [d for d in devices if d["max_output_channels"] > 0]
        return HealthCheck(
            "Audio I/O", True,
            f"{len(input_devs)} input, {len(output_devs)} output devices"
        )

    return safe_execute(_check, fallback=HealthCheck("Audio I/O", False, "Not available"))


def check_openWakeWord() -> HealthCheck:
    """Check openWakeWord module availability."""
    def _check() -> HealthCheck:
        import importlib.util
        spec = importlib.util.find_spec("openwakeword")
        if spec:
            return HealthCheck("openWakeWord", True, "Module available")
        return HealthCheck("openWakeWord", False, "Not installed")

    return safe_execute(_check, fallback=HealthCheck("openWakeWord", False, "Not installed"))


def check_faster_whisper() -> HealthCheck:
    """Check faster-whisper module availability."""
    def _check() -> HealthCheck:
        import importlib.util
        spec = importlib.util.find_spec("faster_whisper")
        if spec:
            return HealthCheck("faster-whisper", True, "Module available")
        return HealthCheck("faster-whisper", False, "Not installed")

    return safe_execute(_check, fallback=HealthCheck("faster-whisper", False, "Not installed"))


def check_config() -> HealthCheck:
    from pathlib import Path
    toml_path = Path(__file__).resolve().parent.parent / "config" / "jarvis.toml"
    if toml_path.exists():
        return HealthCheck("Config", True, "jarvis.toml found")
    return HealthCheck("Config", False, "jarvis.toml missing", str(toml_path))


def check_api_keys() -> HealthCheck:
    try:
        from core.api_keys import get_all_api_keys
        all_keys = get_all_api_keys()
        found_keys = [k for k, v in all_keys.items() if v]
        if found_keys:
            return HealthCheck("API Keys", True, f"{len(found_keys)} configured: {', '.join(found_keys)}")
    except Exception:
        pass

    keys = {
        "GROQ_API_KEY": os.environ.get("GROQ_API_KEY", ""),
        "GOOGLE_AI_KEY": os.environ.get("GOOGLE_AI_KEY", ""),
        "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", ""),
    }
    found = [k for k, v in keys.items() if v]

    if found:
        return HealthCheck("API Keys", True, f"{len(found)} configured: {', '.join(found)}")
    return HealthCheck("API Keys", False, "No API keys found (only Ollama available)")


def check_groq_package() -> HealthCheck:
    try:
        import importlib.util
        spec = importlib.util.find_spec("groq")
        if spec:
            return HealthCheck("Groq Package", True, "Installed")
        return HealthCheck("Groq Package", False, "Not installed (LLM fallback will skip Groq)")
    except Exception:
        return HealthCheck("Groq Package", False, "Not installed")


def check_ollama_package() -> HealthCheck:
    try:
        import importlib.util
        spec = importlib.util.find_spec("ollama")
        if spec:
            return HealthCheck("Ollama Package", True, "Installed")
        return HealthCheck("Ollama Package", False, "Not installed (LLM fallback will skip Ollama)")
    except Exception:
        return HealthCheck("Ollama Package", False, "Not installed")


def _run_check_with_timeout(check_fn, timeout=3):
    """Run a single check function with a timeout using a raw thread."""
    import threading
    result = [None]
    exc = [None]

    def _target():
        try:
            result[0] = check_fn()
        except Exception as e:
            exc[0] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        return HealthCheck(check_fn.__name__, False, "Timed out")
    if exc[0] is not None:
        return HealthCheck(check_fn.__name__, False, f"Error: {exc[0]}")
    return result[0] or HealthCheck(check_fn.__name__, False, "No result")


_cache_lock = threading.Lock()
_cache_result: list[HealthCheck] | None = None
_cache_time: float = 0.0
_CACHE_TTL = 300.0  # 5 minutes


def run_all_checks() -> list[HealthCheck]:
    """Run all health checks in parallel with per-check timeouts.

    Results are cached for 5 minutes since most checks (Python version,
    Ollama availability, package presence) rarely change within that window.
    """
    global _cache_result, _cache_time

    now = time.time()
    with _cache_lock:
        if _cache_result is not None and now - _cache_time < _CACHE_TTL:
            return list(_cache_result)

    from concurrent.futures import ThreadPoolExecutor

    checks = [
        check_python,
        check_ollama,
        check_piper,
        check_edge_tts,
        check_sounddevice,
        check_openWakeWord,
        check_faster_whisper,
        check_config,
        check_api_keys,
        check_groq_package,
        check_ollama_package,
    ]

    with ThreadPoolExecutor(max_workers=len(checks)) as pool:
        futures = {pool.submit(_run_check_with_timeout, fn, 5): fn for fn in checks}
        results = []
        for fn in checks:
            future = next(f for f, ffn in futures.items() if ffn is fn)
            results.append(future.result())

    with _cache_lock:
        _cache_result = results
        _cache_time = time.time()
    return list(results)


def force_health_refresh() -> None:
    """Invalidate the health check cache so the next call re-runs all checks."""
    global _cache_result, _cache_time
    with _cache_lock:
        _cache_result = None
        _cache_time = 0.0


def format_health_report(checks: list[HealthCheck]) -> str:
    """Format health checks into a readable report."""
    lines = ["=== JARVIS MK-X Health Report ===\n"]
    for c in checks:
        status = "OK" if c.ok else "FAIL"
        line = f"[{status}] {c.name}: {c.message}"
        if c.details:
            line += f" ({c.details})"
        lines.append(line)

    passed = sum(1 for c in checks if c.ok)
    total = len(checks)
    lines.append(f"\n{passed}/{total} checks passed")
    return "\n".join(lines)
