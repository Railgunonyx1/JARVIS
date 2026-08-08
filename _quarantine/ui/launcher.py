"""
JARVIS MK-X — Application Launcher
Handles venv activation, dependency checks, Ollama startup, and mode selection.

Usage:
  python launcher.py              # Interactive mode selection
  python launcher.py --gui        # Launch GUI directly
  python launcher.py --text       # Launch text mode
  python launcher.py --voice      # Launch voice mode
  python launcher.py --health     # Run health checks
  python launcher.py --install    # Install/update dependencies only
"""

import os
import sys
import subprocess
import shutil
import urllib.request
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT))
VENV_DIR = ROOT / "venv"
PYTHON_EXE = VENV_DIR / "Scripts" / "python.exe"
REQUIREMENTS = ROOT / "requirements.txt"

BANNER = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██║╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
            MARK LXXXV - Cloud-First AI Assistant
"""

PYTHON_SEARCH_PATHS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python311" / "python.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python312" / "python.exe",
    Path("C:/Python311/python.exe"),
    Path("C:/Python312/python.exe"),
    Path("C:/Program Files/Python311/python.exe"),
    Path("C:/Program Files/Python312/python.exe"),
]


def _find_system_python() -> str | None:
    """Find a working system Python (not the Store alias, not the venv)."""
    # Try shutil.which first
    found = shutil.which("python3") or shutil.which("python")
    if found:
        try:
            subprocess.run(
                [found, "-c", "import sys; print(sys.version)"],
                capture_output=True, timeout=5, check=True,
            )
            return found
        except Exception:
            pass

    # Try known paths
    for p in PYTHON_SEARCH_PATHS:
        if p.exists():
            try:
                subprocess.run(
                    [str(p), "-c", "import sys; print(sys.version)"],
                    capture_output=True, timeout=5, check=True,
                )
                return str(p)
            except Exception:
                continue

    return None


def _is_venv_active() -> bool:
    return hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )


def _ensure_venv():
    if _is_venv_active():
        return True

    # If we're not in the venv, check if venv exists and re-exec inside it
    if PYTHON_EXE.exists():
        print(f"[INFO] Activating venv...")
        os.execv(str(PYTHON_EXE), [str(PYTHON_EXE)] + sys.argv)
        return False

    # No venv — create it using system Python
    sys_python = _find_system_python()
    if not sys_python:
        print("[FAIL] Cannot find Python. Install Python 3.11+ from python.org")
        sys.exit(1)

    print("[SETUP] Creating virtual environment...")
    subprocess.run([sys_python, "-m", "venv", str(VENV_DIR)], check=True)
    print("[OK] Virtual environment created.")

    # Re-exec inside the new venv
    os.execv(str(PYTHON_EXE), [str(PYTHON_EXE)] + sys.argv)
    return False


def _ensure_dependencies():
    if not REQUIREMENTS.exists():
        print("[WARN] requirements.txt not found, skipping dependency check.")
        return

    marker = VENV_DIR / ".deps_installed"
    if marker.exists():
        req_mtime = REQUIREMENTS.stat().st_mtime
        marker_mtime = marker.stat().st_mtime
        if req_mtime <= marker_mtime:
            return

    print("[SETUP] Installing/updating dependencies (may take a few minutes)...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        check=True,
    )
    marker.write_text(str(time.time()))
    print("[OK] Dependencies ready.")


def _ensure_ollama():
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=2) as r:
            if r.status == 200:
                print("[OK] Ollama is running.")
                return True
    except Exception:
        pass

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path("C:/Program Files/Ollama/ollama.exe"),
    ]
    ollama_path = next((p for p in candidates if p.exists()), None)
    if not ollama_path:
        print("[WARN] Ollama not found. Local models unavailable.")
        return False

    print("[SETUP] Starting Ollama...")
    subprocess.Popen(
        [str(ollama_path), "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )

    for _ in range(30):
        time.sleep(0.5)
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
            print("[OK] Ollama started.")
            return True
        except Exception:
            continue

    print("[WARN] Ollama started but may not be ready yet.")
    return False


def _run_main(mode: str | None = None):
    import subprocess as _sp
    # Use pythonw (no console window) for all modes except health/install
    pw = VENV_DIR / "Scripts" / "pythonw.exe"
    exe = str(pw if pw.exists() else PYTHON_EXE)
    args = [exe, str(BASE_DIR / "main.py")]
    if mode:
        args.append(f"--{mode}")
    kwargs = {"cwd": str(BASE_DIR)}
    if sys.platform == "win32":
        kwargs["creationflags"] = _sp.CREATE_NO_WINDOW
    _sp.run(args, **kwargs)


def _show_menu() -> str:
    print(BANNER)
    print("  Select mode:")
    print("    [1] Desktop   -- Arc Reactor HUD (default)")
    print("    [2] Text      -- Terminal chat, no voice")
    print("    [3] Voice     -- Mic input + TTS output")
    print("    [4] Full      -- Desktop + Voice + Camera + Gestures")
    print("    [5] Health    -- Run system health checks")
    print("    [6] Install   -- Reinstall dependencies")
    print("    [Q] Quit")
    print()

    choice = input("  > ").strip().lower()
    mapping = {"1": "desktop", "2": "text", "3": "voice", "4": "full", "5": "health", "6": "install", "q": "quit"}
    return mapping.get(choice, "")


def main():
    os.chdir(BASE_DIR)

    # Fix Windows console encoding for Unicode output
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    if not _ensure_venv():
        return

    for arg in sys.argv[1:]:
        if arg == "--install":
            _ensure_dependencies()
            print("[OK] Done.")
            return
        if arg in ("--gui", "--text", "--voice", "--full", "--health", "--web"):
            _ensure_ollama()
            _run_main(arg.lstrip("-"))
            return

    if len(sys.argv) > 1:
        return

    _ensure_dependencies()
    _ensure_ollama()

    mode = _show_menu()
    if mode == "quit":
        print("Goodbye, sir.")
        return
    if mode == "install":
        _ensure_dependencies()
        print("[OK] Dependencies updated.")
        input("\nPress Enter to continue...")
        return
    if mode:
        _run_main(mode)


if __name__ == "__main__":
    main()
