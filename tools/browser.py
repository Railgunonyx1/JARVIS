"""Browser tools — Playwright/Chromium via J-Browser.

Handlers are sync (the executor runs them via ``asyncio.to_thread``). They
route through :func:`jbrowser.controller.get_controller` so there is exactly
one engine path (a single Playwright process) for every browser tool — the
legacy and J-Browser tool sets share the same controller and backend.

Playwright is optional: when unavailable the backend keeps a WebScraper
fallback for read/navigation so the tools never hard-fail on installs.
"""

from __future__ import annotations

from typing import Any

from tools.schema import ToolResult, truncate

MAX_TEXT = 8000


def _controller():
    from jbrowser.controller import get_controller
    return get_controller()


def browser_status(args: dict[str, Any]) -> ToolResult:
    status = _controller().status()
    return ToolResult(
        success=True,
        output=(
            f"Browser backend: {status['backend']} "
            f"(launched={status['launched']}, headless={status['headless']}). "
            f"Fully available: {status['available']}."
        ),
        metadata=status,
    )


def browser_open(args: dict[str, Any]) -> ToolResult:
    url = str(args.get("url", "")).strip()
    if not url:
        return ToolResult(success=False, error="url is required")
    try:
        nav = _controller().navigate(url)
        page = _controller().read()
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to open {url}: {e}")
    text = truncate(page.text, MAX_TEXT)
    return ToolResult(
        success=True,
        output=(
            f"Title: {page.title}\n"
            f"URL: {nav.get('url', url)}\n"
            f"Backend: {_controller().status().get('backend', '?')}\n\n"
            f"{text}"
        ),
        metadata={
            "url": page.url or url,
            "title": page.title,
            "backend": _controller().status().get("backend", "?"),
            "links": page.links[:20],
        },
    )


def browser_screenshot(args: dict[str, Any]) -> ToolResult:
    try:
        path = _controller().screenshot()
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Screenshot unavailable: {e} (install playwright + chromium)",
        )
    return ToolResult(
        success=True,
        output=f"Screenshot saved to {path}",
        metadata={"path": path},
    )


def browser_click(args: dict[str, Any]) -> ToolResult:
    selector = str(args.get("selector", "")).strip()
    if not selector:
        return ToolResult(success=False, error="selector is required")
    try:
        _controller().click_selector(selector)
    except Exception as e:
        return ToolResult(success=False, error=f"Click failed ({selector}): {e}")
    return ToolResult(
        success=True,
        output=f"Clicked {selector}. Current URL: {_controller().current_url()}",
        metadata={"selector": selector, "url": _controller().current_url()},
    )


def browser_type(args: dict[str, Any]) -> ToolResult:
    selector = str(args.get("selector", "")).strip()
    text = str(args.get("text", "") or "")
    if not selector:
        return ToolResult(success=False, error="selector is required")
    try:
        _controller().type_selector(selector, text)
    except Exception as e:
        return ToolResult(success=False, error=f"Type failed ({selector}): {e}")
    return ToolResult(
        success=True,
        output=f"Typed {len(text)} chars into {selector}",
        metadata={"selector": selector, "chars": len(text)},
    )


def browser_extract(args: dict[str, Any]) -> ToolResult:
    try:
        text = _controller().extract_text(args.get("selector"))
    except Exception as e:
        return ToolResult(success=False, error=f"Extract failed: {e}")
    return ToolResult(
        success=True,
        output=truncate(text or "(empty)", MAX_TEXT),
        metadata={"selector": args.get("selector"), "chars": len(text or "")},
    )
