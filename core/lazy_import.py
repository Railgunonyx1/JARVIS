"""Lazy Loader — defer heavy imports until first use."""

import importlib
import logging
from typing import Any, Optional

logger = logging.getLogger("jarvis.lazy")


class LazyModule:
    """Wrapper that loads the real module on first attribute access."""

    def __init__(self, name: str, package: Optional[str] = None):
        self._name = name
        self._package = package
        self._module: Any = None

    def _load(self) -> Any:
        if self._module is None:
            logger.debug("Lazy loading module: %s", self._name)
            self._module = importlib.import_module(self._name, self._package)
        return self._module

    def __getattr__(self, item: str) -> Any:
        return getattr(self._load(), item)

    def __call__(self, *args, **kwargs) -> Any:
        return self._load()(*args, **kwargs)

    def __bool__(self) -> bool:
        return self._module is not None


# Heavy modules that should be lazy-loaded
cv2 = LazyModule("cv2")
numpy = LazyModule("numpy")
torch = LazyModule("torch")
torchvision = LazyModule("torchvision")
mediapipe = LazyModule("mediapipe")
sounddevice = LazyModule("sounddevice")
soundfile = LazyModule("soundfile")
librosa = LazyModule("librosa")
whisper = LazyModule("whisper")
faster_whisper = LazyModule("faster_whisper")
openwakeword = LazyModule("openwakeword")
onnxruntime = LazyModule("onnxruntime")
deepspeech = LazyModule("deepspeech")
pyaudio = LazyModule("pyaudio")
PIL = LazyModule("PIL")
PIL_Image = LazyModule("PIL.Image")
PIL_ImageDraw = LazyModule("PIL.ImageDraw")
PIL_ImageFont = LazyModule("PIL.ImageFont")
sklearn = LazyModule("sklearn")
scipy = LazyModule("scipy")
pandas = LazyModule("pandas")
matplotlib = LazyModule("matplotlib")
plotly = LazyModule("plotly")
huggingface_hub = LazyModule("huggingface_hub")
transformers = LazyModule("transformers")
sentence_transformers = LazyModule("sentence_transformers")
faiss = LazyModule("faiss")
chromadb = LazyModule("chromadb")
sqlalchemy = LazyModule("sqlalchemy")
redis = LazyModule("redis")
psycopg2 = LazyModule("psycopg2")
pymongo = LazyModule("pymongo")
requests = LazyModule("requests")
httpx = LazyModule("httpx")
aiohttp = LazyModule("aiohttp")
websockets = LazyModule("websockets")
uvicorn = LazyModule("uvicorn")
fastapi = LazyModule("fastapi")
starlette = LazyModule("starlette")
pydantic = LazyModule("pydantic")
pydantic_settings = LazyModule("pydantic_settings")
python_dotenv = LazyModule("python_dotenv")
toml = LazyModule("toml")
yaml = LazyModule("yaml")
jsonschema = LazyModule("jsonschema")
pydub = LazyModule("pydub")
edge_tts = LazyModule("edge_tts")
piper_tts = LazyModule("piper")
deepface = LazyModule("deepface")
insightface = LazyModule("insightface")
dlib = LazyModule("dlib")
face_recognition = LazyModule("face_recognition")
screen_brightness_control = LazyModule("screen_brightness_control")
pynput = LazyModule("pynput")
pyautogui = LazyModule("pyautogui")
mss = LazyModule("mss")
psutil = LazyModule("psutil")
pynvml = LazyModule("pynvml")
wmi = LazyModule("wmi")
pythoncom = LazyModule("pythoncom")
win32api = LazyModule("win32api")
win32con = LazyModule("win32con")
win32gui = LazyModule("win32gui")
win32process = LazyModule("win32process")
win32security = LazyModule("win32security")
ctypes = LazyModule("ctypes")
ctypes_wintypes = LazyModule("ctypes.wintypes")
comtypes = LazyModule("comtypes")
comtypes_client = LazyModule("comtypes.client")

# Pre-created lazy modules for common patterns
_lazy_cache: dict[str, LazyModule] = {}


def get_lazy(name: str) -> Any:
    """Get a lazy module by name (creates if needed)."""
    if name not in _lazy_cache:
        _lazy_cache[name] = LazyModule(name)
    return _lazy_cache[name]


def import_lazy(name: str) -> Any:
    """Eagerly import a lazy module (for when you need the real module)."""
    return get_lazy(name)._load()


def is_loaded(name: str) -> bool:
    """Check if a lazy module has been loaded."""
    if name in _lazy_cache:
        return _lazy_cache[name]._module is not None
    if name in globals():
        return globals()[name]._module is not None
    return False