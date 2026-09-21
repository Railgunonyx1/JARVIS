"""browser.wait — wait for a selector/text/gone condition on the active page.

Derived from webdriverio's wait semantics (waitForDisplayed / waitForText /
waitUntil): after a click or SPA route change the agent needs a *condition*
wait instead of a blind sleep. Uses the jbrowser controller's
``execute_script`` so no new backend surface is required.

Note: ``execute_script`` returns the raw JS evaluation as a string
(truthy -> "true"). Every poll re-checks the live DOM, so short polls are
cheap and the agent never acts on a half-loaded page.
"""

from __future__ import annotations

import json
import time
from typing import Any

from tools.schema import ToolResult

MAX_TIMEOUT = 30.0
_POLL_S = 0.25


def _js_for(kind: str, value: str) -> str:
    lit = json.dumps(value)
    if kind == "selector":
        return f"!!document.querySelector({lit})"
    if kind == "gone":
        return f"!document.querySelector({lit})"
    # text
    return f"!!(document.body && document.body.innerText.includes({lit}))"


def browser_wait(args: dict[str, Any]) -> ToolResult:
    """Wait until a condition holds on the active page, then report it."""
    kind = str(args.get("condition", "")).strip()
    value = str(args.get("value", "")).strip()
    if kind not in ("selector", "text", "gone", "delay"):
        return ToolResult(
            success=False,
            error="condition must be one of: selector, text, gone, delay",
        )
    if kind in ("selector", "gone", "text") and not value:
        return ToolResult(success=False, error=f"condition '{kind}' requires 'value'.")

    timeout = min(float(args.get("timeout", 10.0)), MAX_TIMEOUT)

    if kind == "delay":
        waited = min(max(float(value or 1), 0.1), 5.0)
        time.sleep(waited)
        return ToolResult(success=True, output=f"Waited {waited:.1f}s.", metadata={"condition": "delay"})

    from jbrowser.controller import get_controller

    try:
        controller = get_controller()
    except Exception as e:  # noqa: BLE001
        return ToolResult(success=False, error=f"Browser unavailable: {e}")

    js = _js_for(kind, value)
    deadline = time.monotonic() + timeout
    last_err = ""
    while time.monotonic() < deadline:
        try:
            raw = controller.execute_script(js)
            if str(raw).strip().lower() in ("true", "1"):
                waited = round(timeout - (deadline - time.monotonic()), 2)
                return ToolResult(
                    success=True,
                    output=f"Condition met after {waited}s: {kind} '{value}'",
                    metadata={"condition": kind, "value": value, "waited_s": waited},
                )
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        time.sleep(_POLL_S)

    extra = f" (last error: {last_err})" if last_err else ""
    return ToolResult(
        success=False,
        error=f"Timeout after {timeout}s waiting for {kind} '{value}'{extra}",
    )


__all__ = ["browser_wait"]
