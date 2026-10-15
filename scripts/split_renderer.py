"""Split orbit-browser/src/js/renderer.js (4.6k lines) into feature modules.

Slices by stable `// ──` section-header comments (robust to inter-slice
edits), writing sibling files that load BEFORE renderer.js so the single
global scope still links all cross-references. Keeps infra + init tail in
renderer.js (< 2000 lines).

Ordering hazard: top-level bare event bindings like `el.onclick = foo`
resolve `foo` at load time. They are rewritten to closures
(`el.onclick = function(){ return foo.apply(this, arguments); }`) so
every binding resolves at CALL time and module load order is irrelevant.

Usage: python scripts/split_renderer.py
Verifies each marker is unique before slicing; aborts otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # cp1252-safe

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "orbit-browser" / "src" / "js" / "renderer.js"

# region -> marker of the header comment at that region's FIRST line
MARKERS = {
    "core": None,  # file start -> Reopen Closed Tab
    "tabs": "// ── Reopen Closed Tab",
    "sidebar": "// ── Sidebar Toggle / JARVIS Launch",
    "jarvis": "// ── Composer (DSH Native Integration)",
    "nav-tools": "// ── Zoom Controls",
    "menus": "// ── Vision Panel",
    "pages": "// ── Permissions Page (real allowlist)",
    "settings-ux": "// ── Close all popups",
    "data-pages": "// ── History (Chrome-style recent visits",
    "tail": "// ── Reader Mode (Safari/Brave-style)",
}

HEADER = """/* %(name)s - extracted from renderer.js by scripts/split_renderer.py.
 * Classic script, loads in the shared global scope before renderer.js.
 * Event bindings use closures so load order never matters.
 */
// ---------------------------------------------------------------------
"""


def find_markers(text: str) -> dict[str, int]:
    """Return {region: 0-based line index of marker start}."""
    lines = text.splitlines()
    positions: dict[str, int] = {}
    for region, marker in MARKERS.items():
        if marker is None:
            continue
        hits = [i for i, ln in enumerate(lines) if ln.startswith(marker)]
        if len(hits) != 1:
            print(f"[ABORT] marker {marker!r} matched {len(hits)} times")
            sys.exit(1)
        positions[region] = hits[0]
    return positions


_NON_FN = {"null", "undefined", "true", "false"}
BARE_ON = re.compile(
    r"^(\s*)([\w$]+\.(?:on[a-zA-Z_$][\w$]*|<[-a-zA-Z_$][\w$]*))\s*=\s*(async\s+)?([a-zA-Z_$][\w$]*)\s*;?\s*$"
)
BARE_ADD = re.compile(
    r"^(.*addEventListener\(\s*(?:[`'\"]\{\w+[`'\"]|[`'\"]\w+[`'\"]|\w+)\s*,\s*)([a-zA-Z_$][\w$]*)\s*(\)\s*;\s*)$"
)


def laprelim_rewrite(text: str) -> str:
    """Make top-level bare event handlers order-independent."""
    out: list[str] = []
    for ln in text.splitlines():
        m = BARE_ON.match(ln)
        if m and not ln.strip().startswith("//"):
            indent, target, _async, name = m.groups()
            if name not in _NON_FN:
                out.append(f"{indent}{target} = function() {{ return {name}.apply(this, arguments); }};")
                continue
        m = BARE_ADD.match(ln)
        if m and not ln.strip().startswith("//"):
            name = m.group(2)
            if name not in _NON_FN:
                out.append(
                    f"{m.group(1)}function() {{ return {name}.apply(this, arguments); }}{m.group(3)}"
                )
                continue
        out.append(ln)
    return "\n".join(out)


def main() -> None:
    text = RENDERER.read_text(encoding="utf-8")
    if "// ── Multi-file split" in text or text.startswith("/**\n * JARVIS Orbit — Renderer Process (split)"):
        print("[ABORT] renderer.js is already split — restore the monolithic file from git:\n"
              "        git checkout -- orbit-browser/src/js/renderer.js  (loses the working-tail edits)")
        sys.exit(1)
    lines = text.splitlines()
    pos = find_markers(text)

    order = ["core", "tabs", "sidebar", "jarvis", "nav-tools", "menus", "pages", "settings-ux", "data-pages"]
    regions: dict[str, list[str]] = {}

    # core: file start -> tabs marker; others are slices between markers.
    regions["core"] = lines[: pos["tabs"]]
    for a, b in zip(order[1:], order[2:] + ["tail"]):
        regions[a] = lines[pos[a] : pos[b]]
    regions["tail"] = lines[pos["tail"] :]

    for name in order:
        body = laprelim_rewrite("\n".join(regions[name]) + "\n")
        dest = ROOT / "orbit-browser" / "src" / "js" / f"{name}.js"
        dest.write_text(HEADER % {"name": name} + body, encoding="utf-8")
        print(f"[write] {dest.name:14s} {len(regions[name]):4d} src lines")

    # renderer.js = chrome tail only (infra lives in core.js, which must be
    # listed FIRST in index.html)
    joined = "\n".join(regions["tail"]) + "\n"
    marker = "/**\n * JARVIS Orbit"
    pointer = joined.find(marker)
    if pointer != -1:
        joined = joined[:pointer]
    joined = (
        "/**\n"
        " * JARVIS Orbit — Renderer Process (split)\n"
        " *\n"
        " * This file carries the browser chrome tail + init. Shared infra and"
        " * state live in core.js (review labels: DOM cache, error logger,\n"
        " * DOM refs, state, toast, matrix). Feature code lives in sibling\n"
        " * modules: tabs.js, sidebar.js, jarvis.js, nav-tools.js, menus.js,\n"
        " * pages.js, settings-ux.js, data-pages.js. Load order in index.html:\n"
        " * core.js FIRST, then modules, then this file LAST so init sees every\n"
        " * cross-file reference. Regenerate: python scripts/split_renderer.py\n"
        " */\n"
        "// ---------------------------------------------------------------------\n"
    ) + joined
    RENDERER.write_text(joined, encoding="utf-8")
    print(f"[write] renderer.js           {len(joined.splitlines()):4d} lines")


if __name__ == "__main__":
    main()