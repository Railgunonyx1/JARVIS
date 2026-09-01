"""Browser tools — Playwright-backed automation with WebScraper fallback.

Handlers are sync (the executor runs them via ``asyncio.to_thread``).
The underlying BrowserAgent is a session singleton: the browser launches
lazily on first use and stays warm across tool calls.
"""

from __future__ import annotations

from typing import Any

from tools.schema import ToolResult, truncate

MAX_TEXT = 8000


def _agent():
    from external.browser_agent import get_browser_agent
    return get_browser_agent()


def browser_status(args: dict[str, Any]) -> ToolResult:
    agent = _agent()
    status = agent.status()
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
        page = _agent().open(url)
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to open {url}: {e}")
    text = truncate(page.get("text", ""), MAX_TEXT)
    return ToolResult(
        success=True,
        output=(
            f"Title: {page.get('title', '')}\n"
            f"URL: {page.get('url', url)}\n"
            f"Backend: {page.get('backend', '?')}\n\n"
            f"{text}"
        ),
        metadata={
            "url": page.get("url", url),
            "title": page.get("title", ""),
            "backend": page.get("backend", "?"),
            "links": page.get("links", [])[:20],
            "fetch_ms": page.get("fetch_ms"),
        },
    )


def browser_screenshot(args: dict[str, Any]) -> ToolResult:
    try:
        path = _agent().screenshot(args.get("path"))
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
        _agent().click(selector)
    except Exception as e:
        return ToolResult(success=False, error=f"Click failed ({selector}): {e}")
    return ToolResult(
        success=True,
        output=f"Clicked {selector}. Current URL: {_agent().current_url()}",
        metadata={"selector": selector, "url": _agent().current_url()},
    )


def browser_type(args: dict[str, Any]) -> ToolResult:
    selector = str(args.get("selector", "")).strip()
    text = str(args.get("text", "") or "")
    if not selector:
        return ToolResult(success=False, error="selector is required")
    try:
        _agent().type_text(selector, text)
    except Exception as e:
        return ToolResult(success=False, error=f"Type failed ({selector}): {e}")
    return ToolResult(
        success=True,
        output=f"Typed {len(text)} chars into {selector}",
        metadata={"selector": selector, "chars": len(text)},
    )


def browser_extract(args: dict[str, Any]) -> ToolResult:
    try:
        text = _agent().extract_text(args.get("selector"))
    except Exception as e:
        return ToolResult(success=False, error=f"Extract failed: {e}")
    return ToolResult(
        success=True,
        output=truncate(text or "(empty)", MAX_TEXT),
        metadata={"selector": args.get("selector"), "chars": len(text or "")},
    )
