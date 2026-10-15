"""Download every JARVIS dependency in one command.

Cross-platform (Linux/Bazzite + Windows). Installs:

  1. runtime dependencies  (requirements.txt)
  2. dev/test tools        (requirements-dev.txt)
  3. optional Playwright Chromium   --playwright
  4. optional Orbit npm deps        --orbit
  5. optional precompiled bytecode  --precompile

Examples
--------
    python scripts/download_dependencies.py
    python scripts/download_dependencies.py --playwright --orbit
    python scripts/download_dependencies.py --system   # use current interpreter
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements.txt"
REQUIREMENTS_DEV = ROOT / "requirements-dev.txt"
VENV_DIR = ROOT / "venv"


def info(msg: str) -> None:
    print(f"  [..] {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"  [ok] {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"  [!!] {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"  [!!] {msg}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def _venv_python() -> Path:
    return VENV_DIR / ("Scripts" if sys.platform == "win32" else "bin") / (
        "python.exe" if sys.platform == "win32" else "python"
    )


def ensure_python(use_system: bool) -> Path:
    if use_system:
        ok(f"Using current interpreter: {sys.executable}")
        return Path(sys.executable)

    existing = _venv_python()
    if existing.exists():
        ok(f"Reusing virtual environment: {VENV_DIR}")
        return existing

    info(f"Creating virtual environment in {VENV_DIR} ...")
    result = subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)])
    if result.returncode != 0 or not existing.exists():
        fail("venv creation failed (install python3-venv / python3-devel).")
    ok(f"Virtual environment ready: {existing}")
    return existing


def run_pip(python: Path, *args: str, required: bool = True) -> None:
    cmd = [str(python), "-m", "pip", *args]
    info("pip " + " ".join(args))
    result = subprocess.run(cmd)
    if result.returncode != 0 and required:
        fail(f"Command failed: pip {' '.join(args)}")


def install_requirements(python: Path) -> None:
    if not REQUIREMENTS.exists():
        fail(f"Missing {REQUIREMENTS}")
    run_pip(python, "install", "--upgrade", "pip")
    run_pip(python, "install", "-r", str(REQUIREMENTS))
    ok("Runtime dependencies installed.")
    if REQUIREMENTS_DEV.exists():
        run_pip(python, "install", "-r", str(REQUIREMENTS_DEV))
        ok("Dev/test dependencies installed.")


def install_playwright(python: Path) -> None:
    info("Installing Playwright Chromium engine ...")
    run_pip(python, "install", "playwright")
    result = subprocess.run([str(python), "-m", "playwright", "install", "chromium"])
    if result.returncode != 0:
        warn("playwright install chromium failed (non-fatal).")
    else:
        ok("Playwright Chromium installed.")


def install_orbit() -> None:
    pkg = ROOT / "orbit-browser"
    if not (pkg / "package.json").exists():
        warn("orbit-browser/package.json not found — skipping.")
        return
    npm = shutil.which("npm")
    if npm is None:
        warn("npm not found — skipping Orbit deps (install Node.js 20+).")
        return
    install_cmd = ["ci", "--prefer-offline", "--no-audit", "--no-fund"]
    if not (pkg / "package-lock.json").exists():
        install_cmd = ["install", "--prefer-offline", "--no-audit", "--no-fund"]
    info("Installing Orbit browser npm dependencies ...")
    result = subprocess.run([npm, *install_cmd], cwd=str(pkg))
    if result.returncode != 0:
        fail("npm install failed in orbit-browser.")
    ok("Orbit browser dependencies installed.")


def precompile(python: Path) -> None:
    script = ROOT / "scripts" / "precompile.py"
    if not script.exists():
        return
    info("Precompiling bytecode ...")
    result = subprocess.run([str(python), str(script)])
    if result.returncode == 0:
        ok("Bytecode precompiled.")
    else:
        warn("Precompile skipped (non-fatal).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download all JARVIS dependencies.")
    parser.add_argument("--system", action="store_true",
                        help="install into the current interpreter instead of venv/")
    parser.add_argument("--playwright", action="store_true",
                        help="also download the Playwright Chromium engine")
    parser.add_argument("--orbit", action="store_true",
                        help="also install the Orbit browser npm dependencies")
    parser.add_argument("--precompile", action="store_true",
                        help="precompile bytecode after installing")
    args = parser.parse_args(argv)

    print()
    print("  JARVIS — Dependency Downloader")
    print("  ==============================")

    python = ensure_python(args.system)
    install_requirements(python)
    if args.playwright:
        install_playwright(python)
    if args.orbit:
        install_orbit()
    if args.precompile:
        precompile(python)

    print()
    ok("ALL DEPENDENCIES DOWNLOADED")
    print(f"       Interpreter: {python}")
    print("       Run the agent: python -m cli")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
