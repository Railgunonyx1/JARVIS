"""J-Browser — agent tool handlers.

Every function here is a sync handler returning a :class:`ToolResult`; the
tool executor runs them via ``asyncio.to_thread`` (matching the rest of the
tool layer). They all route through :class:`BrowserController` — the single
path to the engine, satisfying the architecture contract (tools always pass
through ToolExecutionService; no tool bypasses it).

Risk: high-risk handlers (execute_script) rely on the permission engine gating
; the controller/backend does not enforce approval itself.
"""

from __future__ import annotations

from typing import Any

from jbrowser.controller import get_controller
from jbrowser.page_context import PageContext
from jbrowser.permissions import describe_permissions
from tools.schema import ToolResult, truncate

MAX_OUTPUT = 8000
MAX_CTX_TEXT = 5000


def browser_new_tab(args: dict[str, Any]) -> ToolResult:
    url = str(args.get("url", "")).strip()
    try:
        tab = get_controller().new_tab(url)
    except Exception as e:
        return ToolResult(success=False, error=f"new_tab failed: {e}")
    return ToolResult(
        success=True,
        output=f"Opened tab {tab['tab_id']} -> {tab['url'] or '(blank)'}",
        metadata=tab,
    )


def browser_close_tab(args: dict[str, Any]) -> ToolResult:
    tab_id = str(args.get("tab_id", "")).strip()
    if not tab_id:
        return ToolResult(success=False, error="tab_id is required")
    res = get_controller().close_tab(tab_id)
    return ToolResult(success=res.get("closed", False),
                      output=f"Closed tab {tab_id}" if res.get("closed") else f"Tab not found: {tab_id}",
                      metadata={"tab_id": tab_id})


def browser_tabs(args: dict[str, Any]) -> ToolResult:
    tabs = get_controller().list_tabs()
    if not tabs:
        return ToolResult(success=True, output="No open tabs.")
    lines = []
    for t in tabs:
        marker = "ACTIVE" if t.get("active") else "     "
        lines.append(f"{marker} {t.get('tab_id')} [{t.get('session_id')}] {t.get('title') or ''} {t.get('url') or ''}")
    return ToolResult(success=True, output="\n".join(lines), metadata={"tabs": tabs})


def browser_switch_tab(args: dict[str, Any]) -> ToolResult:
    tab_id = str(args.get("tab_id", "")).strip()
    if not tab_id:
        return ToolResult(success=False, error="tab_id is required")
    try:
        info = get_controller().switch_tab(tab_id)
    except Exception as e:
        return ToolResult(success=False, error=str(e))
    return ToolResult(success=True, output=f"Switched to tab {tab_id} -> {info.get('url', '')}",
                      metadata=info)


def browser_open(args: dict[str, Any]) -> ToolResult:
    url = str(args.get("url", "")).strip()
    if not url:
        return ToolResult(success=False, error="url is required")
    try:
        result = get_controller().navigate(url)
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to open {url}: {e}")
    return ToolResult(
        success=True,
        output=f"Title: {result.get('title','')}\nURL: {result.get('url', url)}",
        metadata=result,
    )


def browser_read(args: dict[str, Any]) -> ToolResult:
    tab_id = args.get("tab_id")
    try:
        ctx: PageContext = get_controller().read(tab_id)
    except Exception as e:
        return ToolResult(success=False, error=f"read failed: {e}")
    text = ctx.text or ""
    output = ctx.to_prompt_block()
    if len(output) > MAX_OUTPUT:
        output = output[:MAX_OUTPUT]
    return ToolResult(
        success=True,
        output=output,
        metadata={
            "url": ctx.url,
            "title": ctx.title,
            "interactive_count": len(ctx.interactives),
            "link_count": len(ctx.links),
            "form_count": len(ctx.forms),
            "text_len": len(text),
        },
    )


def browser_find(args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query", "")).strip()
    tab_id = args.get("tab_id")
    if not query:
        return ToolResult(success=False, error="query is required")
    controller = get_controller()
    ctx: PageContext = controller.read(tab_id)
    text = (ctx.text or "").lower()
    needle = query.lower()
    matches = []
    for i, line in enumerate(ctx.text.splitlines() if ctx.text else []):
        if needle in line.lower():
            matches.append(f"line {i}: {truncate(line.strip(), 200)}")
    count = text.count(needle)
    return ToolResult(
        success=True,
        output=f"Found {count} occurrence(s) of {query!r}." + ("\n" + "\n".join(matches[:15]) if matches else ""),
        metadata={"count": count, "matches": len(matches)},
    )


def browser_click(args: dict[str, Any]) -> ToolResult:
    handle = str(args.get("handle", "") or args.get("selector", "")).strip()
    tab_id = args.get("tab_id")
    if not handle:
        return ToolResult(success=False, error="handle is required (use the [elN] handles from browser.read)")
    try:
        res = get_controller().click(handle, tab_id)
    except Exception as e:
        return ToolResult(success=False, error=f"Click failed ({handle}): {e}")
    return ToolResult(success=True, output=f"Clicked {handle}", metadata=res)


def browser_type(args: dict[str, Any]) -> ToolResult:
    handle = str(args.get("handle", "") or args.get("selector", "")).strip()
    text = str(args.get("text", "") or "")
    tab_id = args.get("tab_id")
    if not handle:
        return ToolResult(success=False, error="handle is required")
    try:
        res = get_controller().type_text(handle, text, tab_id)
    except Exception as e:
        return ToolResult(success=False, error=f"Type failed ({handle}): {e}")
    return ToolResult(success=True, output=f"Typed {len(text)} chars into {handle}", metadata=res)


def browser_scroll(args: dict[str, Any]) -> ToolResult:
    direction = str(args.get("direction", "down")).strip()
    amount = int(args.get("amount", 500))
    tab_id = args.get("tab_id")
    try:
        get_controller().scroll(direction, amount, tab_id)
    except ValueError as e:
        return ToolResult(success=False, error=str(e))
    except Exception as e:
        return ToolResult(success=False, error=f"Scroll failed: {e}")
    return ToolResult(success=True, output=f"Scrolled {direction}")


def browser_screenshot(args: dict[str, Any]) -> ToolResult:
    tab_id = args.get("tab_id")
    try:
        path = get_controller().screenshot(tab_id)
    except Exception as e:
        return ToolResult(success=False,
                          error=f"Screenshot unavailable: {e} (install playwright + chromium)")
    return ToolResult(success=True, output=f"Screenshot saved to {path}", metadata={"path": path})


def browser_status(args: dict[str, Any]) -> ToolResult:
    status = get_controller().status()
    return ToolResult(
        success=True,
        output=(
            f"J-Browser backend: {status['backend']} "
            f"(available={status['available']}, launched={status['launched']}, "
            f"headless={status['headless']}). Tabs: {status['tabs']}. "
            f"Sessions: {len(status['sessions'])}."
        ),
        metadata=status,
    )


def browser_profile(args: dict[str, Any]) -> ToolResult:
    session_id = str(args.get("session_id", "")).strip()
    try:
        info = get_controller().session_info(session_id)
    except Exception as e:
        return ToolResult(success=False, error=str(e))
    if not info:
        return ToolResult(success=True, output="No browser session active yet. Open a tab first.")
    return ToolResult(
        success=True,
        output=(
            f"Session: {info.get('session_id')}\n"
            f"Persistent profile: {info.get('persistent')}\n"
            f"Profile dir: {info.get('profile_dir') or '(ephemeral)'}"
        ),
        metadata=info,
    )


def browser_permissions(args: dict[str, Any]) -> ToolResult:
    perms = describe_permissions()
    return ToolResult(
        success=True,
        output=(
            "LOW (auto): " + ", ".join(perms["low"]) + "\n"
            "MEDIUM: " + ", ".join(perms["medium"]) + "\n"
            "HIGH (requires approval): " + ", ".join(perms["high"])
        ),
        metadata=perms,
    )


def browser_extract(args: dict[str, Any]) -> ToolResult:
    """Legacy-alias -> browser.read (kept for backward compatibility)."""
    return browser_read(args)
