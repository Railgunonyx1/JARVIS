"""Launch JARVIS daemon from jarvis.bat.

This script is called by jarvis.bat to start the JARVIS daemon in the background.
It uses the venv Python to start the daemon server.
"""

import subprocess
import sys
import os

# Get the JARVIS root directory (where jarvis.bat lives)
jarvis_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else os.getcwd()
# Resolve to absolute path if relative
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
]

# Start daemon (detached so bat can continue)
 subprocess.StartupInformation = None
 subprocess.CREATE_NEW_CONSOLE = 0x00000010

try:
    subprocess.Popen(
        cmd,
        cwd=jarvis_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
except Exception:
    # Fallback: just print the command for user to run manually
    print(" ".join(cmd))