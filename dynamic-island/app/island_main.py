"""JARVIS Desktop Island — entry point for the Dynamic Island overlay.

Top-center morphing pill: idle -> hover peek -> click to expand into the
compact conversation panel. Also the target of the OS autostart entry.

Autostart is enabled by default on install (the installer writes the entry and
starts the app with `jarvis-desktop-island`). Users can opt out at any time:
  - `jarvis-autostart disable` removes JARVIS's own freedesktop entry, or
  - Settings > "Launch on login" toggle in the desktop app.
"""

import argparse
import logging
import os
import signal
import sys

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

try:
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
except Exception:  # pragma: no cover - Qt availability only
    QLocalServer = None
    QLocalSocket = None

APP_ID = "jarvis-island"

logger = logging.getLogger("jarvis.desktop.island")

from app.settings import load

# Load settings once before the autostart branches touch settings.get().
from app.ui.island_controller import IslandController
from app.ui.overlay_window import IslandWindow

# Executed by the *launcher* (the #!/usr/bin/env python3 wrapper in
# bin/jarvis-desktop-island), not by a double-click in an editor.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
APP_DIR = os.path.join(REPO_ROOT, "dynamic-island")

# Installed layout: bin/jarvis-desktop-island  ->  dynamic-island/app/island_main.py
_INSTALLED_BIN = os.path.join(REPO_ROOT, "bin", "jarvis-desktop-island")
_INSTALLED_ISLAND = os.path.join(REPO_ROOT, "dynamic-island", "app", "island_main.py")

# In-tree (development) layout: dynamic-island/app/island_main.py
_DEV_ISLAND = os.path.join(APP_DIR, "island_main.py")

# Where the installed launcher normally lives.
_INSTALLED_LAUNCHER = os.path.join(REPO_ROOT, "bin", "jarvis-desktop-island")

# The platform default is the installed launcher; fall back to the
# in-tree entry point only when the installed one is absent.
_ENTRY_POINT = _INSTALLED_LAUNCHER
if not os.path.isfile(_INSTALLED_LAUNCHER):
    _ENTRY_POINT = _DEV_ISLAND


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


class _InstanceIpc(QObject):
    """Brings an existing island to front when a second instance launches."""

    def __init__(self, server_name: str, island):
        super().__init__()
        self._island = island
        if QLocalServer is None:
            self._server = None
            return
        self._server = QLocalServer(self)
        QLocalServer.removeServer(server_name)
        self._server.listen(server_name)
        self._server.newConnection.connect(self._on_connection)

    def _on_connection(self):
        server = getattr(self, "_server", None)
        if server is None:
            return
        sock = server.nextPendingConnection()
        if sock is None:
            return
        sock.readyRead.connect(lambda s=sock: self._handle(sock))
        sock.disconnected.connect(sock.deleteLater)

    def _handle(self, sock):
        try:
            data = sock.readAll().data().decode("utf-8", errors="ignore").strip()
        except Exception:
            data = ""
        sock.flush()
        sock.disconnectFromServer()
        if data == "show":
            island = self._island
            if island is not None:
                island.show()
                island.raise_()
                island.activateWindow()


def _ask_running_instance(server_name: str) -> bool:
    if QLocalSocket is None:
        return False
    sock = QLocalSocket()
    sock.connectToServer(server_name)
    if not sock.waitForConnected(300):
        return False
    sock.write(b"show")
    sock.flush()
    sock.waitForBytesWritten(300)
    sock.disconnectFromServer()
    sock.waitForDisconnected(300)
    return True


def _instance_server_name(lock_path: str) -> str:
    # Keep the name stable and filesystem-safe.
    base = os.path.basename(lock_path).replace(".", "-")
    return f"{APP_ID}-{base}-ipc"


def _select_entry_point() -> str:
    """Return the absolute executable that launches the island.

    Installed layout (as delivered by the desktop installer):

      bin/jarvis-desktop-island  ->  dynamic-island/app/island_main.py

    In-tree checkout layout is the fallback, used only when the installed
    binary is not present.
    """
    if os.path.isfile(_INSTALLED_LAUNCHER):
        return _INSTALLED_LAUNCHER
    if os.path.isfile(_INSTALLED_ISLAND):
        return _INSTALLED_ISLAND
    return _DEV_ISLAND


def main() -> int:
    app = QApplication(sys.argv)
    _configure_app(app)

    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    lock_path = os.path.join(runtime, f"{APP_ID}-{os.getuid()}.lock")
    server_name = _instance_server_name(lock_path)
    guard = _single_instance_guard(lock_path)
    if guard is None:
        if _ask_running_instance(server_name):
            return 0
        print("JARVIS Island is already running.", file=sys.stderr)
        return 0

    parser = argparse.ArgumentParser(description="JARVIS Desktop Island")
    parser.add_argument(
        "--no-autostart",
        action="store_true",
        help="Do not register the login autostart entry (default: on)",
    )
    parser.add_argument(
        "--enable-autostart",
        action="store_true",
        help="Force-register the login autostart entry",
    )
    args, _ = parser.parse_known_args()

    from app import autostart

    # Load persistence settings once before the autostart branch touches
    # settings.get(). This removes an undefined-variable NameError at startup.
    settings = load()

    # Enable login autostart by default; the installer does this too, and the
    # user can opt out with Settings > Launch on login or `jarvis-autostart
    # disable`. Explicit opt-out wins.
    if args.no_autostart:
        autostart.disable()
    elif args.enable_autostart or settings.get("autostart_enabled", True):
        autostart.enable()

    controller = IslandController()
    island = IslandWindow(controller)
    island.show()

    ipc = _InstanceIpc(server_name, island)
    app.setProperty("_jarvis_island_ipc", ipc)

    # Qt's event loop does not dispatch Python signal handlers on its own:
    # app.exec() never returns to the interpreter, so a SIGINT/SIGTERM handler
    # would never run. A running QTimer slot executes Python bytecode, which
    # gives the interpreter a chance to deliver the pending signal.
    signal.signal(signal.SIGINT, lambda *_: island.quit_application())
    signal.signal(signal.SIGTERM, lambda *_: island.quit_application())

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
