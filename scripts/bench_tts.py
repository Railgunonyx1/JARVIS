"""Baseline TTS benchmark — clean-machine rerun of the Kokoro pipeline.

Times the REAL production path (jbrowser-bridge/voice.py) end to end:
model.create -> numpy PCM -> WAV bytes, with the tuned ONNX session.

Reports per-trial rtf (audio duration / wall time), mean/p50/min/max,
plus CPU load sampled DURING synthesis so we can correlate noise.
"""

from __future__ import annotations

import io
import statistics
import sys
import threading
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psutil  # noqa: E402  (already a dependency via voice.py)

sys.path.insert(0, str(ROOT / "jbrowser-bridge"))

import voice as V  # module handle so we can clear caches between trials
from voice import tts, voice_status  # noqa: E402

TEXTS = {
    "short": "Opening it.",  # instant-ack length, ~1s of audio
    "medium": "Here is a summary of the results. Four tests passed and one was skipped because it needs a live browser.",  # ~8s
    "long": "JARVIS has finished scanning the repository. I found twelve functions that can be simplified, three modules with duplicated logic, and one configuration file that is no longer referenced anywhere. I will start with the duplicated logic because it reduces the chance of the two copies drifting apart over time.",  # ~20s
}

TRIALS = 3


class LoadSampler:
    """Sample total CPU% in a background thread; exposes stats over any window."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.samples: list[float] = []
        psutil.cpu_percent(interval=None)  # prime
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.samples.append(psutil.cpu_percent(interval=0.5))

    def stop(self) -> tuple[float, float]:
        self._stop.set()
        self._thread.join(timeout=2)
        if not self.samples:
            return 0.0, 0.0
        return statistics.mean(self.samples), max(self.samples)


def wav_duration(pcm: bytes, rate: int = 24000) -> float:
    with wave.open(io.BytesIO(pcm)) as w:
        return w.getnframes() / w.getframerate()


def main() -> int:
    print("=" * 72)
    print("TTS BASELINE — clean-machine rerun")
    print("=" * 72)

    status = voice_status()
    print(f"engine chain : {status.get('tts_chain')}")
    print(f"threads      : {status.get('kokoro', {}).get('threads')}")

    # ---- warmup (model load + first synthesis excluded from results) ----
    print("\nwarming up (model load + first synthesis)...")
    t0 = time.perf_counter()
    pcm, _mime, engine = tts("Warming up the voice engine.")
    warm_s = time.perf_counter() - t0
    print(f"  warmup: {warm_s:.1f}s  engine={engine}")
    if engine != "kokoro":
        print(f"  WARNING: kokoro did not load; results measure '{engine}' instead")

    # ---- measured runs ----
    results: dict[str, list[dict]] = {k: [] for k in TEXTS}
    sampler = LoadSampler()
    engines: set[str] = set()
    try:
        for name, text in TEXTS.items():
            for i in range(TRIALS):
                V._AUDIO_CACHE.clear()  # force real synthesis every trial
                t = time.perf_counter()
                pcm, _mime, engine = tts(text)
                wall = time.perf_counter() - t
                engines.add(engine)
                dur = wav_duration(pcm)
                rtf = wall / dur
                results[name].append(
                    {"wall": wall, "dur": dur, "rtf": rtf}
                )
                print(
                    f"  {name:6s} trial {i + 1}: {dur:5.2f}s audio in {wall:5.2f}s"
                    f"  -> rtf {rtf:.2f}  ({'FASTER' if rtf < 1 else 'slower'} than realtime)"
                )
    finally:
        avg_load, peak_load = sampler.stop()

    if engines - {"kokoro"}:
        print(f"\nNOTE: non-kokoro engines served some runs: {sorted(engines)}")

    # ---- summary ----
    print("\n" + "=" * 72)
    print(f"CPU load during runs: avg {avg_load:.0f}%  peak {peak_load:.0f}%")
    print("=" * 72)
    print(f"{'text':8s} {'audio':>6s} {'mean rtf':>9s} {'p50':>6s} {'min':>6s} {'max':>6s}")
    overall = []
    for name, rs in results.items():
        rtfs = [r["rtf"] for r in rs]
        overall.extend(rtfs)
        print(
            f"{name:8s} {rs[0]['dur']:5.2f}s {statistics.mean(rtfs):9.2f}"
            f" {statistics.median(rtfs):6.2f} {min(rtfs):6.2f} {max(rtfs):6.2f}"
        )
    print("-" * 72)
    print(
        f"{'ALL':8s} {'':6s} {statistics.mean(overall):9.2f}"
        f" {statistics.median(overall):6.2f} {min(overall):6.2f} {max(overall):6.2f}"
    )

    m = statistics.mean(overall)
    print("\nverdict:", end=" ")
    if m < 0.75:
        print("excellent — comfortably faster than real-time even in the worst runs")
    elif m < 1.0:
        print("real-time capable — conversation pacing holds on this machine")
    elif m < 2.0:
        print("marginal — OK with sentence streaming; consider engine for very long replies")
    else:
        print("still slow — load or config problem, re-check machine state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
