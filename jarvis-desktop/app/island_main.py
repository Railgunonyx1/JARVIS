"""JARVIS Desktop Island — entry point for the Dynamic Island overlay.

Top-center morphing pill: idle -> hover peek -> click to expand into the
compact conversation panel. Also the target of the OS autostart entry.
"""

import argparse
import os
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

APP_ID = "jarvis-island"

_DESKTOP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "jarvis-desktop"))
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)

from app.settings import load
from app.ui.island_controller import IslandController
from app.ui.overlay_window import IslandWindow


def _configure_app(app: QApplication) -> None:
    app.setApplicationName(APP_ID)
    app.setDesktopFileName(APP_ID)
    app.setApplicationDisplayName("JARVIS Island")
    app.setQuitOnLastWindowClosed(False)


def _single_instance_guard(lock_path: str | None = None):
    """Take an exclusive lock; return the open handle, or None if held.

    flock is released by the kernel when the process dies, so a stale lock
    file never blocks a fresh start.
    """
    try:
        import fcntl
    except ImportError:
        return open(os.devnull, "w")

    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    path = lock_path or os.path.join(runtime, f"{APP_ID}-{os.getuid()}.lock")
    handle = open(path, "a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def main() -> int:
    app = QApplication(sys.argv)
    _configure_app(app)

    guard = _single_instance_guard()
    if guard is None:
        print("JARVIS Island is already running.", file=sys.stderr)
        return 0

    parser = argparse.ArgumentParser(description="JARVIS Desktop Island")
    parser.add_argument("--no-autostart", action="store_true",
                        help="Do not register the login autostart entry")
    parser.add_argument("--enable-autostart", action="store_true",
                        help="Force-register the login autostart entry")
    args, _ = parser.parse_known_args()

    from app import autostart
    settings = load()
    if args.no_autostart:
        autostart.disable()
    elif args.enable_autostart or settings.get("autostart_enabled", False):
        autostart.enable()

    controller = IslandController()
    island = IslandWindow(controller)
    island.show()

    # Qt's event loop does not dispatch Python signal handlers on its own:
    # app.exec() never returns to the interpreter, so a SIGINT/SIGTERM handler
    # would never run. A running QTimer slot executes Python bytecode, which
    # gives the interpreter a chance to deliver the pending signal.
    signal.signal(signal.SIGINT, lambda *_: island.quit_application())
    signal.signal(signal.SIGTERM, lambda *_: island.quit_application())
    keepalive = QTimer()
    keepalive.timeout.connect(lambda: None)
    keepalive.start(100)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
