"""
JARVIS MK-X — Futuristic Desktop HUD
Arc Reactor center, system monitor, status panels, control bar.
PyQt6 — optimized for low CPU/GPU usage on i5 + 8GB RAM.
"""

from __future__ import annotations

import ctypes
import math
import os
import platform
import random
import sys
import threading
import time
from pathlib import Path

import psutil

from PyQt6.QtCore import (
    QPointF, QRectF, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QFontDatabase, QLinearGradient,
    QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient,
)
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPushButton, QSizePolicy, QSlider, QTextEdit, QVBoxLayout,
    QWidget,
)

# ── Paths ──────────────────────────────────────────────────────────────────────

from core.utils import get_project_root as _base_dir

BASE_DIR = _base_dir()

# ── Color Palette ──────────────────────────────────────────────────────────────

class C:
    BG          = "#06080c"
    PANEL       = "#0a0e14"
    PANEL_GLASS = "#0c1018"
    BORDER      = "#141c28"
    BORDER_B    = "#1e2d40"
    BORDER_A    = "#2a3f58"

    PRI         = "#00d4ff"
    PRI_DIM     = "#006a88"
    PRI_GHO     = "#001828"
    PRI_DARK    = "#003858"

    AMBER       = "#ffaa00"
    AMBER_DIM   = "#886600"
    AMBER_GHO   = "#1a1200"

    GREEN       = "#00ff88"
    GREEN_DIM   = "#007744"
    GREEN_GHO   = "#001a0e"

    RED         = "#ff3355"
    RED_DIM     = "#881a33"

    TEXT        = "#c8d8e8"
    TEXT_DIM    = "#5a7088"
    TEXT_MED    = "#8aa0b8"
    WHITE       = "#e8f0f8"
    DARK        = "#030508"


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h)
    c.setAlpha(a)
    return c


# ── System Metrics (background thread) ─────────────────────────────────────────

# NVML cached (avoid redefining ctypes.Structure every 2s)
_nvml_lib = None
_nvml_ok = None


class _U(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _SysMetrics:
    def __init__(self):
        self.cpu = 0.0
        self.cpu_freq = 0.0
        self.mem = 0.0
        self.mem_used = 0.0
        self.mem_total = 0.0
        self.net_up = 0.0
        self.net_down = 0.0
        self.disk_read = 0.0
        self.disk_write = 0.0
        self.disk_pct = 0.0
        self.battery_pct = -1.0
        self.battery_charging = False
        self.uptime = ""
        self.processes = 0
        self.gpu = -1.0
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_disk = psutil.disk_io_counters()
        self._last_net_t = time.time()
        self._last_disk_t = time.time()
        self._running = True
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(2.0)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        try:
            freq = psutil.cpu_freq()
            cpu_freq = freq.current if freq else 0.0
        except Exception:
            cpu_freq = 0.0

        mem = psutil.virtual_memory()
        mem_pct = mem.percent
        mem_used = mem.used / (1024 ** 3)
        mem_total = mem.total / (1024 ** 3)

        nc = psutil.net_io_counters()
        now = time.time()
        dt = now - self._last_net_t
        if dt > 0:
            net_up = (nc.bytes_sent - self._last_net.bytes_sent) / dt / 1024
            net_down = (nc.bytes_recv - self._last_net.bytes_recv) / dt / 1024
        else:
            net_up = net_down = 0.0
        self._last_net = nc
        self._last_net_t = now

        dc = psutil.disk_io_counters()
        dt2 = now - self._last_disk_t
        if dt2 > 0 and dc:
            disk_read = (dc.read_bytes - self._last_disk.read_bytes) / dt2 / 1024
            disk_write = (dc.write_bytes - self._last_disk.write_bytes) / dt2 / 1024
        else:
            disk_read = disk_write = 0.0
        if dc:
            self._last_disk = dc
        self._last_disk_t = now

        disk = psutil.disk_usage("/")
        disk_pct = disk.percent

        bat = psutil.sensors_battery()
        if bat:
            bat_pct = bat.percent
            bat_charging = bat.power_plugged
        else:
            bat_pct = -1.0
            bat_charging = False

        boot = psutil.boot_time()
        up_secs = now - boot
        up_h = int(up_secs // 3600)
        up_m = int((up_secs % 3600) // 60)
        uptime = f"{up_h}h {up_m}m"

        procs = len(psutil.pids())

        gpu = self._get_gpu()

        with self._lock:
            self.cpu = cpu
            self.cpu_freq = cpu_freq
            self.mem = mem_pct
            self.mem_used = mem_used
            self.mem_total = mem_total
            self.net_up = net_up
            self.net_down = net_down
            self.disk_read = disk_read
            self.disk_write = disk_write
            self.disk_pct = disk_pct
            self.battery_pct = bat_pct
            self.battery_charging = bat_charging
            self.uptime = uptime
            self.processes = procs
            self.gpu = gpu

    def _get_gpu(self) -> float:
        global _nvml_lib, _nvml_ok

        try:
            import pynvml
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            return float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)
        except Exception:
            pass

        if _nvml_ok is False:
            return -1.0

        try:
            if _nvml_lib is None:
                if platform.system() == "Windows":
                    _nvml_lib = ctypes.WinDLL("nvml")
                else:
                    _nvml_lib = ctypes.CDLL("libnvidia-ml.so.1")
                _nvml_lib.nvmlInit_v2()

            dev = ctypes.c_void_p()
            _nvml_lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
            u = _U()
            _nvml_lib.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(u))
            _nvml_ok = True
            return float(u.gpu)
        except Exception:
            _nvml_ok = False
            return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu, "cpu_freq": self.cpu_freq,
                "mem": self.mem, "mem_used": self.mem_used, "mem_total": self.mem_total,
                "net_up": self.net_up, "net_down": self.net_down,
                "disk_read": self.disk_read, "disk_write": self.disk_write,
                "disk_pct": self.disk_pct,
                "battery_pct": self.battery_pct, "battery_charging": self.battery_charging,
                "uptime": self.uptime, "processes": self.processes,
                "gpu": self.gpu,
            }


_metrics = _SysMetrics()


# ── Arc Reactor Widget ─────────────────────────────────────────────────────────

class ArcReactor(QWidget):
    """
    Central Arc Reactor element.
    States: idle, listening, thinking, speaking, muted
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.state = "idle"
        self._tick = 0
        self._ring_angles = [0.0, 120.0, 240.0]
        self._pulse_r = 0.0
        self._scan = 0.0
        self._brightness = 0.6
        self._tgt_brightness = 0.6

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(33)

    def set_state(self, state: str):
        self.state = state

    def _step(self):
        self._tick += 1

        speeds = {
            "idle":     [0.3, -0.2, 0.4],
            "listening": [1.2, -0.8, 1.6],
            "thinking": [2.0, -1.5, 2.5],
            "speaking": [1.8, -1.2, 2.2],
            "muted":    [0.05, -0.03, 0.08],
        }
        sp = speeds.get(self.state, speeds["idle"])
        for i in range(3):
            self._ring_angles[i] = (self._ring_angles[i] + sp[i]) % 360

        scan_speeds = {"idle": 0.8, "listening": 2.5, "thinking": 4.0, "speaking": 3.0, "muted": 0.1}
        self._scan = (self._scan + scan_speeds.get(self.state, 0.8)) % 360

        bright = {"idle": 0.5, "listening": 0.9, "thinking": 0.75, "speaking": 1.0, "muted": 0.15}
        self._tgt_brightness = bright.get(self.state, 0.5)
        self._brightness += (self._tgt_brightness - self._brightness) * 0.08

        if self.state == "speaking":
            self._pulse_r += 3.5
            fw = min(self.width(), self.height()) * 0.38
            if self._pulse_r > fw:
                self._pulse_r = 0.0
        elif self.state == "thinking":
            self._pulse_r += 2.0
            fw = min(self.width(), self.height()) * 0.38
            if self._pulse_r > fw:
                self._pulse_r = 0.0
        else:
            self._pulse_r = max(0, self._pulse_r - 2.0)

        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), qcol(C.BG))

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)
        br = self._brightness

        state_col = {
            "idle":      C.PRI,
            "listening": C.PRI,
            "thinking":  C.AMBER,
            "speaking":  C.GREEN,
            "muted":     C.RED,
        }.get(self.state, C.PRI)

        # Outer halo
        for i in range(8):
            r = fw * 0.44 * (1.0 - i * 0.04)
            a = max(0, min(255, int(br * 30 * (1.0 - i / 8))))
            p.setPen(QPen(qcol(state_col, a), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # Pulse rings
        if self._pulse_r > 2:
            pr = self._pulse_r
            a = max(0, int(180 * (1.0 - pr / (fw * 0.38))))
            p.setPen(QPen(qcol(state_col, a), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(cx - pr, cy - pr, pr * 2, pr * 2))

        # Three rotating arc rings
        ring_specs = [
            (0.40, 2.5, 100, 70),
            (0.33, 2.0, 70, 50),
            (0.26, 1.5, 50, 38),
        ]
        for idx, (r_frac, width, arc_len, gap) in enumerate(ring_specs):
            r = fw * r_frac
            angle = self._ring_angles[idx]
            a = max(0, min(255, int(br * 220 * (1.0 - idx * 0.15))))
            p.setPen(QPen(qcol(state_col, a), width))
            p.setBrush(Qt.BrushStyle.NoBrush)
            rect = QRectF(cx - r, cy - r, r * 2, r * 2)
            start = angle
            while start < angle + 360:
                p.drawArc(rect, int(start * 16), int(arc_len * 16))
                start += arc_len + gap

        # Scanner line
        sr = fw * 0.42
        sa = min(255, int(br * 160))
        arc_len = 60 if self.state in ("thinking", "speaking") else 40
        p.setPen(QPen(qcol(state_col, sa), 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        srect = QRectF(cx - sr, cy - sr, sr * 2, sr * 2)
        p.drawArc(srect, int(self._scan * 16), int(arc_len * 16))

        # Center core
        core_r = fw * 0.10
        grad = QRadialGradient(cx, cy, core_r)
        col = QColor(state_col)
        grad.setColorAt(0.0, qcol(state_col, min(255, int(br * 255))))
        grad.setColorAt(0.6, qcol(state_col, min(255, int(br * 120))))
        grad.setColorAt(1.0, qcol(state_col, 0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - core_r, cy - core_r, core_r * 2, core_r * 2))

        # Inner core ring
        inner_r = fw * 0.06
        p.setPen(QPen(qcol(state_col, min(255, int(br * 200))), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2))

        # Tick marks
        t_out = fw * 0.44
        t_in = fw * 0.42
        p.setPen(QPen(qcol(state_col, int(br * 80)), 0.8))
        for deg in range(0, 360, 10):
            rad = math.radians(deg)
            inn = t_in if deg % 30 == 0 else t_in + 3
            p.drawLine(
                QPointF(cx + t_out * math.cos(rad), cy - t_out * math.sin(rad)),
                QPointF(cx + inn * math.cos(rad), cy - inn * math.sin(rad)),
            )

        # Crosshair
        ch = fw * 0.46
        gap_h = fw * 0.14
        p.setPen(QPen(qcol(state_col, int(br * 50)), 0.6))
        p.drawLine(QPointF(cx - ch, cy), QPointF(cx - gap_h, cy))
        p.drawLine(QPointF(cx + gap_h, cy), QPointF(cx + ch, cy))
        p.drawLine(QPointF(cx, cy - ch), QPointF(cx, cy - gap_h))
        p.drawLine(QPointF(cx, cy + gap_h), QPointF(cx, cy + ch))

        # Corner brackets
        bl = 16
        bc = qcol(state_col, int(br * 140))
        p.setPen(QPen(bc, 1.5))
        hl, hr = cx - fw * 0.48, cx + fw * 0.48
        ht, hb = cy - fw * 0.48, cy + fw * 0.48
        for bx, by, dx, dy in [(hl, ht, 1, 1), (hr, ht, -1, 1), (hl, hb, 1, -1), (hr, hb, -1, -1)]:
            p.drawLine(QPointF(bx, by), QPointF(bx + dx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * bl))

        # State label
        labels = {
            "idle": "STANDBY", "listening": "LISTENING", "thinking": "PROCESSING",
            "speaking": "SPEAKING", "muted": "MUTED",
        }
        label = labels.get(self.state, "INIT")
        p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(state_col, min(255, int(br * 220))), 1))
        p.drawText(QRectF(0, cy + fw * 0.32, W, 20), Qt.AlignmentFlag.AlignCenter, label)


# ── Status Panel (Left) ────────────────────────────────────────────────────────

class StatusPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setStyleSheet(f"background: {C.PANEL}; border-right: 1px solid {C.BORDER};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        lay.addWidget(self._header("JARVIS STATUS"))
        lay.addSpacing(4)

        self._voice_label = self._info_row("VOICE", "IDLE", C.PRI)
        self._wake_label = self._info_row("WAKE WORD", "OFFLINE", C.TEXT_DIM)
        self._task_label = self._info_row("TASK", "None", C.TEXT_DIM)
        self._intent_label = self._info_row("INTENT", "—", C.TEXT_DIM)
        self._mic_label = self._info_row("MIC", "ON", C.GREEN)

        lay.addSpacing(8)
        lay.addWidget(self._separator())
        lay.addSpacing(4)

        self._model_label = self._info_row("MODEL", "Ollama", C.PRI_DIM)
        self._fallback_label = self._info_row("FALLBACK", "—", C.TEXT_DIM)
        self._latency_label = self._info_row("LATENCY", "—", C.TEXT_DIM)

        lay.addStretch()

    def _header(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        l.setStyleSheet(f"color: {C.PRI}; background: transparent; padding: 2px 0;")
        return l

    def _separator(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet(f"color: {C.BORDER}; max-height: 1px;")
        return f

    def _info_row(self, label: str, value: str, color: str) -> dict:
        lbl = QLabel(label)
        lbl.setFont(QFont("Consolas", 7))
        lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        val = QLabel(value)
        val.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        val.setStyleSheet(f"color: {color}; background: transparent;")
        val.setWordWrap(True)
        return {"label": lbl, "value": val, "color": color}

    def _update_row(self, row: dict, value: str, color: str | None = None):
        row["value"].setText(value)
        if color:
            row["value"].setStyleSheet(f"color: {color}; background: transparent;")

    def set_voice_state(self, state: str):
        colors = {"IDLE": C.TEXT_DIM, "LISTENING": C.GREEN, "THINKING": C.AMBER, "SPEAKING": C.PRI}
        self._update_row(self._voice_label, state, colors.get(state, C.TEXT_DIM))

    def set_wake_word(self, status: str):
        c = C.GREEN if status == "ACTIVE" else C.TEXT_DIM
        self._update_row(self._wake_label, status, c)

    def set_task(self, task: str):
        self._update_row(self._task_label, task[:24], C.TEXT_MED)

    def set_intent(self, intent: str):
        self._update_row(self._intent_label, intent[:24], C.TEXT_MED)

    def set_mic(self, on: bool):
        if on:
            self._update_row(self._mic_label, "ON", C.GREEN)
        else:
            self._update_row(self._mic_label, "OFF", C.RED)

    def set_model(self, name: str):
        self._update_row(self._model_label, name[:20], C.PRI)

    def set_fallback(self, name: str):
        self._update_row(self._fallback_label, name[:20], C.TEXT_DIM)

    def set_latency(self, ms: str):
        self._update_row(self._latency_label, ms, C.TEXT_MED)


# ── System Monitor Panel (Right) ───────────────────────────────────────────────

class MonitorPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(210)
        self.setStyleSheet(f"background: {C.PANEL}; border-left: 1px solid {C.BORDER};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        lay.addWidget(self._header("SYSTEM MONITOR"))
        lay.addSpacing(4)

        self._cpu_bar = self._metric_row("CPU", "0%", "0 GHz")
        self._ram_bar = self._metric_row("RAM", "0%", "0/0 GB")
        self._gpu_bar = self._metric_row("GPU", "N/A", "")
        self._net_bar = self._metric_row("NET", "↑0 ↓0 KB/s", "")
        self._disk_bar = self._metric_row("DISK", "0%", "R:0 W:0 KB/s")
        self._bat_bar = self._metric_row("BATTERY", "N/A", "")

        lay.addSpacing(6)
        lay.addWidget(self._separator())
        lay.addSpacing(4)

        self._uptime_row = self._info_row("UPTIME", "—")
        self._proc_row = self._info_row("PROCESSES", "—")

        lay.addStretch()

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._refresh)
        self._tmr.start(2000)

    def _header(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        l.setStyleSheet(f"color: {C.PRI}; background: transparent; padding: 2px 0;")
        return l

    def _separator(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet(f"color: {C.BORDER}; max-height: 1px;")
        return f

    def _metric_row(self, label: str, value: str, sub: str) -> dict:
        lbl = QLabel(label)
        lbl.setFont(QFont("Consolas", 7))
        lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        val = QLabel(value)
        val.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        val.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        sub_lbl = QLabel(sub)
        sub_lbl.setFont(QFont("Consolas", 7))
        sub_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        return {"label": lbl, "value": val, "sub": sub_lbl}

    def _info_row(self, label: str, value: str) -> dict:
        lbl = QLabel(label)
        lbl.setFont(QFont("Consolas", 7))
        lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        val = QLabel(value)
        val.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        val.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        return {"label": lbl, "value": val}

    def _update_metric(self, row: dict, value: str, sub: str = "", color: str = C.TEXT):
        row["value"].setText(value)
        row["value"].setStyleSheet(f"color: {color}; background: transparent;")
        if sub:
            row["sub"].setText(sub)

    def _update_info(self, row: dict, value: str):
        row["value"].setText(value)

    def _color_for_pct(self, pct: float) -> str:
        if pct > 85:
            return C.RED
        elif pct > 65:
            return C.AMBER
        return C.GREEN

    def _refresh(self):
        s = _metrics.snapshot()

        cpu_c = self._color_for_pct(s["cpu"])
        self._update_metric(
            self._cpu_bar,
            f"{s['cpu']:.1f}%",
            f"{s['cpu_freq']:.0f} MHz" if s["cpu_freq"] else "",
            cpu_c,
        )

        ram_c = self._color_for_pct(s["mem"])
        self._update_metric(
            self._ram_bar,
            f"{s['mem']:.1f}%",
            f"{s['mem_used']:.1f}/{s['mem_total']:.1f} GB",
            ram_c,
        )

        if s["gpu"] >= 0:
            gpu_c = self._color_for_pct(s["gpu"])
            self._update_metric(self._gpu_bar, f"{s['gpu']:.0f}%", "", gpu_c)
        else:
            self._update_metric(self._gpu_bar, "N/A", "", C.TEXT_DIM)

        self._update_metric(
            self._net_bar,
            f"↑{s['net_up']:.0f}  ↓{s['net_down']:.0f} KB/s",
            "",
            C.TEXT_MED,
        )

        disk_c = self._color_for_pct(s["disk_pct"])
        self._update_metric(
            self._disk_bar,
            f"{s['disk_pct']:.0f}%",
            f"R:{s['disk_read']:.0f}  W:{s['disk_write']:.0f} KB/s",
            disk_c,
        )

        if s["battery_pct"] >= 0:
            bat_c = C.GREEN if s["battery_charging"] else self._color_for_pct(100 - s["battery_pct"])
            chg = "⚡" if s["battery_charging"] else ""
            self._update_metric(self._bat_bar, f"{s['battery_pct']:.0f}% {chg}", "", bat_c)
        else:
            self._update_metric(self._bat_bar, "N/A", "", C.TEXT_DIM)

        self._update_info(self._uptime_row, s["uptime"])
        self._update_info(self._proc_row, str(s["processes"]))


# ── Log Widget ─────────────────────────────────────────────────────────────────

class LogWidget(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.DARK};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
                padding: 6px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 6px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 3px;
                min-height: 20px;
            }}
        """)
        self._queue: list[str] = []
        self._typing = False
        self._text = ""
        self._pos = 0
        self._tag = "sys"

    def append_log(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text = self._queue.pop(0)
        self._pos = 0
        tl = self._text.lower()
        if tl.startswith("you:"):
            self._tag = "you"
        elif tl.startswith("jarvis:") or tl.startswith("ai:"):
            self._tag = "ai"
        elif "err" in tl:
            self._tag = "err"
        else:
            self._tag = "sys"

        colors = {"you": C.WHITE, "ai": C.PRI, "err": C.RED, "sys": C.TEXT_DIM}
        col = colors.get(self._tag, C.TEXT)
        cur = self.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        fmt = cur.charFormat()
        fmt.setForeground(QBrush(qcol(col)))
        cur.insertText(self._text + "\n", fmt)
        self.setTextCursor(cur)
        self.ensureCursorVisible()


# ── Mic Button ─────────────────────────────────────────────────────────────────

class MicButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(56, 56)
        self.setCheckable(True)
        self.setChecked(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._glow = 0.0
        self._tgt_glow = 0.0
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._animate)
        self._tmr.start(33)
        self._update_style()

    def _animate(self):
        self._glow += (self._tgt_glow - self._glow) * 0.15
        self.update()

    def _update_style(self):
        if self.isChecked():
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {C.RED_DIM};
                    border: 2px solid {C.RED};
                    border-radius: 28px;
                    color: {C.RED};
                    font-size: 20px;
                }}
                QPushButton:hover {{
                    background: {C.RED};
                    color: {C.DARK};
                }}
            """)
            self.setText("🔇")
            self._tgt_glow = 0.0
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: {C.GREEN_GHO};
                    border: 2px solid {C.GREEN};
                    border-radius: 28px;
                    color: {C.GREEN};
                    font-size: 20px;
                }}
                QPushButton:hover {{
                    background: {C.GREEN_DIM};
                    color: {C.WHITE};
                }}
            """)
            self.setText("🎙")
            self._tgt_glow = 1.0

    def nextCheckState(self):
        super().nextCheckState()
        self._update_style()


# ── Control Bar (Bottom) ───────────────────────────────────────────────────────

class ControlBar(QWidget):
    text_command = pyqtSignal(str)
    mute_toggled = pyqtSignal(bool)
    voice_toggled = pyqtSignal(bool)
    camera_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)
        self.setStyleSheet(f"background: {C.PANEL}; border-top: 1px solid {C.BORDER};")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(12)

        # Left: mic + buttons
        left = QVBoxLayout()
        left.setSpacing(4)
        self._mic_btn = MicButton()
        self._mic_btn.toggled.connect(self._on_mute)
        left.addWidget(self._mic_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        # Voice toggle button
        self._voice_btn = QPushButton("🎤")
        self._voice_btn.setFixedSize(28, 28)
        self._voice_btn.setFont(QFont("Consolas", 10))
        self._voice_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._voice_btn.setCheckable(True)
        self._voice_btn.setToolTip("Toggle voice input")
        self._voice_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.DARK}; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:checked {{
                background: {C.GREEN_DIM}; color: {C.WHITE};
                border-color: {C.GREEN};
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}
        """)
        self._voice_btn.toggled.connect(self.voice_toggled.emit)
        btn_row.addWidget(self._voice_btn)

        # Camera toggle button
        self._cam_btn = QPushButton("📷")
        self._cam_btn.setFixedSize(28, 28)
        self._cam_btn.setFont(QFont("Consolas", 10))
        self._cam_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cam_btn.setCheckable(True)
        self._cam_btn.setToolTip("Toggle camera + gestures")
        self._cam_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.DARK}; color: {C.TEXT_DIM};
                border: 1px solid {C.BORDER}; border-radius: 4px;
            }}
            QPushButton:checked {{
                background: {C.PRI_DIM}; color: {C.WHITE};
                border-color: {C.PRI};
            }}
            QPushButton:hover {{ color: {C.PRI}; border-color: {C.BORDER_B}; }}
        """)
        self._cam_btn.toggled.connect(self.camera_toggled.emit)
        btn_row.addWidget(self._cam_btn)

        for label, icon in [("Settings", "⚙"), ("Memory", "🧠"), ("Diagnostics", "🔍")]:
            btn = QPushButton(icon)
            btn.setFixedSize(28, 28)
            btn.setFont(QFont("Consolas", 10))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(label)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {C.DARK}; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 4px;
                }}
                QPushButton:hover {{
                    color: {C.PRI}; border-color: {C.BORDER_B};
                }}
            """)
            btn_row.addWidget(btn)
        left.addLayout(btn_row)
        lay.addLayout(left)

        # Center: response text
        center = QVBoxLayout()
        center.setSpacing(4)
        self._response = QLabel("System online. Awaiting input.")
        self._response.setFont(QFont("Consolas", 10))
        self._response.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._response.setWordWrap(True)
        self._response.setMinimumHeight(36)
        center.addWidget(self._response)

        # Input row — editable text field
        input_row = QHBoxLayout()
        input_row.setSpacing(4)
        self._input = QLineEdit()
        self._input.setFont(QFont("Consolas", 9))
        self._input.setPlaceholderText("Type a command...")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {C.DARK}; color: {C.TEXT};
                border: 1px solid {C.BORDER}; border-radius: 3px;
                padding: 4px 8px;
            }}
            QLineEdit:focus {{
                border-color: {C.PRI_DIM};
            }}
        """)
        self._input.setFixedHeight(28)
        self._input.returnPressed.connect(self._on_send)
        input_row.addWidget(self._input)

        send = QPushButton("▸")
        send.setFixedSize(28, 28)
        send.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {C.PANEL}; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
        """)
        send.clicked.connect(self._on_send)
        input_row.addWidget(send)
        center.addLayout(input_row)
        lay.addLayout(center, stretch=1)

        # Right: indicators
        right = QVBoxLayout()
        right.setSpacing(2)
        self._model_lbl = self._indicator("MODEL", "Ollama")
        self._fallback_lbl = self._indicator("FALLBACK", "—")
        self._latency_lbl = self._indicator("LATENCY", "—")
        self._mic_status_lbl = self._indicator("MIC", "OFF")
        self._cam_status_lbl = self._indicator("CAM", "OFF")
        self._gesture_lbl = self._indicator("GESTURE", "—")
        right.addStretch()
        lay.addLayout(right)

    def _indicator(self, label: str, value: str) -> dict:
        lbl = QLabel(label)
        lbl.setFont(QFont("Consolas", 6))
        lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        val = QLabel(value)
        val.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        val.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        return {"label": lbl, "value": val}

    def _on_mute(self, checked: bool):
        self.mute_toggled.emit(checked)

    def _on_send(self):
        text = self._input.text().strip()
        if text:
            self.text_command.emit(text)
            self._input.clear()

    def set_response(self, text: str):
        self._response.setText(text[:200])

    def set_model(self, name: str):
        self._model_lbl["value"].setText(name[:18])

    def set_fallback(self, name: str):
        self._fallback_lbl["value"].setText(name[:18])

    def set_latency(self, ms: str):
        self._latency_lbl["value"].setText(ms)

    def set_memory_usage(self, mb: str):
        pass

    def set_mic_status(self, on: bool):
        self._mic_status_lbl["value"].setText("ON" if on else "OFF")
        color = C.GREEN if on else C.TEXT_DIM
        self._mic_status_lbl["value"].setStyleSheet(f"color: {color}; background: transparent;")

    def set_cam_status(self, on: bool):
        self._cam_status_lbl["value"].setText("ON" if on else "OFF")
        color = C.PRI if on else C.TEXT_DIM
        self._cam_status_lbl["value"].setStyleSheet(f"color: {color}; background: transparent;")

    def set_gesture(self, gesture: str):
        self._gesture_lbl["value"].setText(gesture[:18])


# ── Header Bar (Top) ──────────────────────────────────────────────────────────

class HeaderBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(f"background: {C.DARK}; border-bottom: 1px solid {C.BORDER};")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)

        left = QLabel("JARVIS MK-X")
        left.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        left.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(left)

        self._status = QLabel("SYSTEM ONLINE")
        self._status.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        self._status.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        lay.addWidget(self._status)

        lay.addStretch()

        ver = QLabel("MK-X 1.0")
        ver.setFont(QFont("Consolas", 7))
        ver.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(ver)

    def set_status(self, text: str, color: str = C.GREEN):
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {color}; background: transparent;")


# ── Main Window ────────────────────────────────────────────────────────────────

class JarvisUI(QMainWindow):
    on_text_command = None
    on_mute_toggle = None
    on_voice_toggle = None
    on_camera_toggle = None

    # Signals for thread-safe updates from background threads
    gesture_update = pyqtSignal(str)
    camera_frame = pyqtSignal(object)
    voice_text = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS MK-X")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 780)
        self.setStyleSheet(f"background: {C.BG}; color: {C.TEXT};")

        # Start metrics thread lazily (only when UI is created)
        _metrics.start()

        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QVBoxLayout(central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # Header
        self._header = HeaderBar()
        main_lay.addWidget(self._header)

        # Body: left panel | reactor + log | right panel
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Left panel
        self._status_panel = StatusPanel()
        body.addWidget(self._status_panel)

        # Center: reactor + log + camera feed
        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(0)

        # Camera feed (hidden by default, shown when camera is active)
        self._camera_label = QLabel()
        self._camera_label.setFixedHeight(180)
        self._camera_label.setStyleSheet(f"background: {C.DARK}; border: 1px solid {C.BORDER};")
        self._camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._camera_label.setText("📷 Camera off")
        self._camera_label.setFont(QFont("Consolas", 9))
        self._camera_label.setStyleSheet(f"color: {C.TEXT_DIM}; background: {C.DARK}; border: 1px solid {C.BORDER};")
        self._camera_label.hide()
        center.addWidget(self._camera_label)

        self._reactor = ArcReactor()
        center.addWidget(self._reactor, stretch=1)

        self._log = LogWidget()
        self._log.setFixedHeight(140)
        center.addWidget(self._log)

        body.addLayout(center, stretch=1)

        # Right panel
        self._monitor = MonitorPanel()
        body.addWidget(self._monitor)

        main_lay.addLayout(body, stretch=1)

        # Control bar
        self._controls = ControlBar()
        self._controls.mute_toggled.connect(self._on_mute)
        self._controls.voice_toggled.connect(self._on_voice)
        self._controls.camera_toggled.connect(self._on_camera)
        self._controls.text_command.connect(self._on_text)
        main_lay.addWidget(self._controls)

        # Connect signals for thread-safe updates
        self.gesture_update.connect(self._handle_gesture_update)
        self.camera_frame.connect(self._handle_camera_frame)
        self.voice_text.connect(self._handle_voice_text)

        # Connect log to controls
        self._controls.set_model("Ollama")

    def _on_mute(self, muted: bool):
        if self.on_mute_toggle:
            self.on_mute_toggle(muted)

    def _on_voice(self, on: bool):
        self._controls.set_mic_status(on)
        if self.on_voice_toggle:
            self.on_voice_toggle(on)

    def _on_camera(self, on: bool):
        self._controls.set_cam_status(on)
        if on:
            self._camera_label.show()
        else:
            self._camera_label.hide()
            self._camera_label.setText("📷 Camera off")
        if self.on_camera_toggle:
            self.on_camera_toggle(on)

    def _on_text(self, text: str):
        if self.on_text_command:
            self.on_text_command(text)

    def _handle_gesture_update(self, gesture: str):
        self._controls.set_gesture(gesture)

    def _handle_camera_frame(self, frame_data):
        """Update camera feed label with a frame (numpy array or QPixmap)."""
        try:
            from PyQt6.QtGui import QImage, QPixmap
            import numpy as np
            if isinstance(frame_data, np.ndarray):
                h, w, ch = frame_data.shape
                bytes_per_line = ch * w
                qt_img = QImage(frame_data.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(qt_img.rgbSwapped())
                scaled = pixmap.scaled(
                    self._camera_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._camera_label.setPixmap(scaled)
        except Exception:
            pass

    def _handle_voice_text(self, text: str):
        """Display recognized voice text in the input field."""
        self._controls._input.setText(text)

    def set_state(self, state: str):
        state_map = {
            "INITIALISING": "idle",
            "IDLE": "idle",
            "LISTENING": "listening",
            "THINKING": "thinking",
            "PROCESSING": "thinking",
            "SPEAKING": "speaking",
            "SLEEPING": "muted",
        }
        reactor_state = state_map.get(state, "idle")
        self._reactor.set_state(reactor_state)
        self._status_panel.set_voice_state(state)
        colors = {"LISTENING": C.GREEN, "THINKING": C.AMBER, "SPEAKING": C.PRI, "SLEEPING": C.TEXT_DIM}
        self._header.set_status(state, colors.get(state, C.GREEN))

    def write_log(self, text: str):
        self._log.append_log(text)

    def set_response(self, text: str):
        self._controls.set_response(text)

    def set_model(self, name: str):
        self._controls.set_model(name)
        self._status_panel.set_model(name)

    def set_latency(self, ms: str):
        self._controls.set_latency(ms)
        self._status_panel.set_latency(ms)

    def set_task(self, task: str):
        self._status_panel.set_task(task)

    def set_intent(self, intent: str):
        self._status_panel.set_intent(intent)

    def set_mic(self, on: bool):
        self._status_panel.set_mic(on)

    def set_wake_word(self, status: str):
        self._status_panel.set_wake_word(status)


# ── Standalone Test ────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    ui = JarvisUI()
    ui.show()

    def _demo():
        import random
        states = ["IDLE", "LISTENING", "THINKING", "SPEAKING"]
        i = [0]

        def _cycle():
            s = states[i[0] % len(states)]
            ui.set_state(s)
            ui.set_intent("query.time")
            ui.set_task("Processing voice input")
            i[0] += 1

        t = QTimer()
        t.timeout.connect(_cycle)
        t.start(3000)

        ui.write_log("SYS: JARVIS MK-X initialized")
        ui.write_log("SYS: All subsystems online")
        ui.write_log("YOU: What time is it?")
        ui.write_log("AI: It's 07:30 PM.")
        ui.set_response("It's 07:30 PM. All systems operational.")

    _demo()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
