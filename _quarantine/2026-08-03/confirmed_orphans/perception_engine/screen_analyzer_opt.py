"""Optimized Screen Analyzer — fast screen capture and change detection."""

import time
import math
import hashlib
import logging
import threading
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.perception_engine.screen_analyzer_opt")

try:
    import mss
    import mss.tools
    _HAS_MSS = True
except ImportError:
    _HAS_MSS = False
    logger.info("mss not installed — screen capture will return None")


class ScreenAnalyzerOptimized:
    """Lightweight screen capture with change detection and analysis caching."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_capture: Optional[Dict[str, Any]] = None
        self._last_analysis: Optional[Dict[str, Any]] = None
        self._capture_history: deque = deque(maxlen=10)
        self._captures_count: int = 0
        self._analyses_count: int = 0
        self._cache_hits: int = 0

    def capture_screen(self, region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Dict[str, Any]]:
        """Capture the screen (or a region) and return image bytes with metadata.

        Returns dict with keys: "image" (bytes), "timestamp" (float),
        "size" (tuple[int, int]), "hash" (str). Returns None on failure.
        """
        if not _HAS_MSS:
            logger.warning("mss unavailable, cannot capture screen")
            return None

        try:
            with mss.mss() as sct:
                monitors = sct.monitors
                if region:
                    target = {"left": region[0], "top": region[1],
                              "width": region[2], "height": region[3]}
                else:
                    target = monitors[1] if len(monitors) > 1 else monitors[0]

                shot = sct.grab(target)
                png = mss.tools.to_png(shot.rgb, shot.size)

                img_hash = hashlib.md5(png).hexdigest()
                capture = {
                    "image": png,
                    "timestamp": time.perf_counter(),
                    "size": (shot.width, shot.height),
                    "hash": img_hash,
                }

            with self._lock:
                self._last_capture = capture
                self._capture_history.append(capture)
                self._captures_count += 1

            return capture
        except Exception as e:
            logger.error("Screen capture failed: %s", e)
            return None

    def analyze_screen(self, capture: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Analyze the current screen state.

        Returns dict with keys: "description" (str), "elements" (list),
        "timestamp" (float).
        """
        if capture is None:
            capture = self.capture_screen()

        if capture is None:
            return {"description": "Screen capture unavailable", "elements": [], "timestamp": time.perf_counter()}

        analysis: Dict[str, Any] = {
            "description": f"Screen captured at {capture['size'][0]}x{capture['size'][1]}",
            "elements": [],
            "timestamp": capture["timestamp"],
            "capture_hash": capture.get("hash", ""),
        }

        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(capture["image"])).convert("RGB")
            pixels = list(img.getdata())
            total = len(pixels)
            if total > 0:
                avg_r = sum(p[0] for p in pixels) / total
                avg_g = sum(p[1] for p in pixels) / total
                avg_b = sum(p[2] for p in pixels) / total
                brightness = (avg_r + avg_g + avg_b) / 3.0 / 255.0
                analysis["brightness"] = round(brightness, 4)
                analysis["avg_color"] = (int(avg_r), int(avg_g), int(avg_b))

                edge_count = self._estimate_edges(img)
                analysis["complexity"] = round(min(edge_count / max(total, 1), 1.0), 6)

                analysis["description"] = (
                    f"Screen {capture['size'][0]}x{capture['size'][1]}, "
                    f"brightness {brightness:.0%}, "
                    f"complexity {analysis['complexity']:.4f}"
                )
        except Exception as e:
            logger.debug("Pixel analysis skipped: %s", e)

        with self._lock:
            self._last_analysis = analysis
            self._analyses_count += 1

        return analysis

    def get_change_ratio(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> float:
        """Compare two captures and return a 0–1 change ratio."""
        if prev is None or curr is None:
            return 1.0

        prev_hash = prev.get("hash", "")
        curr_hash = curr.get("hash", "")
        if prev_hash == curr_hash:
            return 0.0

        prev_img = prev.get("image")
        curr_img = curr.get("image")
        if prev_img is None or curr_img is None:
            return 1.0

        try:
            from PIL import Image
            import io
            img1 = Image.open(io.BytesIO(prev_img)).convert("L").resize((64, 64))
            img2 = Image.open(io.BytesIO(curr_img)).convert("L").resize((64, 64))

            px1 = list(img1.getdata())
            px2 = list(img2.getdata())
            total = len(px1)
            if total == 0:
                return 1.0

            diff_sum = sum(abs(a - b) for a, b in zip(px1, px2))
            return min(diff_sum / (total * 255.0), 1.0)
        except Exception as e:
            logger.debug("Change ratio computation failed: %s", e)
            return 1.0

    def should_analyze(self, threshold: float = 0.1) -> bool:
        """Return True if the screen changed significantly since last analysis."""
        with self._lock:
            history = list(self._capture_history)

        if len(history) < 2:
            return True

        prev = history[-2]
        curr = history[-1]
        ratio = self.get_change_ratio(prev, curr)
        return ratio >= threshold

    def get_last_capture(self) -> Optional[Dict[str, Any]]:
        """Return the most recent capture dict."""
        with self._lock:
            return self._last_capture

    def get_last_analysis(self) -> Optional[Dict[str, Any]]:
        """Return the most recent analysis dict."""
        with self._lock:
            return self._last_analysis

    def get_stats(self) -> Dict[str, Any]:
        """Return capture and analysis statistics."""
        with self._lock:
            return {
                "captures": self._captures_count,
                "analyses": self._analyses_count,
                "cache_hits": self._cache_hits,
                "history_size": len(self._capture_history),
                "has_mss": _HAS_MSS,
            }

    @staticmethod
    def _estimate_edges(img: Any) -> int:
        """Estimate edge count using simple pixel-difference heuristic."""
        try:
            w, h = img.size
            if w < 2 or h < 2:
                return 0
            pixels = list(img.getdata())
            edges = 0
            for y in range(h):
                for x in range(w - 1):
                    idx = y * w + x
                    p1 = pixels[idx]
                    p2 = pixels[idx + 1]
                    if abs(p1[0] - p2[0]) + abs(p1[1] - p2[1]) + abs(p1[2] - p2[2]) > 80:
                        edges += 1
            return edges
        except Exception:
            return 0


# ----------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------

_instance: Optional[ScreenAnalyzerOptimized] = None
_instance_lock = threading.Lock()


def get_screen_analyzer_opt() -> ScreenAnalyzerOptimized:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ScreenAnalyzerOptimized()
    return _instance
