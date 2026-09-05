"""JARVIS Orbit — browser tool handlers (the Orbit control surface).

Every handler is a sync function returning :class:`tools.schema.ToolResult`;
the ToolExecutionService runs them via ``asyncio.to_thread``. They route
exclusively through :class:`BrowserController` (Orbit CDP backend) — the single
path to Chromium, satisfying the architecture contract: no tool bypasses
``ToolExecutionService`` and no protocol/agent path bypasses the controller.

Risk/gating: the declarative metadata (``risk``, ``is_destructive``,
``permission``) comes from the shared canonical classification in
``tools/classification`` via ``classify_tool``; approval for high/critical
actions is enforced by the central PermissionEngine, never here.
"""

from __future__ import annotations

import functools
from dataclasses import replace
from typing import Any

from core.locks import ResourceLockedError
from jbrowser.page_context import PageContext
from jbrowser.permissions import describe_permissions
from tools.classification import classify_tool
from tools.schema import Tool, ToolResult

from memory.keyspace import KIND_AGENT, owner_key
from orbit.controller import get_orbit_controller

MAX_OUTPUT = 8000


def _protect(handler: Any) -> Any:
    """Convert ownership contests into a structured ToolResult.

    The coordinator surfaces a deterministic RESOURCE_LOCKED signal when another
    owner (USER on the DSH, or a sibling AGENT) holds the tab. Handlers stay
    thin: they never decide access — they just translate the lock into an
    auditable, schema-shaped failure instead of a raw exception.
    """

    @functools.wraps(handler)
    def wrapped(args: dict[str, Any]) -> ToolResult:
        try:
            return handler(args)
        except ResourceLockedError as e:
            return ToolResult(
                success=False,
                error=f"RESOURCE_LOCKED: tab '{e.key}' is owned by '{e.owner}'",
                metadata={"reason": "RESOURCE_LOCKED", "key": e.key, "owner": e.owner},
            )

    return wrapped


def orbit_new_tab(args: dict[str, Any]) -> ToolResult:
    url = str(args.get("url", "")).strip()
    try:
        tab = get_orbit_controller().new_tab(url)
    except ResourceLockedError:
        raise
    except Exception as e:
        return ToolResult(success=False, error=f"orbit new_tab failed: {e}")
    return ToolResult(
        success=True,
        output=f"Opened tab {tab['tab_id']} -> {tab['url'] or '(blank)'}",
        metadata=tab,
    )


def orbit_close_tab(args: dict[str, Any]) -> ToolResult:
    tab_id = str(args.get("tab_id", "")).strip()
    if not tab_id:
        return ToolResult(success=False, error="tab_id is required")
    res = get_orbit_controller().close_tab(tab_id)
    return ToolResult(
        success=res.get("closed", False),
        output=f"Closed tab {tab_id}" if res.get("closed") else f"Tab not found: {tab_id}",
        metadata={"tab_id": tab_id},
    )


def orbit_list_tabs(args: dict[str, Any]) -> ToolResult:
    tabs = get_orbit_controller().list_tabs()
    if not tabs:
        return ToolResult(success=True, output="No open tabs.")
    lines = []
    for t in tabs:
        marker = "ACTIVE" if t.get("active") else "     "
        lines.append(
            f"{marker} {t.get('tab_id')} [{t.get('session_id')}] "
            f"{t.get('title') or ''} {t.get('url') or ''}"
        )
    return ToolResult(success=True, output="\n".join(lines), metadata={"tabs": tabs})


def orbit_activate_tab(args: dict[str, Any]) -> ToolResult:
    tab_id = str(args.get("tab_id", "")).strip()
    if not tab_id:
        return ToolResult(success=False, error="tab_id is required")
    try:
        info = get_orbit_controller().switch_tab(tab_id)
    except ResourceLockedError:
        raise
    except Exception as e:
        return ToolResult(success=False, error=str(e))
    return ToolResult(
        success=True,
        output=f"Activated tab {tab_id} -> {info.get('url', '')}",
        metadata=info,
    )


def orbit_navigate(args: dict[str, Any]) -> ToolResult:
    url = str(args.get("url", "")).strip()
    tab_id = args.get("tab_id")
    if not url:
        return ToolResult(success=False, error="url is required")
    try:
        result = get_orbit_controller().navigate(url, tab_id)
    except ResourceLockedError:
        raise
    except Exception as e:
        return ToolResult(success=False, error=f"Failed to open {url}: {e}")
    return ToolResult(
        success=True,
        output=f"Title: {result.get('title', '')}\nURL: {result.get('url', url)}",
        metadata=result,
    )


def orbit_read(args: dict[str, Any]) -> ToolResult:
    tab_id = args.get("tab_id")
    try:
        ctx: PageContext = get_orbit_controller().read(tab_id)
    except ResourceLockedError:
        raise
    except Exception as e:
        return ToolResult(success=False, error=f"read failed: {e}")
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
            "text_len": len(ctx.text or ""),
        },
    )


def orbit_back(args: dict[str, Any]) -> ToolResult:
    try:
        get_orbit_controller().go_back(args.get("tab_id"))
    except ResourceLockedError:
        raise
    except Exception as e:
        return ToolResult(success=False, error=f"go_back failed: {e}")
    return ToolResult(success=True, output="Went back")


def orbit_forward(args: dict[str, Any]) -> ToolResult:
    try:
        get_orbit_controller().go_forward(args.get("tab_id"))
    except ResourceLockedError:
        raise
    except Exception as e:
        return ToolResult(success=False, error=f"go_forward failed: {e}")
    return ToolResult(success=True, output="Went forward")


def orbit_reload(args: dict[str, Any]) -> ToolResult:
    try:
        get_orbit_controller().reload(args.get("tab_id"))
    except ResourceLockedError:
        raise
    except Exception as e:
        return ToolResult(success=False, error=f"reload failed: {e}")
    return ToolResult(success=True, output="Reloaded")


def orbit_click(args: dict[str, Any]) -> ToolResult:
    handle = str(args.get("handle", "") or args.get("selector", "")).strip()
    tab_id = args.get("tab_id")
    if not handle:
        return ToolResult(success=False, error="handle is required (use [elN] handles from browser.read)")
    try:
        res = get_orbit_controller().click(handle, tab_id)
    except ResourceLockedError:
        raise
    except Exception as e:
        return ToolResult(success=False, error=f"Click failed ({handle}): {e}")
    return ToolResult(success=True, output=f"Clicked {handle}", metadata=res)


def orbit_type(args: dict[str, Any]) -> ToolResult:
    handle = str(args.get("handle", "") or args.get("selector", "")).strip()
    text = str(args.get("text", "") or "")
    tab_id = args.get("tab_id")
    if not handle:
        return ToolResult(success=False, error="handle is required")
    try:
        res = get_orbit_controller().type_text(handle, text, tab_id)
    except ResourceLockedError:
        raise
    except Exception as e:
        return ToolResult(success=False, error=f"Type failed ({handle}): {e}")
    return ToolResult(success=True, output=f"Typed {len(text)} chars into {handle}", metadata=res)


def orbit_scroll(args: dict[str, Any]) -> ToolResult:
    direction = str(args.get("direction", "down")).strip()
    amount = int(args.get("amount", 500))
    tab_id = args.get("tab_id")
    try:
        get_orbit_controller().scroll(direction, amount, tab_id)
    except ResourceLockedError:
        raise
    except ValueError as e:
        return ToolResult(success=False, error=str(e))
    except Exception as e:
        return ToolResult(success=False, error=f"Scroll failed: {e}")
    return ToolResult(success=True, output=f"Scrolled {direction}")


def orbit_screenshot(args: dict[str, Any]) -> ToolResult:
    tab_id = args.get("tab_id")
    try:
        path = get_orbit_controller().screenshot(tab_id)
    except ResourceLockedError:
        raise
    except Exception as e:
        return ToolResult(success=False, error=f"Screenshot unavailable: {e}")
    return ToolResult(success=True, output=f"Screenshot saved to {path}", metadata={"path": path})


def orbit_status(args: dict[str, Any]) -> ToolResult:
    status = get_orbit_controller().status()
    return ToolResult(
        success=True,
        output=(
            f"Orbit backend: {status['backend']} "
            f"(available={status['available']}, launched={status['launched']}, "
            f"headless={status['headless']}). Tabs: {status['tabs']}."
        ),
        metadata=status,
    )


def orbit_permissions(args: dict[str, Any]) -> ToolResult:
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


def orbit_import_passwords(args: dict[str, Any]) -> ToolResult:
    """Analyze a pasted credentials CSV and return a masked import plan.

    Guidance only: no password value is persisted, logged, or returned. The
    plan keeps per-account presence/strength flags and user-side actions.
    """
    from orbit.wizard import run_import_analysis

    csv_text = str(args.get("csv") or "")
    if not csv_text.strip():
        return ToolResult(success=False, error="csv is required")
    try:
        plan = run_import_analysis(csv_text)
    except ValueError as e:
        return ToolResult(success=False, error=f"invalid CSV: {e}")
    return ToolResult(
        success=True,
        output=plan.to_text(),
        metadata={
            "accounts": plan.total,
            "needs_password": len(plan.needs_password),
            "weak_passwords": len(plan.weak_passwords),
            "duplicates": len(plan.duplicates),
            "sensitive_sites": len(plan.sensitive_sites),
            "parse_errors": len(plan.parse_errors),
        },
    )


def _memory_owner(args: dict[str, Any]) -> str:
    """Resolve the canonical owner string from tool args (G12).

    The tool surface exposes ``user`` and ``agent`` ownership only; ``system``
    namespaces are reserved for runtime callers at the store level.
    """
    owner_kind = str(args.get("owner") or "user").strip().lower()
    agent_id = str(args.get("agent_id") or "").strip()
    if owner_kind == "agent":
        if not agent_id:
            raise ValueError("owner='agent' requires agent_id")
        return owner_key(KIND_AGENT, agent_id)
    if owner_kind == "user":
        return "user"
    raise ValueError(f"owner must be 'user' or 'agent' (got {owner_kind!r})")


def orbit_memory_remember(args: dict[str, Any]) -> ToolResult:
    """Persist a text memory under the constellation keyspace (G12)."""
    from orbit.memory import get_orbit_memory

    key = str(args.get("key") or "").strip()
    value = str(args.get("value") or "")
    if not key or not value.strip():
        return ToolResult(success=False, error="key and value are required")
    try:
        owner = _memory_owner(args)
        get_orbit_memory().store_owned(
            key, value, owner=owner,
            category=str(args.get("category") or "general")[:64],
        )
    except (ValueError, PermissionError) as e:
        return ToolResult(success=False, error=f"memory_remember failed: {e}")
    return ToolResult(success=True, output=f"remembered {key}",
                      metadata={"key": key, "owner": owner})


def orbit_memory_recall(args: dict[str, Any]) -> ToolResult:
    """Recall a memory by key or search value content (G12).

    Reads are scoped to the caller's ownership claim: an agent never sees a
    sibling agent's private namespace.
    """
    from orbit.memory import get_orbit_memory

    key = str(args.get("key") or "").strip()
    query = str(args.get("query") or "").strip()
    if not key and not query:
        return ToolResult(success=False, error="key or query is required")
    try:
        owner = _memory_owner(args)
    except ValueError as e:
        return ToolResult(success=False, error=f"memory_recall failed: {e}")
    store = get_orbit_memory()
    if key:
        value = store.recall(key, owner=owner)
        if value is None:
            return ToolResult(success=False,
                              error=f"no memory at {key} readable by {owner}")
        return ToolResult(success=True,
                          output=value[:MAX_OUTPUT] or "(empty)",
                          metadata={"key": key, "owner": owner})
    hits = store.search(query, limit=8, owner=owner)
    if not hits:
        return ToolResult(success=False, error=f"no memories match {query!r}")
    lines = [f"- {h['key']}: {(h['value'] or '')[:240]}" for h in hits]
    return ToolResult(success=True, output="\n".join(lines),
                      metadata={"hits": len(hits), "owner": owner})


def orbit_memory_forget(args: dict[str, Any]) -> ToolResult:
    """Delete a memory the caller owns (G12)."""
    from orbit.memory import get_orbit_memory

    key = str(args.get("key") or "").strip()
    if not key:
        return ToolResult(success=False, error="key is required")
    try:
        owner = _memory_owner(args)
        deleted = get_orbit_memory().delete_owned(key, owner)
    except (ValueError, PermissionError) as e:
        return ToolResult(success=False, error=f"memory_forget failed: {e}")
    return ToolResult(success=deleted, output=f"forgotten {key}" if deleted
                      else f"no memory at {key}",
                      metadata={"key": key, "owner": owner, "deleted": deleted})


def orbit_memory_artifact_save(args: dict[str, Any]) -> ToolResult:
    """Store a binary artifact (base64 in) under the keyspace (G12 BLOB)."""
    import base64 as _b64

    from orbit.memory import get_orbit_memory

    key = str(args.get("key") or "").strip()
    data_b64 = str(args.get("data_base64") or "")
    if not key or not data_b64:
        return ToolResult(success=False, error="key and data_base64 are required")
    try:
        data = _b64.b64decode(data_b64, validate=True)
        owner = _memory_owner(args)
        size = get_orbit_memory().put_blob(
            key, data, owner=owner,
            mime=str(args.get("mime") or "application/octet-stream")[:128],
            meta=str(args.get("meta") or "")[:512],
        )
    except (ValueError, PermissionError) as e:
        return ToolResult(success=False, error=f"artifact_save failed: {e}")
    return ToolResult(success=True, output=f"stored artifact {key}",
                      metadata={"key": key, "owner": owner, "size": size})


def orbit_memory_artifact_get(args: dict[str, Any]) -> ToolResult:
    """Fetch an artifact's metadata + payload (base64 out) (G12 BLOB)."""
    import base64 as _b64

    from orbit.memory import get_orbit_memory

    key = str(args.get("key") or "").strip()
    if not key:
        return ToolResult(success=False, error="key is required")
    try:
        owner = _memory_owner(args)
        blob = get_orbit_memory().get_blob(key, owner=owner)
    except ValueError as e:
        return ToolResult(success=False, error=f"artifact_get failed: {e}")
    if blob is None:
        return ToolResult(success=False,
                          error=f"no artifact at {key} readable by {owner}")
    return ToolResult(
        success=True,
        output=(f"artifact {key}: {blob['mime']} ({blob['size']} bytes)"),
        metadata={
            "key": key, "owner": owner, "mime": blob["mime"],
            "size": blob["size"], "data_base64": _b64.b64encode(
                blob["data"]).decode("ascii"),
        },
    )


def orbit_extract(args: dict[str, Any]) -> ToolResult:
    """Alias -- selectable text from the whole page or a CSS selector."""
    selector = args.get("selector")
    tab_id = args.get("tab_id")
    try:
        text = get_orbit_controller().extract_text(selector, tab_id)
    except ResourceLockedError:
        raise
    except Exception as e:
        return ToolResult(success=False, error=f"extract failed: {e}")
    return ToolResult(
        success=True,
        output=text[:MAX_OUTPUT] if text else "(no text)",
        metadata={"chars": len(text or "")},
    )


def orbit_execute_script(args: dict[str, Any]) -> ToolResult:
    script = str(args.get("script", "") or "")
    tab_id = args.get("tab_id")
    if not script.strip():
        return ToolResult(success=False, error="script is required")
    try:
        out = get_orbit_controller().execute_script(script, tab_id)
    except ResourceLockedError:
        raise
    except Exception as e:
        return ToolResult(success=False, error=f"execute_script failed: {e}")
    return ToolResult(success=True, output=out[:MAX_OUTPUT], metadata={"len": len(out)})


# ---------------------------------------------------------------------------
# Canonical tool declarations (classified by the shared classification engine).
# ---------------------------------------------------------------------------

_ORBIT_TOOLS: list[Tool] = [
    Tool(
        name="orbit.new_tab",
        description="Open a new tab in the JARVIS Orbit browser.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to open (scheme optional)."},
            },
            "required": [],
        },
        permission="orbit.browser",
        handler=orbit_new_tab,
        category="orbit",
    ),
    Tool(
        name="orbit.close_tab",
        description="Close a tab by its stable tab_id.",
        parameters={
            "type": "object",
            "properties": {
                "tab_id": {"type": "string", "description": "tab_id of the tab to close."},
            },
            "required": ["tab_id"],
        },
        permission="orbit.browser",
        handler=orbit_close_tab,
        category="orbit",
    ),
    Tool(
        name="orbit.list_tabs",
        description="List all open tabs with their stable tab_id.",
        parameters={"type": "object", "properties": {}, "required": []},
        permission="orbit.browser",
        handler=orbit_list_tabs,
        category="orbit",
    ),
    Tool(
        name="orbit.activate_tab",
        description="Make a tab the active tab for subsequent operations.",
        parameters={
            "type": "object",
            "properties": {
                "tab_id": {"type": "string", "description": "tab_id to activate."},
            },
            "required": ["tab_id"],
        },
        permission="orbit.browser",
        handler=orbit_activate_tab,
        category="orbit",
    ),
    Tool(
        name="orbit.navigate",
        description="Navigate the active (or named) tab to a URL. "
        "Public destinations only; private/loopback destinations are denied.",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Destination URL."},
                "tab_id": {"type": "string", "description": "Optional tab_id (default active)."},
            },
            "required": ["url"],
        },
        permission="orbit.browser.open",
        handler=orbit_navigate,
        category="orbit",
    ),
    Tool(
        name="orbit.read",
        description="Read the current (or named) page: URL, title, interactive "
        "elements with [elN] handles, links, and visible text.",
        parameters={
            "type": "object",
            "properties": {
                "tab_id": {"type": "string", "description": "Optional tab_id (default active)."},
            },
            "required": [],
        },
        permission="orbit.browser",
        handler=orbit_read,
        category="orbit",
    ),
    Tool(
        name="orbit.back",
        description="Navigate back in history.",
        parameters={
            "type": "object",
            "properties": {"tab_id": {"type": "string"}},
            "required": [],
        },
        permission="orbit.browser",
        handler=orbit_back,
        category="orbit",
    ),
    Tool(
        name="orbit.forward",
        description="Navigate forward in history.",
        parameters={
            "type": "object",
            "properties": {"tab_id": {"type": "string"}},
            "required": [],
        },
        permission="orbit.browser",
        handler=orbit_forward,
        category="orbit",
    ),
    Tool(
        name="orbit.reload",
        description="Reload the current page.",
        parameters={
            "type": "object",
            "properties": {"tab_id": {"type": "string"}},
            "required": [],
        },
        permission="orbit.browser",
        handler=orbit_reload,
        category="orbit",
    ),
    Tool(
        name="orbit.click",
        description="Click an interactive element by its [elN] handle (from orbit.read).",
        parameters={
            "type": "object",
            "properties": {
                "handle": {"type": "string", "description": "elN handle."},
                "tab_id": {"type": "string"},
            },
            "required": ["handle"],
        },
        permission="orbit.browser.act",
        handler=orbit_click,
        category="orbit",
    ),
    Tool(
        name="orbit.type",
        description="Type text into an input by its [elN] handle (from orbit.read).",
        parameters={
            "type": "object",
            "properties": {
                "handle": {"type": "string", "description": "elN handle."},
                "text": {"type": "string", "description": "Text to type."},
                "tab_id": {"type": "string"},
            },
            "required": ["handle", "text"],
        },
        permission="orbit.browser.act",
        handler=orbit_type,
        category="orbit",
    ),
    Tool(
        name="orbit.scroll",
        description="Scroll the page up/down/top/bottom.",
        parameters={
            "type": "object",
            "properties": {
                "direction": {"enum": ["up", "down", "top", "bottom"], "type": "string"},
                "amount": {"type": "integer"},
                "tab_id": {"type": "string"},
            },
            "required": [],
        },
        permission="orbit.browser",
        handler=orbit_scroll,
        category="orbit",
    ),
    Tool(
        name="orbit.screenshot",
        description="Capture a screenshot of the current (or named) tab.",
        parameters={
            "type": "object",
            "properties": {"tab_id": {"type": "string"}},
            "required": [],
        },
        permission="orbit.browser.screenshot",
        handler=orbit_screenshot,
        category="orbit",
    ),
    Tool(
        name="orbit.status",
        description="Report the Orbit browser backend/tab status.",
        parameters={"type": "object", "properties": {}, "required": []},
        permission="orbit.browser",
        handler=orbit_status,
        category="orbit",
    ),
    Tool(
        name="orbit.permissions",
        description="Describe the current browser permission model (LOW/MEDIUM/HIGH).",
        parameters={"type": "object", "properties": {}, "required": []},
        permission="orbit.browser",
        handler=orbit_permissions,
        category="orbit",
    ),
    Tool(
        name="orbit.extract",
        description="Extract visible text from a CSS selector (or the whole page).",
        parameters={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Optional CSS selector."},
                "tab_id": {"type": "string"},
            },
            "required": [],
        },
        permission="orbit.browser",
        handler=orbit_extract,
        category="orbit",
    ),
    Tool(
        name="orbit.execute_script",
        description="Run JavaScript in the page. High risk; requires consent.",
        parameters={
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "JavaScript to run."},
                "tab_id": {"type": "string"},
            },
            "required": ["script"],
        },
        permission="orbit.browser.script",
        handler=orbit_execute_script,
        category="orbit",
    ),
    Tool(
        name="orbit.import_passwords",
        description="Analyze a pasted site-credentials CSV and return a masked "
        "import plan (accounts to add, weak/duplicate/sensitive flags, "
        "guidance). Guidance only: no password value is stored, logged, or "
        "returned.",
        parameters={
            "type": "object",
            "properties": {
                "csv": {"type": "string",
                        "description": "CSV text: site,url,username,password."},
            },
            "required": ["csv"],
        },
        permission="orbit.credentials",
        handler=orbit_import_passwords,
        category="orbit",
    ),
    Tool(
        name="orbit.memory_remember",
        description="Persist a text memory under the constellation keyspace. "
        "Keys must be namespaced: user.<domain>.<name>, agent.<agent_id>.<domain>."
        "<name>, or system.<domain>.<name>; the caller may only write its own "
        "namespace (owner + agent_id).",
        parameters={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
                "owner": {"type": "string", "enum": ["user", "agent"]},
                "agent_id": {"type": "string"},
                "category": {"type": "string"},
            },
            "required": ["key", "value"],
        },
        permission="orbit.memory",
        handler=orbit_memory_remember,
        category="orbit",
    ),
    Tool(
        name="orbit.memory_recall",
        description="Recall a memory by key or search its content. Reads are "
        "scoped to the caller's ownership claim (owner + agent_id); an agent "
        "never sees a sibling agent's private namespace.",
        parameters={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "query": {"type": "string"},
                "owner": {"type": "string", "enum": ["user", "agent"]},
                "agent_id": {"type": "string"},
            },
            "required": [],
        },
        permission="orbit.memory",
        handler=orbit_memory_recall,
        category="orbit",
    ),
    Tool(
        name="orbit.memory_forget",
        description="Delete a memory the caller owns (constellation keyspace "
        "ownership enforced; cannot delete outside your namespace).",
        parameters={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "owner": {"type": "string", "enum": ["user", "agent"]},
                "agent_id": {"type": "string"},
            },
            "required": ["key"],
        },
        permission="orbit.memory",
        handler=orbit_memory_forget,
        category="orbit",
        # Not flagged destructive: deletion is bounded to the caller's own
        # namespace by the constellation ownership guard (user/system/sibling
        # keys are unreachable), so it stays low-risk and auto-approved.
    ),
    Tool(
        name="orbit.memory_artifact_save",
        description="Store a binary artifact (base64 data) under the "
        "constellation keyspace. Blobs never appear in text recall/search; "
        "retrieve by key reference.",
        parameters={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "data_base64": {"type": "string"},
                "mime": {"type": "string"},
                "meta": {"type": "string"},
                "owner": {"type": "string", "enum": ["user", "agent"]},
                "agent_id": {"type": "string"},
            },
            "required": ["key", "data_base64"],
        },
        permission="orbit.memory",
        handler=orbit_memory_artifact_save,
        category="orbit",
    ),
    Tool(
        name="orbit.memory_artifact_get",
        description="Fetch an artifact's metadata and base64 payload by key "
        "reference (owner-scoped).",
        parameters={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "owner": {"type": "string", "enum": ["user", "agent"]},
                "agent_id": {"type": "string"},
            },
            "required": ["key"],
        },
        permission="orbit.memory",
        handler=orbit_memory_artifact_get,
        category="orbit",
    ),
]

def build_orbit_tools() -> list[Tool]:
    """Return the classified Orbit tool catalog (safe to register many).

    Every handler is wrapped so ownership contests surface as structured
    RESOURCE_LOCKED ToolResults; the declarative metadata (risk, retry
    semantics, concurrency) comes from the shared classification engine.
    """
    return [
        classify_tool(_with_protected_handler(tool)) for tool in _ORBIT_TOOLS
    ]


def _with_protected_handler(tool: Tool) -> Tool:
    return replace(tool, handler=_protect(tool.handler))