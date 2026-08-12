"""Voice Benchmark — Measures TTS synthesis time, STT transcription time, voice pipeline latency."""
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import asyncio
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@dataclass
class VoiceBenchmarkResult:
    tts_synthesis_ms: list[float] = field(default_factory=list)
    tts_first_chunk_ms: list[float] = field(default_factory=list)
    tts_warmup_ms: float = 0.0
    tts_precache_ms: float = 0.0
    stt_transcription_ms: list[float] = field(default_factory=list)
    vad_detection_ms: list[float] = field(default_factory=list)
    full_voice_roundtrip_ms: list[float] = field(default_factory=list)
    tts_backend: str = "unknown"
    stt_backend: str = "unknown"
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tts_avg_synthesis_ms": round(statistics.mean(self.tts_synthesis_ms), 1) if self.tts_synthesis_ms else 0,
            "tts_avg_first_chunk_ms": round(statistics.mean(self.tts_first_chunk_ms), 1) if self.tts_first_chunk_ms else 0,
            "tts_warmup_ms": round(self.tts_warmup_ms, 1),
            "tts_precache_ms": round(self.tts_precache_ms, 1),
            "stt_avg_transcription_ms": round(statistics.mean(self.stt_transcription_ms), 1) if self.stt_transcription_ms else 0,
            "vad_avg_detection_ms": round(statistics.mean(self.vad_detection_ms), 1) if self.vad_detection_ms else 0,
            "full_roundtrip_avg_ms": round(statistics.mean(self.full_voice_roundtrip_ms), 1) if self.full_voice_roundtrip_ms else 0,
            "tts_backend": self.tts_backend,
            "stt_backend": self.stt_backend,
            "errors": self.errors,
        }


TTS_TEST_PHRASES = [
    "Hello, how can I help you today?",
    "The weather is sunny with a high of seventy five degrees.",
    "I found three search results for your query.",
    "Your meeting with John is scheduled for 2 PM tomorrow.",
    "I've opened Chrome and navigated to the search page.",
]


def run_voice_benchmark(rounds: int = 1) -> VoiceBenchmarkResult:
    result = VoiceBenchmarkResult()

    for _ in range(rounds):
        _run_single_voice_benchmark(result)

    return result


def _run_single_voice_benchmark(result: VoiceBenchmarkResult):
    from pipeline.tts import TextToSpeech

    from core.config import Config

    config = Config()
    voice_cfg = config.get_section("voice")

    # 1. TTS Warmup
    tts = TextToSpeech(voice_cfg)
    t0 = time.perf_counter()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(tts.warmup())
        result.tts_warmup_ms = (time.perf_counter() - t0) * 1000
    except Exception as e:
        result.errors.append(f"TTS warmup: {e}")
        result.tts_warmup_ms = (time.perf_counter() - t0) * 1000
    finally:
        try:
            loop.close()
        except Exception:
            pass

    # 2. TTS Synthesis per phrase
    for phrase in TTS_TEST_PHRASES:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            t0 = time.perf_counter()
            first_chunk_time = None
            chunk_count = 0

            async def _synthesize():
                nonlocal first_chunk_time, chunk_count
                async for chunk in tts.synthesize_stream(phrase):
                    if first_chunk_time is None:
                        first_chunk_time = (time.perf_counter() - t0) * 1000
                    chunk_count += 1

            loop.run_until_complete(asyncio.wait_for(_synthesize(), timeout=10))
            total_ms = (time.perf_counter() - t0) * 1000

            if first_chunk_time is not None:
                result.tts_first_chunk_ms.append(first_chunk_time)
            result.tts_synthesis_ms.append(total_ms)
        except Exception as e:
            result.errors.append(f"TTS '{phrase[:30]}...': {e}")
        finally:
            try:
                loop.close()
            except Exception:
                pass

    # 3. TTS precache
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        t0 = time.perf_counter()
        loop.run_until_complete(tts.precache_deterministic())
        result.tts_precache_ms = (time.perf_counter() - t0) * 1000
    except Exception as e:
        result.errors.append(f"TTS precache: {e}")
    finally:
        try:
            loop.close()
        except Exception:
            pass

    # 4. STT benchmark (requires a test audio file or recording)
    try:
        from pipeline.stt import SpeechToText
        stt = SpeechToText()
        result.stt_backend = "groq_whisper" if hasattr(stt, '_groq_client') else "local_whisper"

        # We can't easily test STT without a real audio file
        # Just record that STT was initialized
    except Exception as e:
        result.errors.append(f"STT init: {e}")


def print_voice_result(result: VoiceBenchmarkResult):
    print(f"\n{'=' * 60}")
    print("  VOICE BENCHMARK RESULTS")
    print(f"{'=' * 60}")

    print(f"  TTS Backend: {result.tts_backend}")
    print(f"  STT Backend: {result.stt_backend}")

    if result.tts_warmup_ms:
        print(f"\n  TTS Warmup:        {result.tts_warmup_ms:.0f}ms")

    if result.tts_first_chunk_ms:
        avg_first = statistics.mean(result.tts_first_chunk_ms)
        print(f"\n  TTS First Audio:   {avg_first:.0f}ms (avg)")
        print(f"    Best:           {min(result.tts_first_chunk_ms):.0f}ms")
        print(f"    Worst:          {max(result.tts_first_chunk_ms):.0f}ms")
        print(f"    Samples:        {len(result.tts_first_chunk_ms)}")

    if result.tts_synthesis_ms:
        avg_synth = statistics.mean(result.tts_synthesis_ms)
        print(f"\n  TTS Full Synth:    {avg_synth:.0f}ms (avg)")

    if result.tts_precache_ms:
        print(f"\n  TTS Precache:      {result.tts_precache_ms:.0f}ms")

    if result.stt_transcription_ms:
        avg_stt = statistics.mean(result.stt_transcription_ms)
        print(f"\n  STT Transcription: {avg_stt:.0f}ms (avg)")

    if result.vad_detection_ms:
        avg_vad = statistics.mean(result.vad_detection_ms)
        print(f"\n  VAD Detection:     {avg_vad:.0f}ms (avg)")

    if result.errors:
        print(f"\n  Errors ({len(result.errors)}):")
        for err in result.errors[:5]:
            print(f"    - {err}")

    print(f"{'=' * 60}")
