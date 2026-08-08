"""
JARVIS MK-X — Main Entry Point
Terminal-first autonomous engineering agent (Claude Code style).

Usage:
  python main.py                       # Launch terminal CLI (interactive)
  python main.py <goal>                # One-shot goal
  python main.py --health              # Run health checks and exit
  python -m cli                        # Same CLI (preferred entry point)

The PyQt6 HUD, web dashboard, React/Tauri frontend, and vision stack have
been quarantined (see _quarantine/ui). The terminal is now the primary
interface; voice/vision/HUD remain optional extensions only.
"""

import sys

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def run_health_check():
    """Run health checks and print report."""
    from core.health import format_health_report, run_all_checks
    print(format_health_report(run_all_checks()))


def main():
    if "--health" in sys.argv:
        run_health_check()
        return
    # Everything else routes to the Claude Code-style terminal CLI.
    from cli.main import app
    app()


if __name__ == "__main__":
    main()
