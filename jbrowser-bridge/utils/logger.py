import json
import logging
import os
import threading
from datetime import date
from logging.handlers import RotatingFileHandler

# Canonical per-installation log directory (mirrors the bridge-token precedent).
_LOG_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "JARVIS",
    "logs",
)
_LOG_DATE_FMT = "%Y-%m-%d"

# Levels we emit in the file (everything that logs at INFO or above).
_LOG_FILE_LEVEL = logging.INFO

# Rotates the per-day file; keeps one extra day's file around for cross-day
# debugging. A 64KB cap keeps the file trivial on disk; the bridge serves a
# capped tail anyway.
_LOG_ROTATION_BYTES = 64 * 1024

# Guard: init_log_dir() writes the dir before the first request.
_init_lock = threading.Lock()


def init_log_dir() -> None:
    """Create the log directory lazily (best-effort; no-op if it exists)."""
    with _init_lock:
        try:
            os.makedirs(_LOG_DIR, exist_ok=True)
        except OSError:
            pass


def _log_path() -> str:
    return os.path.join(_LOG_DIR, f"bridge-{date.today().strftime(_LOG_DATE_FMT)}.log")


def _structured_handler(record: logging.LogRecord) -> str:
    """Emit the record plus a trailing structured JSON block for the panel.

    Each line: ``HH:MM:SS.mmm | LEVEL      | name | message | {"detail": {...}}``.
    The ``details`` string is treated as structured when it starts with ``{``
    and ends with ``}``; the parser splits on the last `` | `` so a message
    that itself contains `` | `` is not confused.
    """
    detail = getattr(record, "detail", None)
    if detail is None:
        return record.getMessage()
    try:
        return f"{record.getMessage()} | {json.dumps(detail, ensure_ascii=False)}"
    except (TypeError, ValueError):
        return record.getMessage()


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return _structured_handler(record)


def get_bridge_logger() -> logging.Logger:
    """Return the bridge logger with a rotating file handler attached.

    The existing stdout StreamHandler (and basicConfig) are left untouched;
    this only *adds* a file sink for the unified log UI.
    """
    logger = logging.getLogger("jbrowser-bridge")
    logger.setLevel(logging.DEBUG)  # let handlers decide what they write
    for h in logger.handlers:
        if isinstance(h, RotatingFileHandler) or h.baseFilename.startswith(
            os.path.abspath(_LOG_DIR)
        ):
            return logger

    handler = RotatingFileHandler(
        _log_path(),
        maxBytes=_LOG_ROTATION_BYTES,
        backupCount=1,
        encoding="utf-8",
    )
    handler.setLevel(_LOG_FILE_LEVEL)
    handler.setFormatter(StructuredFormatter())
    logger.addHandler(handler)
    return logger


def log_detail(
    level: int,
    source: str,
    message: str,
    detail: dict | None = None,
) -> None:
    """Log an event that the UI panel needs structured metadata for.

    The file line carries a trailing JSON block (``detail``) that
    ``_read_log_entries`` parses into ``source`` / ``tabId`` /
    ``duration_ms``; the renderer renders the message and collapses detail.
    """
    record = logging.LogRecord(
        name="jbrowser-bridge",
        level=level,
        pathname="",
        lineno=0,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.detail = detail
    logger = logging.getLogger("jbrowser-bridge")
    logger.log(level, record.getMessage(), extra={"detail": detail})
