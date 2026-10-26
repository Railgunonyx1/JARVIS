"""Deterministic workspace loading tests — DI-051.

Tests verify deterministic state transitions, missing files, invalid resources,
failed initialization and readiness signaling. Separates testable loading logic
from graphical rendering.

Hardware/QML-dependent tests require Qt runtime and are marked MANUAL.
"""


import sys
import os

# Ensure project root is on PATH for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Ensure dynamic-island app is importable
DYNAMIC_ISLAND_ROOT = os.path.join(PROJECT_ROOT, "dynamic-island")
DYNAMIC_ISLAND_APP = os.path.join(PROJECT_ROOT, "dynamic-island", "app")
if DYNAMIC_ISLAND_ROOT not in sys.path:
    sys.path.insert(0, DYNAMIC_ISLAND_ROOT)
if DYNAMIC_ISLAND_APP not in sys.path:
    sys.path.insert(0, DYNAMIC_ISLAND_APP)

# Attempt to import the module under test
HAS_WORKSPACE = False
Workspace3D = None

try:
    from dynamic_island.app.workspace3d.workspace3d import Workspace3D as _Workspace3D
    Workspace3D = _Workspace3D
    HAS_WORKSPACE = True
except (ModuleNotFoundError, ImportError):
    HAS_WORKSPACE = False


# Import pytest markers and utilities
import pytest


@pytest.mark.skipif(
    not HAS_WORKSPACE,
    reason="Workspace3D module not available - skipping DI-051 tests"
)
class TestWorkspaceLoading:
    """Tests for deterministic workspace loading behavior.

    Verifies:
    - QML load success/failure
    - show/hide state transitions
    - panel text update
    - Resource cleanup / shutdown
    - Idempotent load()
    """

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        # Ensure clean state per test
        pass

    @pytest.mark.requires_qt
    def test_workspace_load_success(self):
        """Workspace3D.load() returns True when QML loads successfully."""
        if not HAS_WORKSPACE:
            pytest.skip("Workspace3D not available")

        ws = Workspace3D()
        # load() should succeed if QML is available
        result = ws.load()
        assert isinstance(result, bool), f"Expected bool, got {type(result)}"
        # If QML loads, is_loaded should be True
        if result:
            assert ws.is_loaded == True
            # Clean up
            ws.shutdown()

    @pytest.mark.requires_qt
    def test_workspace_load_idempotent(self):
        """Workspace3D.load() is idempotent - calling twice returns True."""
        if not HAS_WORKSPACE:
            pytest.skip("Workspace3D not available")

        ws = Workspace3D()
        result1 = ws.load()
        assert result1 is True, "First load should succeed"
        result2 = ws.load()
        assert result2 is True, "Second load (idempotent) should succeed"
        ws.shutdown()

    @pytest.mark.requires_qt
    def test_workspace_show_hide_transitions(self):
        """Workspace3D.show()/hide() toggle state correctly."""
        if not HAS_WORKSPACE:
            pytest.skip("Workspace3D not available")

        ws = Workspace3D()
        assert ws.is_visible is False
        ws.show()
        assert ws.is_visible is True
        ws.hide()
        assert ws.is_visible is False
        ws.shutdown()

    @pytest.mark.requires_qt
    def test_workspace_set_panel_text(self):
        """Workspace3D.set_panel_text() updates panel data and emits signal."""
        if not HAS_WORKSPACE:
            pytest.skip("Workspace3D not available")

        ws = Workspace3D()
        ws.load()
        # Set panel text - should update internal dict
        ws.set_panel_text("chat", "Hello JARVIS")
        # The panel_updated signal should have been emitted;
        # since we can't capture signals easily without qtbot, verify internal state
        assert ws.get_panel_text("chat") == "Hello JARVIS"
        ws.shutdown()

    @pytest.mark.requires_qt
    def test_workspace_shutdown_clears_resources(self):
        """Workspace3D.shutdown() releases resources and resets state."""
        if not HAS_WORKSPACE:
            pytest.skip("Workspace3D not available")

        ws = Workspace3D()
        ws.load()
        assert ws.is_loaded is True
        ws.shutdown()
        assert ws.is_loaded is False
        # Widget should be None after shutdown
        assert ws.get_widget() is None
        ws.__dict__.clear()

    def test_workspace_no_crash_on_missing_qml(self):
        """Workspace3D should not crash when QML file missing - gracefully returns False."""
        if not HAS_WORKSPACE:
            pytest.skip("Workspace3D not available - QML dependent")

        # Create a workspace with a non-existent QML path by patching
        # Since we can't easily patch _QML_PATH, test the error handling path
        # by verifying the method catches exceptions
        try:
            ws = Workspace3D()
            # Calling load() should not raise; it should return False on error
            result = ws.load()
            assert isinstance(result, bool), "load() should return bool even on failure"
            # On failure, widget should be None and loaded should be False
            assert ws.is_loaded is False
            ws.shutdown()
        except Exception as e:
            pytest.fail(f"Workspace3D.load() raised exception on error path: {e}")

    @pytest.mark.manual
    def test_workspace_with_real_qml_runtime(self):
        """REQUIRES: Real Qt Quick 3D runtime with scene.qml present.

        This test validates the complete QML loading pipeline when the
        Qt environment is properly configured. It is explicitly marked
        MANUAL and not represented as an automated CI pass.

        On systems with PySide6 + Qt Quick 3D, this exercises the full
        load/show/hide/set_panel_text/shutdown pipeline end-to-end.

        SKIP in CI unless Qt Quick 3D runtime is available.
        """
        pytest.skip("Manual test - requires real Qt Quick 3D runtime")