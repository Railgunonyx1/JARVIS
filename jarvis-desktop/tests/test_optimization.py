"""Phase 7 — optimization tests: performance monitoring and benchmarks."""

import sys
import os
import time

import pytest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_DESKTOP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _DESKTOP_ROOT not in sys.path:
    sys.path.insert(0, _DESKTOP_ROOT)


def test_performance_monitor_constructs():
    from app.diagnostics.monitor import PerformanceMonitor
    monitor = PerformanceMonitor(interval=0.1)
    assert monitor._running is False
    monitor.start()
    assert monitor._running is True
    monitor.stop()
    assert monitor._running is False


def test_performance_monitor_records_events():
    from app.diagnostics.monitor import PerformanceMonitor
    monitor = PerformanceMonitor(interval=0.1)
    monitor.start()
    time.sleep(0.2)
    monitor.record_event("voice_roundtrip", 1.5)
    monitor.record_event("tool_exec", 0.3)
    time.sleep(0.2)
    monitor.stop()

    latencies = monitor.get_event_latencies("voice_roundtrip")
    assert 1.5 in latencies


def test_performance_monitor_averages():
    from app.diagnostics.monitor import PerformanceMonitor
    monitor = PerformanceMonitor(interval=0.05)
    monitor.start()
    time.sleep(0.5)
    monitor.stop()

    avg_cpu = monitor.get_average_cpu()
    avg_ram = monitor.get_average_ram()
    peak_ram = monitor.get_peak_ram_gb()

    assert avg_cpu >= 0.0
    assert avg_ram >= 0.0
    assert peak_ram >= 0.0


def test_benchmark_result_serialization():
    from app.diagnostics.monitor import BenchmarkResult
    result = BenchmarkResult("test_metric", 1.5, "s", target=2.0, passed=True)
    d = result.to_dict()
    assert d["name"] == "test_metric"
    assert d["value"] == 1.5
    assert d["unit"] == "s"
    assert d["target"] == 2.0
    assert d["passed"] is True


def test_benchmark_startup_time():
    from app.diagnostics.monitor import PerformanceBenchmarker
    benchmarker = PerformanceBenchmarker()

    def slow_startup():
        time.sleep(0.01)

    result = benchmarker.measure_startup_time(slow_startup)
    assert result.value >= 0.01
    assert result.passed is True
    assert len(benchmarker.get_results()) == 1


def test_benchmark_idle_resources():
    from app.diagnostics.monitor import PerformanceBenchmarker
    benchmarker = PerformanceBenchmarker()
    cpu_result, ram_result = benchmarker.measure_idle_resources(duration_s=0.5)

    assert cpu_result.unit == "%"
    assert ram_result.unit == "GB"
    assert cpu_result.value >= 0.0
    assert ram_result.value >= 0.0


def test_benchmark_tool_execution():
    from app.diagnostics.monitor import PerformanceBenchmarker
    benchmarker = PerformanceBenchmarker()

    def fast_tool():
        time.sleep(0.001)

    result = benchmarker.measure_tool_execution(fast_tool)
    assert result.unit == "s"
    assert result.passed is True


def test_benchmark_summary():
    from app.diagnostics.monitor import PerformanceBenchmarker
    benchmarker = PerformanceBenchmarker()
    benchmarker.measure_startup_time(lambda: None)
    benchmarker.measure_tool_execution(lambda: None)

    summary = benchmarker.get_summary()
    assert summary["total_measurements"] == 2
    assert summary["passed"] == 2
    assert summary["failed"] == 0
    assert summary["all_passed"] is True


def test_benchmark_save_report(tmp_path):
    from app.diagnostics.monitor import PerformanceBenchmarker
    benchmarker = PerformanceBenchmarker()
    benchmarker.measure_startup_time(lambda: None)
    benchmarker.measure_tool_execution(lambda: None)

    report_path = tmp_path / "benchmark_report.json"
    benchmarker.save_report(report_path)
    assert report_path.exists()

    import json
    report = json.loads(report_path.read_text())
    assert "results" in report
    assert "summary" in report
    assert len(report["results"]) == 2


def test_benchmark_voice_roundtrip():
    from app.diagnostics.monitor import PerformanceBenchmarker
    benchmarker = PerformanceBenchmarker()

    def mock_stt():
        return "hello"

    def mock_agent(text):
        pass

    def mock_tts(text):
        pass

    result = benchmarker.measure_voice_roundtrip(mock_stt, mock_agent, mock_tts)
    assert result.unit == "s"
    assert result.passed is True


def test_benchmark_workspace_fps():
    from app.diagnostics.monitor import PerformanceBenchmarker
    benchmarker = PerformanceBenchmarker()

    def mock_get_fps():
        return 30.0

    result = benchmarker.measure_workspace_fps(mock_get_fps, duration_s=0.2)
    assert result.unit == "fps"
    assert result.value == 30.0
    assert result.passed is True


def test_gesture_tracker_has_fps_limit():
    from app.gestures.tracking import HandTracker
    tracker = HandTracker(target_fps=10)
    assert tracker._target_fps == 10
    assert tracker._min_frame_interval == 0.1


def test_chat_window_has_message_limit():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from app.ui.chat_window import ChatWindow
    window = ChatWindow()
    assert window._max_messages == 500


def test_voice_manager_lazy_warmup():
    """Voice manager should warm up models without blocking."""
    from app.voice.voice_manager import VoiceManager
    vm = VoiceManager(prefer_local_stt=False, use_kokoro_tts=False)
    # warmup should not block
    vm.warmup()
    assert vm.state.value == "idle"
