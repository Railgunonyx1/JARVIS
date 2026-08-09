"""Screen Capture & Multimodal Vision Analysis module for JARVIS MK-X.

Supports full desktop, multi-monitor, and active focused window cropping.
"""

import io
import ctypes
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("jarvis.actions.screen_capture")


def _get_active_window_bbox() -> Optional[Tuple[int, int, int, int]]:
    """Get (left, top, right, bottom) bbox of the currently focused active window on Windows."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        rect = ctypes.wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
            if right > left and bottom > top:
                return (left, top, right, bottom)
    except Exception as e:
        logger.debug("Failed to get active window rect: %s", e)
    return None


def capture_screen(
    output_path: Optional[Path] = None,
    active_window_only: bool = False,
    all_screens: bool = True
) -> Optional[bytes]:
    """Capture screen (full screen, all monitors, or active focused window) and return PNG bytes."""
    try:
        from PIL import ImageGrab

        bbox = None
        if active_window_only:
            bbox = _get_active_window_bbox()

        if bbox:
            img = ImageGrab.grab(bbox=bbox, all_screens=all_screens)
        else:
            img = ImageGrab.grab(all_screens=all_screens)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(png_bytes)
            logger.info("Screenshot saved to %s", output_path)

        return png_bytes
    except Exception as e:
        logger.error("Screen capture failed: %s", e)
        return None


def analyze_screen(
    prompt: str = "Describe what is currently visible on the screen, highlighting any code, errors, or key windows.",
    api_key: str = "",
    active_window_only: bool = False
) -> str:
    """Capture screen (or active window) and run multimodal vision analysis using Gemini."""
    png_bytes = capture_screen(active_window_only=active_window_only)
    if not png_bytes:
        return "Failed to capture the screen."

    if not api_key:
        from core.config import Config
        cfg = Config.instance()
        api_key = cfg.api_keys.get("gemini", "")

    if not api_key:
        return "Gemini API key is required for visual screen analysis."

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        image_part = {
            "mime_type": "image/png",
            "data": png_bytes
        }

        mode_str = "active focused window" if active_window_only else "computer screen"
        system_prompt = (
            f"You are JARVIS MK-X Vision Engine. The user has requested an analysis of their {mode_str}. "
            "Be direct, concise, and highlight relevant code, terminal errors, active windows, or key details."
        )

        response = model.generate_content([system_prompt, prompt, image_part])
        return response.text.strip() if response and response.text else "No analysis produced."
    except Exception as e:
        logger.error("Multimodal screen analysis failed: %s", e)
        return f"Screen analysis error: {e}"
