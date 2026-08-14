"""Launch JARVIS daemon from jarvis.bat.

This script is called by jarvis.bat to start the JARVIS daemon in the background.
It uses the venv Python to start the daemon server.
"""

import subprocess
import sys
import os

# The JARVIS root directory (parent of this daemon/ package).
jarvis_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.path.isabs(jarvis_dir):
    jarvis_dir = os.path.abspath(jarvis_dir)

# Activate venv and start daemon
venv_python = os.path.join(jarvis_dir, "venv", "Scripts", "python.exe")
project_dir = jarvis_dir

cmd = [
    venv_python,
    "-m", "daemon.server",
    "start",
    "--project-dir", project_dir,
    "--ui-port", "8787",
]


def _kill_stale_daemons() -> None:
    """Terminate any leftover JARVIS daemon so only one owns the ports.

    Stale daemons (e.g. started manually with system Python) keep a console
    window open and hold ws://127.0.0.1:8787/ws, which makes a fresh launch
    appear to do nothing. Only processes running ``-m daemon.server`` inside
    the JARVIS project are targeted.
    """
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | "
        "Where-Object { $_.CommandLine -match '-m daemon.server' -and $_.CommandLine -match 'JARVIS' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            cwd=jarvis_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=30,
        )
    except Exception:
        pass


try:
    _kill_stale_daemons()
    subprocess.Popen(
        cmd,
        cwd=jarvis_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
    )
except Exception:
    # Fallback: just print the command for user to run manually
    print(" ".join(cmd))
