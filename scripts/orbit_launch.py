#!/usr/bin/env python3
"""JARVIS Orbit — Browser Launcher.

A Chrome-like launcher that:
1. Starts the JARVIS bridge server (if not running)
2. Launches unbranded Chromium with the JARVIS extension
3. Shows a clean status UI during startup

Usage:
    python scripts/orbit_launch.py              # Normal launch
    python scripts/orbit_launch.py --first-run  # First-run setup
    python scripts/orbit_launch.py --debug      # Debug mode (show browser stdout)
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = ROOT / "venv" / "Scripts" / "python.exe"
BRIDGE_SERVER = ROOT / "jbrowser-bridge" / "server.py"
EXT_DIR = ROOT / "extensions" / "jbrowser"
ICON_PATH = ROOT / "scripts" / "jbrowser.ico"
BRIDGE_URL = "http://127.0.0.1:8170/status"
BRIDGE_PORT = 8170

# ── Colors ─────────────────────────────────────────────────────────
class C:
    """ANSI color codes."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BG_BLACK = "\033[40m"

# ── Banner ─────────────────────────────────────────────────────────
ORBIT_BANNER = f"""
{C.DIM}┌─────────────────────────────────────────────┐
│                                             │
│   {C.CYAN}{C.BOLD}● ORBIT{C.RESET}{C.DIM}                               │
│   {C.WHITE}JARVIS Browser{C.RESET}{C.DIM}                        │
│                                             │
│   {C.DIM}Unbranded Chromium + JARVIS{C.RESET}{C.DIM}              │
│   {C.DIM}Nothing Design System{C.RESET}{C.DIM}                   │
│                                             │
└─────────────────────────────────────────────┘{C.RESET}
"""

# ── Status Display ─────────────────────────────────────────────────
class Launcher:
    """Orbit browser launcher with status display."""

    def __init__(self, debug: bool = False, first_run: bool = False):
        self.debug = debug
        self.first_run = first_run
        self.bridge_process: subprocess.Popen | None = None
        self.chromium_process: subprocess.Popen | None = None

    def status(self, msg: str, state: str = "info") -> None:
        """Print a status line with colored prefix."""
        icons = {
            "info": f"{C.CYAN}●",
            "ok": f"{C.GREEN}✓",
            "warn": f"{C.YELLOW}⚠",
            "error": f"{C.RED}✗",
            "wait": f"{C.BLUE}◌",
            "start": f"{C.MAGENTA}▸",
        }
        icon = icons.get(state, "●")
        print(f"  {icon} {C.RESET}{msg}")

    def header(self, text: str) -> None:
        """Print a section header."""
        print(f"\n{C.BOLD}{C.WHITE}{text}{C.RESET}")
        print(f"{C.DIM}{'─' * 40}{C.RESET}")

    # ── Python Detection ───────────────────────────────────────────
    def find_python(self) -> str:
        """Find the Python executable."""
        # Check venv first
        if VENV_PYTHON.exists():
            return str(VENV_PYTHON)

        # Check system Python
        for name in ["python3", "python"]:
            try:
                result = subprocess.run(
                    [name, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return name
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        return "python"

    # ── Bridge Detection ───────────────────────────────────────────
    def is_bridge_running(self) -> bool:
        """Check if the bridge server is already running."""
        try:
            import urllib.request
            req = urllib.request.urlopen(BRIDGE_URL, timeout=2)
            data = req.read()
            return b'"ok": true' in data or b'"ok":true' in data
        except Exception:
            return False

    def start_bridge(self) -> bool:
        """Start the JARVIS bridge server."""
        if self.is_bridge_running():
            self.status("Bridge already running", "ok")
            return True

        python = self.find_python()
        self.status(f"Starting bridge on port {BRIDGE_PORT}...", "start")

        try:
            cmd = [python, str(BRIDGE_SERVER), "--backend", "echo"]
            self.bridge_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL if not self.debug else None,
                stderr=subprocess.DEVNULL if not self.debug else None,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            self.status(f"Failed to start bridge: {e}", "error")
            return False

        # Wait for bridge to come up
        for i in range(30):  # 3 seconds max
            time.sleep(0.1)
            if self.is_bridge_running():
                self.status("Bridge connected", "ok")
                return True
            if self.bridge_process and self.bridge_process.poll() is not None:
                self.status("Bridge process exited unexpectedly", "error")
                return False

        self.status("Bridge still starting (browser will connect when ready)", "warn")
        return True

    # ── Chromium Detection ─────────────────────────────────────────
    def find_chromium(self) -> str | None:
        """Find Orbit's unbranded Chromium runtime.

        Orbit ships its own Chromium — never the user's Chrome.
        Priority: J_BROWSER_CHROMIUM_PATH env > Playwright's ms-playwright > system Chromium.
        """
        # 1. Explicit env override
        env_path = os.environ.get("J_BROWSER_CHROMIUM_PATH")
        if env_path and Path(env_path).exists():
            return env_path

        # 2. Playwright's ms-playwright directory (LOCALAPPDATA/ms-playwright)
        pw_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
        if pw_dir.exists():
            # Find latest chromium-* directory
            chromium_dirs = sorted(pw_dir.glob("chromium-*"), reverse=True)
            for d in chromium_dirs:
                if sys.platform == "win32":
                    chrome = d / "chrome-win64" / "chrome.exe"
                elif sys.platform == "darwin":
                    chrome = d / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
                else:
                    chrome = d / "chrome-linux" / "chrome"
                if chrome.exists():
                    return str(chrome)

        # 3. System Chromium (unbranded — NOT Chrome)
        candidates = []
        if sys.platform == "win32":
            candidates = [
                Path(os.environ.get("LOCALAPPDATA", "")) / "Chromium" / "Application" / "chrome.exe",
                Path(os.environ.get("PROGRAMFILES", "")) / "Chromium" / "Application" / "chrome.exe",
                Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Chromium" / "Application" / "chrome.exe",
            ]
        elif sys.platform == "darwin":
            candidates = [
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            ]
        else:
            candidates = [
                Path("/usr/bin/chromium-browser"),
                Path("/usr/bin/chromium"),
                Path("/snap/bin/chromium"),
            ]

        for c in candidates:
            if c.exists():
                return str(c)

        return None

    # ── Browser Launch ─────────────────────────────────────────────
    def launch_browser(self) -> bool:
        """Launch Orbit's Chromium with the JARVIS extension.

        Orbit is a custom browser — it uses unbranded Chromium, not Chrome.
        """
        browser = self.find_chromium()

        if not browser:
            self.status("Orbit's Chromium not found.", "error")
            self.status("Install unbranded Chromium or set J_BROWSER_CHROMIUM_PATH:", "warn")
            self.status(f"  $env:J_BROWSER_CHROMIUM_PATH = \"C:\\path\\to\\chrome.exe\"", "info")
            self.status("", "info")
            self.status("Or install via Playwright (recommended):", "info")
            self.status("  pip install playwright && playwright install chromium", "info")
            return False

        self.status(f"Orbit Chromium: {Path(browser).name}", "info")

        # Build launch arguments
        args = [
            browser,
            "--new-window",
            "--no-first-run",
            "--no-default-browser-check",
            "--user-data-dir=" + str(ROOT / ".orbit-profile"),
        ]

        # Extension loading
        if EXT_DIR.exists():
            args.append(f"--load-extension={EXT_DIR}")
            self.status(f"Loading extension: {EXT_DIR.name}", "start")

        # JARVIS new tab
        args.append("chrome://newtab")

        # Launch
        try:
            self.chromium_process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL if not self.debug else None,
                stderr=subprocess.DEVNULL if not self.debug else None,
            )
            self.status(f"Orbit launched (PID {self.chromium_process.pid})", "ok")
            return True
        except Exception as e:
            self.status(f"Failed to launch Orbit: {e}", "error")
            return False

    # ── First Run ──────────────────────────────────────────────────
    def first_run(self) -> None:
        """Handle first-run setup."""
        self.header("First Run Setup")

        print(f"""
{C.YELLOW}The JARVIS extension needs to be loaded once:{C.RESET}

  1. Orbit will open to chrome://extensions
  2. Enable {C.BOLD}Developer mode{C.RESET} (top-right toggle)
  3. Click {C.BOLD}Load unpacked{C.RESET}
  4. Select: {C.CYAN}{EXT_DIR}{C.RESET}

{C.DIM}After that, the extension persists across launches.{C.RESET}
""")

        input(f"{C.CYAN}Press Enter when ready...{C.RESET}")

        # Open extensions page
        browser = self.find_chromium()
        if browser:
            subprocess.Popen([browser, "chrome://extensions/"])
            self.status("Opened chrome://extensions in Orbit", "ok")
        else:
            self.status("Orbit Chromium not found — load extension manually", "warn")

    # ── Cleanup ────────────────────────────────────────────────────
    def cleanup(self) -> None:
        """Clean up processes on exit."""
        if self.bridge_process and self.bridge_process.poll() is None:
            self.status("Shutting down bridge...", "info")
            self.bridge_process.terminate()
            try:
                self.bridge_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.bridge_process.kill()

    # ── Main ───────────────────────────────────────────────────────
    def run(self) -> int:
        """Run the launcher."""
        print(ORBIT_BANNER)

        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, lambda *_: (self.cleanup(), sys.exit(0)))

        if self.first_run:
            self.first_run_setup()
            return 0

        # Stage 1: Bridge
        self.header("JARVIS Bridge")
        bridge_ok = self.start_bridge()

        # Stage 2: Browser
        self.header("Chromium Browser")
        browser_ok = self.launch_browser()

        # Summary
        self.header("Status")
        if bridge_ok and browser_ok:
            self.status("Everything is ready", "ok")
            self.status(f"Bridge: {C.CYAN}http://127.0.0.1:{BRIDGE_PORT}{C.RESET}", "info")
            self.status("JARVIS is online in the sidebar", "info")
        elif browser_ok:
            self.status("Browser launched (bridge still starting)", "warn")
        else:
            self.status("Launch failed — check errors above", "error")
            return 1

        print(f"\n{C.DIM}Press Ctrl+C to quit the bridge, or close the browser.{C.RESET}\n")

        # Keep launcher alive to monitor bridge
        try:
            while True:
                time.sleep(5)
                if self.chromium_process and self.chromium_process.poll() is not None:
                    self.status("Browser closed", "info")
                    break
                if self.bridge_process and self.bridge_process.poll() is not None:
                    self.status("Bridge stopped", "warn")
                    break
        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()

        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="JARVIS Orbit — Custom Chromium Browser Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Orbit is a custom browser built on unbranded Chromium with JARVIS.
It is NOT Google Chrome. It ships with its own isolated Chromium.

Examples:
  python scripts/orbit_launch.py              # Normal launch
  python scripts/orbit_launch.py --first-run  # First-run setup
  python scripts/orbit_launch.py --debug      # Show browser stdout
        """,
    )
    parser.add_argument("--first-run", action="store_true", help="First-run setup")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    args = parser.parse_args()

    launcher = Launcher(debug=args.debug, first_run=args.first_run)
    return launcher.run()


if __name__ == "__main__":
    sys.exit(main())
