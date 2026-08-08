"""
JARVIS MK-X — Native Desktop App
Frameless PyQt6 window with custom chrome, system tray, and performance controls.
Flask backend runs in a background thread; QWebEngineView loads the optimized HUD.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger("jarvis.ui_web")

BASE_DIR = Path(__file__).resolve().parent


def _create_tray_icon() -> QPixmap:
    """Create a simple cyan dot icon for the system tray."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#00d4ff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, 24, 24)
    painter.end()
    return pixmap


class JarvisDesktopUI(QMainWindow):
    """Frameless native desktop window with custom title bar."""

    def __init__(self, port=8765):
        super().__init__()
        self.port = port
        self._drag_pos = None
        self._performance_mode = "balanced"
        self._ws_connected = False

        # Frameless + no default title bar
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(1000, 650)
        self.resize(1280, 800)

        self.setStyleSheet("QMainWindow { background: #05080f; }")

        # ── Central widget + layout ───────────────────────────────────
        central = QWidget()
        central.setStyleSheet("background: #05080f;")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Custom title bar ──────────────────────────────────────────
        self._title_bar = QWidget()
        self._title_bar.setFixedHeight(36)
        self._title_bar.setStyleSheet(
            "background: #0a0f18; border-bottom: 1px solid rgba(0,212,255,0.12);"
        )
        tb = QHBoxLayout(self._title_bar)
        tb.setContentsMargins(12, 0, 8, 0)
        tb.setSpacing(10)

        # Cyan dot
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(
            "background: #00d4ff; border-radius: 4px;"
            "box-shadow: 0 0 8px rgba(0,212,255,0.8);"
        )
        tb.addWidget(dot)

        # Title
        title = QLabel("JARVIS MK-X")
        title.setStyleSheet(
            "color: #00d4ff; font-family: 'Segoe UI', monospace; font-size: 12px;"
            "font-weight: bold; letter-spacing: 3px; background: transparent;"
        )
        tb.addWidget(title)

        # Version
        ver = QLabel("v4.2")
        ver.setStyleSheet(
            "color: #555; font-family: 'Segoe UI', monospace; font-size: 9px;"
            "letter-spacing: 1px; background: transparent;"
        )
        tb.addWidget(ver)

        tb.addStretch()

        # Performance mode button
        self._perf_btn = QPushButton("BALANCED")
        self._perf_btn.setFixedSize(80, 22)
        self._perf_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._perf_btn.setStyleSheet(self._perf_button_style("balanced"))
        self._perf_btn.clicked.connect(self._cycle_performance_mode)
        tb.addWidget(self._perf_btn)

        # Connection indicator
        self._conn_label = QLabel("OFFLINE")
        self._conn_label.setStyleSheet(
            "color: #555; font-family: 'Segoe UI', monospace; font-size: 9px;"
            "letter-spacing: 1px; background: transparent;"
        )
        tb.addWidget(self._conn_label)

        self._conn_dot = QLabel()
        self._conn_dot.setFixedSize(6, 6)
        self._conn_dot.setStyleSheet("background: #333; border-radius: 3px;")
        tb.addWidget(self._conn_dot)

        # Window controls
        for text, handler in [
            ("—", self.showMinimized),
            ("□", self._toggle_maximize),
            ("×", self.close),
        ]:
            btn = QPushButton(text)
            btn.setFixedSize(28, 22)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { color: #666; background: transparent; border: none;"
                "font-size: 13px; font-weight: bold; }"
                "QPushButton:hover { color: #00d4ff; background: rgba(0,212,255,0.08); }"
            )
            btn.clicked.connect(handler)
            tb.addWidget(btn)

        root.addWidget(self._title_bar)

        # ── Web engine ────────────────────────────────────────────────
        self._view = QWebEngineView()
        page = self._view.page()
        page.featurePermissionRequested.connect(self._on_permission)

        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)

        # Reduce memory: disable GPU compositing if possible
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)

        root.addWidget(self._view, 1)

        # ── System tray ───────────────────────────────────────────────
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(QIcon(_create_tray_icon()))
        self._tray.setToolTip("JARVIS MK-X")

        tray_menu = QMenu()
        tray_menu.setStyleSheet(
            "QMenu { background: #0a0f18; color: #c8d6e5; border: 1px solid rgba(0,212,255,0.2); }"
            "QMenu::item:selected { background: rgba(0,212,255,0.15); }"
        )
        show_action = QAction("Show", self)
        show_action.triggered.connect(self._show_from_tray)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()

        for mode in ["Eco", "Balanced", "Performance"]:
            action = QAction(mode, self)
            action.triggered.connect(lambda checked, m=mode.lower(): self._set_performance_mode(m))
            tray_menu.addAction(action)

        tray_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        tray_menu.addAction(quit_action)

        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

        # ── Connection checker ─────────────────────────────────────────
        self._conn_timer = QTimer(self)
        self._conn_timer.timeout.connect(self._check_connection)
        self._conn_timer.start(5000)

    # ── Window dragging ──────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 36:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.position().y() < 36:
            self._toggle_maximize()

    # ── Helpers ──────────────────────────────────────────────────────────

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _on_permission(self, url, feature):
        page = self._view.page()
        if feature in (QWebEnginePage.Feature.MediaAudioCapture,
                       QWebEnginePage.Feature.MediaVideoCapture,
                       QWebEnginePage.Feature.MediaAudioVideoCapture):
            page.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser)
            logger.info("Granted %s permission for %s", feature, url)

    def _perf_button_style(self, mode):
        colors = {"eco": "#22c55e", "balanced": "#00d4ff", "performance": "#ff6b35"}
        c = colors.get(mode, "#00d4ff")
        return (
            f"QPushButton {{ color: {c}; background: rgba(0,0,0,0.3); border: 1px solid {c}33;"
            f"border-radius: 4px; font-family: 'Segoe UI', monospace; font-size: 9px;"
            f"letter-spacing: 1px; padding: 2px 6px; }}"
            f"QPushButton:hover {{ background: {c}15; }}"
        )

    def _cycle_performance_mode(self):
        modes = ["eco", "balanced", "performance"]
        idx = modes.index(self._performance_mode)
        self._set_performance_mode(modes[(idx + 1) % len(modes)])

    def _set_performance_mode(self, mode):
        self._performance_mode = mode
        self._perf_btn.setText(mode.upper())
        self._perf_btn.setStyleSheet(self._perf_button_style(mode))
        # Tell the backend
        try:
            import urllib.request
            data = json.dumps({"mode": mode}).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/api/performance",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=2)
        except Exception:
            pass

    def _check_connection(self):
        try:
            import urllib.request
            req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/status")
            urllib.request.urlopen(req, timeout=2)
            if not self._ws_connected:
                self._ws_connected = True
                self._conn_label.setText("ONLINE")
                self._conn_label.setStyleSheet(
                    "color: #00d4ff; font-family: 'Segoe UI', monospace; font-size: 9px;"
                    "letter-spacing: 1px; background: transparent;"
                )
                self._conn_dot.setStyleSheet("background: #00d4ff; border-radius: 3px;")
        except Exception:
            if self._ws_connected:
                self._ws_connected = False
                self._conn_label.setText("OFFLINE")
                self._conn_label.setStyleSheet(
                    "color: #555; font-family: 'Segoe UI', monospace; font-size: 9px;"
                    "letter-spacing: 1px; background: transparent;"
                )
                self._conn_dot.setStyleSheet("background: #333; border-radius: 3px;")

    def load_hud(self):
        """Load the HUD from the Flask server. Retries if backend not ready."""
        import urllib.request
        def _try_load():
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/status", timeout=2)
                self._view.setUrl(QUrl(f"http://127.0.0.1:{self.port}"))
            except Exception:
                QTimer.singleShot(1000, _try_load)
        _try_load()

    def closeEvent(self, event):
        """Minimize to tray instead of quitting."""
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "JARVIS MK-X",
            "Minimized to system tray",
            QSystemTrayIcon.MessageIcon.Information,
            1500,
        )


def _start_flask_background(port: int):
    """Run init_jarvis + Flask server in a background thread."""
    from web.server import app, init_jarvis

    def _serve():
        init_jarvis()
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=_serve, daemon=True)
    server_thread.start()

    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=2)
            logger.info("Flask server ready on port %d", port)
            return True
        except Exception:
            time.sleep(0.3)

    logger.warning("Flask server may not be ready yet")
    return False


def run(port=8765):
    """Launch the desktop app."""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running in tray

    ui = JarvisDesktopUI(port)
    ui.show()
    ui.raise_()
    ui.activateWindow()

    # Start Flask in background WITHOUT blocking — HUD shows until backend ready
    threading.Thread(target=_start_flask_background, args=(port,), daemon=True).start()

    # Load HUD after event loop starts (avoids C++ object deletion)
    QTimer.singleShot(1000, ui.load_hud)

    print("[UI] JARVIS MK-X desktop app running")
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
