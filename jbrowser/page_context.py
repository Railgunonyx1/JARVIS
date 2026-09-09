"""J-Browser — page understanding layer.

Builds a compact, structured :class:`PageContext` from a rendered page so the
model can reason over a typed snapshot instead of a giant screenshot. The
interactive elements carry *stable handles* that the structured action tools
(``click``/``type``/``select``/``submit``) target — auditable, testable,
permission-aware and replayable (browser-use / accessibility-tree pattern).
Screenshot remains a secondary perception mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MAX_CTX_TEXT = 6000
MAX_INTERACTIVES = 60
# Bound the per-element scan on very large pages (e.g. ~100K-node DOMs) so a
# single read never walks the whole tree; handles are stable within the scan.
MAX_SCAN_ELEMENTS = 200

# Global generation counter: incremented on every full page context build.
# Element handles include this generation so stale handles from a previous
# DOM state can be detected and rejected.
_generation: int = 0


@dataclass
class PageContext:
    """A structured snapshot of the current (or named) page."""

    url: str = ""
    title: str = ""
    text: str = ""
    interactives: list[dict[str, Any]] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    forms: list[dict[str, Any]] = field(default_factory=list)
    viewport: dict[str, Any] = field(default_factory=dict)

    generation: int = 0

    def to_prompt_block(self) -> str:
        """Render a compact representation suitable for model context."""
        lines = [f"URL: {self.url}", f"Title: {self.title}"]
        if self.interactives:
            lines.append(f"\nInteractive elements (gen={self.generation}):")
            for el in self.interactives[:MAX_INTERACTIVES]:
                lines.append(
                    f"  [{el.get('handle')}] <{el.get('tag')}> "
                    f"{el.get('kind', '')} {el.get('label') or el.get('text') or ''}"
                )
        if self.links:
            lines.append(f"\nLinks ({len(self.links)}): " + ", ".join(self.links[:20]))
        if self.text:
            body = self.text if len(self.text) <= MAX_CTX_TEXT else self.text[:MAX_CTX_TEXT]
            lines.append("\nPage text:\n" + body)
        return "\n".join(lines)


def build_page_context(page: Any) -> PageContext:
    """Extract a PageContext from a Playwright-like page object.

    ``page`` duck-types the minimal surface we actually use so tests can pass
    a fake and engines can be swapped:
        - ``.url``, ``.title()``, ``.evaluate(js, arg)``
        - ``.query_selector_all(sel)`` returning elements with
          ``.get_attribute(name)``, ``.inner_text()``
    """
    global _generation
    _generation += 1
    ctx = PageContext(
        url=str(getattr(page, "url", "") or ""),
        title=_safe_title(page),
        generation=_generation,
    )
    try:
        ctx.text = (page.evaluate("() => document.body.innerText") or "")[:20000]
    except Exception:
        ctx.text = ""
    ctx.links = _extract_links(page)
    ctx.interactives = _extract_interactives(page, generation=_generation)
    ctx.viewport = _extract_viewport(page)
    ctx.forms = _extract_forms(page)
    return ctx


def _safe_title(page: Any) -> str:
    try:
        t = page.title() or ""
        return str(t)
    except Exception:
        return ""


_SELECTOR = (
    "a[href], button, input, select, textarea, [role='button'], "
    "[role='link'], [role='textbox'], [contenteditable='true']"
)

_INTERESTING = ("a", "button", "input", "select", "textarea")


def parse_handle(handle: str) -> tuple[int, int] | None:
    """Parse an element handle string and return (index, generation) or None.

    Handles are formatted as ``el<idx>_g<generation>``.  Returns None if the
    handle is malformed.
    """
    if not handle.startswith("el"):
        return None
    try:
        parts = handle.split("_g")
        idx = int(parts[0][2:])
        gen = int(parts[1]) if len(parts) > 1 else 0
        return (idx, gen)
    except (ValueError, IndexError):
        return None


def is_handle_stale(handle: str, current_generation: int) -> bool:
    """Return True if the handle's generation doesn't match the current one."""
    parsed = parse_handle(handle)
    if parsed is None:
        return True
    return parsed[1] != current_generation


def _extract_interactives(page: Any, generation: int = 0) -> list[dict[str, Any]]:
    """Map DOM elements to generation-bound handles.

    Handles are formatted as ``el_<idx>_g<generation>`` so stale handles from
    a previous DOM scan can be detected.  The generation is included in the
    prompt block so the model knows when handles are outdated.
    """
    out: list[dict[str, Any]] = []
    try:
        elements = page.query_selector_all(_SELECTOR)
    except Exception:
        return out
    for idx, el in enumerate(elements[:MAX_SCAN_ELEMENTS]):
        handle = f"el{idx}_g{generation}"
        try:
            tag = (el.evaluate("e => e.tagName") or "").lower()
        except Exception:
            tag = "?"
        try:
            selector = el.evaluate(
                "e => { let s = e.tagName.toLowerCase();"
                " if (e.id) return s + '#' + e.id;"
                " if (e.name) return s + '[name="' + e.name + '"]';"
                " let p = e.parentElement;"
                " if (p) { let ci = Array.from(p.children).indexOf(e);"
                " return p.tagName.toLowerCase() + ' > ' + s + ':nth-child(' + (ci+1) + ')'; }"
                " return s; }"
            ) or ""
        except Exception:
            selector = ""
        out.append({
            "handle": handle,
            "tag": tag,
            "kind": _kind(tag),
            "label": _attr(el, "aria-label"),
            "text": _attr(el, "inner_text"),
            "href": _attr(el, "href"),
            "selector": selector[:200],
            "generation": generation,
        })
    return out[:MAX_INTERACTIVES]


def _extract_links(page: Any) -> list[str]:
    try:
        return (page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => e.href).filter(Boolean)",
        ) or [])[:200]
    except Exception:
        return []


def _extract_viewport(page: Any) -> dict[str, Any]:
    try:
        vp = page.evaluate(
            "() => ({w: window.innerWidth, h: window.innerHeight})"
        ) or {}
        return dict(vp)
    except Exception:
        return {}


def _extract_forms(page: Any) -> list[dict[str, Any]]:
    try:
        forms = page.query_selector_all("form")
    except Exception:
        return []
    result = []
    for form in forms:
        result.append({"action": _attr(form, "action"), "method": _attr(form, "method") or "get"})
    return result


def _kind(tag: str) -> str:
    if tag == "a":
        return "link"
    if tag == "button":
        return "button"
    if tag == "input":
        return "input"
    if tag == "select":
        return "select"
    if tag == "textarea":
        return "textarea"
    return "widget"


def _attr(el: Any, name: str) -> str:
    try:
        value = el.get_attribute(name)
        if value:
            return str(value)[:200]
        if name == "inner_text":
            try:
                return (el.inner_text() or "")[:200]
            except Exception:
                return ""
    except Exception:
        return ""
    return ""
