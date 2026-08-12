"""JARVIS MK-X — Core Utilities."""

import logging
import logging.handlers
import sys
from pathlib import Path


def get_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def setup_logging(level: str = "INFO", log_dir: str | None = None) -> None:
    log_dir = log_dir or str(get_project_root() / "logs")
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    fh = logging.handlers.RotatingFileHandler(
        log_path / "jarvis.log", maxBytes=5_242_880, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    ch = logging.StreamHandler(sys.stderr)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    for noisy in ("httpx", "urllib3", "chromadb", "pypff", "PIL", "sounddevice"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def async_sleep(seconds: float) -> None:
    """Non-blocking sleep for async contexts."""
    import asyncio
    await asyncio.sleep(seconds)


def sleep(seconds: float) -> None:
    """Blocking sleep — use only in synchronous contexts."""
    import time
    time.sleep(seconds)
