#!/usr/bin/env python3
"""Test that the CLI imports work correctly."""
import sys
sys.path.insert(0, r'C:\Users\aayan\Desktop\JARVIS')

print("Testing CLI imports...")

# Test basic cli import
try:
    import cli
    print("  cli: OK")
except Exception as e:
    print(f"  cli: FAIL - {e}")

# Test renderer import
try:
    from cli.renderer import Renderer
    print("  renderer: OK")
except Exception as e:
    print(f"  renderer: FAIL - {e}")

# Test bridge import
try:
    from cli.bridge import AgentBridge
    print("  bridge: OK")
except Exception as e:
    print(f"  bridge: FAIL - {e}")

# Test models import
try:
    from cli.models import AppState, Mode, PlanStep, Plan, AgentEvent, Message, ConfirmationRequest, RiskLevel, StepStatus, EventType, EventStatus
    print("  models: OK")
except Exception as e:
    print(f"  models: FAIL - {e}")

# Test layout import
try:
    from cli.layout import LayoutManager, LayoutMode
    print("  layout: OK")
except Exception as e:
    print(f"  layout: FAIL - {e}")

# Test daemon_ui import
try:
    from cli.daemon_ui import DaemonUI, _ui_main
    print("  daemon_ui: OK")
except Exception as e:
    print(f"  daemon_ui: FAIL - {e}")

# Test theme import
try:
    from cli.theme import COLORS, build_rich_theme
    print("  theme: OK")
except Exception as e:
    print(f"  theme: FAIL - {e}")

# Test details import
try:
    from cli.details import render_summary
    print("  details: OK")
except Exception as e:
    print(f"  details: FAIL - {e}")

print("\nAll imports test complete.")