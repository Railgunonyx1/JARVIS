"""JARVIS Orbit — controller facade bound to the CDP backend.

Reuses the canonical :class:`jbrowser.controller.BrowserController` facade
(events, sessions, locks) but binds it to the Orbit CDP backend instead of the
Playwright engine used by J-Browser unit tests. This is the single
``get_orbit_controller()`` path every Orbit tool routes through, keeping the
"one engine process per product" discipline while sharing the agent contract.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from jbrowser.controller import BrowserController

from orbit.cdp import CDPBackend


def make_orbit_backend(
    *,
    headless: bool | None = None,
    profile_dir: Path | None = None,
    extension_dir: Path | None = None,
    chrome: str | Path | None = None,
) -> CDPBackend:
    """Construct the Orbit CDP backend from (overridable) configuration.

    Runtime resolution order for Chromium: explicit ``chrome`` arg, then the
    ``J_BROWSER_CHROMIUM_PATH`` environment variable, then the Playwright
    build (all resolved inside :class:`CDPBackend`). Orbit never touches the
    user's installed Chrome profile.
    """
    headless = headless if headless is not None else (
        os.environ.get("ORBIT_HEADLESS", "") not in ("", "0", "false")
    )
    return CDPBackend(
        chrome=chrome,
        profile_dir=profile_dir or Path("config/browser_profiles/orbit"),
        headless=headless,
        extension_dir=extension_dir,
        auto_launch=True,
    )


_orbit_controller: BrowserController | None = None
_orbit_lock = threading.Lock()


def get_orbit_controller(*, backend: CDPBackend | None = None) -> BrowserController:
    """Module-level singleton controller bound to the Orbit backend.

    Pass ``backend`` on first call to inject a fake CDP backend for tests.
    """
    global _orbit_controller
    if _orbit_controller is None:
        with _orbit_lock:
            if _orbit_controller is None:
                _orbit_controller = BrowserController(
                    backend=backend or make_orbit_backend(),
                    profile_root=Path("."),
                )
    return _orbit_controller


def reset_orbit_controller() -> None:
    """Drop the singleton (for tests / shutdown)."""
    global _orbit_controller
    if _orbit_controller is not None:
        try:
            _orbit_controller.shutdown()
        except Exception:
            pass
    _orbit_controller = None