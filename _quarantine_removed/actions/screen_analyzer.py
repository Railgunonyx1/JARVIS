"""Screen Analyzer — real screen capture, camera, and element finding.

Wraps existing screen_capture.py and adds:
- Camera capture via OpenCV
- AI element finding for screen_click
- Gemini Vision analysis
"""

import io
import logging
import re

logger = logging.getLogger("jarvis.actions.screen_analyzer")

_IMG_MAX_W = 1280
_IMG_MAX_H = 720
_JPEG_Q = 82


def _get_api_key() -> str:
    try:
        from core.config import Config
        return Config.instance().api_keys.get("gemini", "")
    except Exception:
        pass
    import os
    return os.environ.get("GEMINI_API_KEY", "")


def _compress_png(png_bytes: bytes) -> tuple[bytes, str]:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return png_bytes, "image/png"


def _capture_screen_mss() -> tuple[bytes, str] | None:
    try:
        import mss
        import mss.tools
        with mss.mss() as sct:
            monitors = sct.monitors
            target = monitors[1] if len(monitors) > 1 else monitors[0]
            shot = sct.grab(target)
            png = mss.tools.to_png(shot.rgb, shot.size)
        return _compress_png(png)
    except ImportError:
        logger.warning("mss not installed, falling back to PIL")
        return None
    except Exception as e:
        logger.error("mss capture failed: %s", e)
        return None


def _capture_screen_pil() -> tuple[bytes, str] | None:
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return _compress_png(buf.getvalue())
    except Exception as e:
        logger.error("PIL capture failed: %s", e)
        return None


def _capture_camera() -> tuple[bytes, str] | None:
    try:
        import cv2
        from PIL import Image

        backend = cv2.CAP_DSHOW
        cap = cv2.VideoCapture(0, backend)
        if not cap.isOpened():
            cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return None

        for _ in range(10):
            cap.read()
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return None

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q)
        return buf.getvalue(), "image/jpeg"
    except Exception as e:
        logger.error("Camera capture failed: %s", e)
        return None


def _analyze_with_gemini(image_bytes: bytes, mime_type: str, prompt: str, api_key: str) -> str:
    if not api_key:
        logger.info("No Gemini API key — skipping Gemini, trying OpenRouter")
        return _analyze_with_openrouter(image_bytes, mime_type, prompt)

    import google.generativeai as genai

    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    last_error = None

    for model_name in models_to_try:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            system = (
                "You are JARVIS, a vision-enabled AI assistant. "
                "Analyze the provided image with detail and intelligence. "
                "Describe objects, text, UI elements, and context clearly. "
                "Be concise — 2-4 sentences — unless the question demands more detail. "
                "Speak directly to the user ('I can see...', 'You have...'). "
                "Address the user as 'sir'."
            )

            response = model.generate_content([
                system,
                prompt,
                {"mime_type": mime_type, "data": image_bytes}
            ])
            return response.text.strip() if response and response.text else "No analysis produced."
        except Exception as e:
            last_error = e
            logger.warning("Gemini %s failed: %s", model_name, e)
            continue

    logger.info("Gemini all models failed, trying OpenRouter vision fallback")
    return _analyze_with_openrouter(image_bytes, mime_type, prompt)


def _analyze_with_openrouter(image_bytes: bytes, mime_type: str, prompt: str) -> str:
    try:
        from core.config import Config
        cfg = Config.instance()
        api_keys = cfg.api_keys
        api_key = api_keys.get("openrouter", "")
        extra_keys = api_keys.get("openrouter_extra", [])
        all_keys = [k for k in [api_key] + extra_keys if k]
    except Exception:
        all_keys = []

    if not all_keys:
        import os
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if key:
            all_keys = [key]

    if not all_keys:
        return "Screen analysis requires a Gemini or OpenRouter API key."

    import base64 as b64
    b64_data = b64.b64encode(image_bytes).decode("ascii")
    vision_models = [
        "google/gemini-2.5-flash",
        "google/gemini-2.5-flash-lite",
        "google/gemini-3.5-flash",
    ]

    try:
        import openai
    except ImportError:
        return "Screen analysis requires openai package."

    last_error = None
    for i, key in enumerate(all_keys):
        for model in vision_models:
            try:
                client = openai.OpenAI(
                    api_key=key,
                    base_url="https://openrouter.ai/api/v1",
                )
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{mime_type};base64,{b64_data}",
                                    },
                                },
                            ],
                        }
                    ],
                    max_tokens=1024,
                )
                text = response.choices[0].message.content.strip()
                if text:
                    return text
            except Exception as e:
                last_error = e
                logger.warning("OpenRouter %s with key %d failed: %s", model, i, e)
                continue

    return f"Screen analysis failed. Error: {last_error}"


def _find_element_on_screen(description: str, api_key: str) -> tuple[int, int] | None:
    try:
        import mss
        import mss.tools
        import pyautogui

        w, h = pyautogui.size()
        with mss.mss() as sct:
            monitors = sct.monitors
            target = monitors[1] if len(monitors) > 1 else monitors[0]
            shot = sct.grab(target)
            png = mss.tools.to_png(shot.rgb, shot.size)

        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        prompt = (
            f"This is a screenshot of a {w}x{h} pixel screen. "
            f"Locate the UI element described as: '{description}'. "
            f"Reply with ONLY the center coordinates as: x,y "
            f"If the element is not visible, reply: NOT_FOUND"
        )

        response = model.generate_content([
            prompt,
            {"mime_type": "image/png", "data": png}
        ])

        text = (response.text or "").strip()
        if "NOT_FOUND" in text.upper():
            return None

        match = re.search(r"(\d+)\s*,\s*(\d+)", text)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception as e:
        logger.error("Element find failed: %s", e)
    return None


def screen_analyze(params: dict) -> str:
    action = params.get("action", "analyze_screen")
    prompt = params.get("prompt", "Describe everything visible on the screen.")
    api_key = params.get("api_key", "") or _get_api_key()

    if action == "analyze_screen":
        result = _capture_screen_mss()
        if not result:
            result = _capture_screen_pil()
        if not result:
            return "Failed to capture the screen. Please check screen capture permissions."
        image_bytes, mime_type = result
        return _analyze_with_gemini(image_bytes, mime_type, prompt, api_key)

    elif action == "analyze_camera":
        result = _capture_camera()
        if not result:
            return "No camera found or camera capture failed."
        image_bytes, mime_type = result
        return _analyze_with_gemini(image_bytes, mime_type, prompt, api_key)

    elif action == "find_element":
        desc = params.get("description", "")
        if not desc:
            return "No element description provided."
        coords = _find_element_on_screen(desc, api_key)
        return f"Element found at {coords[0]},{coords[1]}" if coords else "Element not found on screen."

    elif action == "click_element":
        desc = params.get("description", "")
        if not desc:
            return "No element description provided."
        coords = _find_element_on_screen(desc, api_key)
        if coords:
            import pyautogui
            pyautogui.click(coords[0], coords[1])
            return f"Clicked '{desc}' at {coords[0]},{coords[1]}"
        return f"Element not found: '{desc}'"

    return f"Unknown screen_analyzer action: {action}"
