"""JARVIS Desktop Island — entry point for the Dynamic Island overlay.

Top-center morphing pill: idle -> hover peek -> click to expand into the
compact conversation panel. Also the target of the OS autostart entry.
"""

import argparse
import os
import signal
import sys

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

try:
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
except Exception:
    QLocalServer = None
    QLocalSocket = None

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
