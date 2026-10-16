"""Guard: every class used by the Orbit shell markup must be styled.

The Orbit Electron shell (orbit-browser/src/index.html) is styled by the
stylesheets it links. A half-applied redesign once shipped markup whose class
names no stylesheet defined, so the shell collapsed (the sidebar laid its
children out in a row, the rail was unstyled, the AI drawer fell into normal
flow). This test fails if any class used in index.html is not defined by one
of the linked stylesheets, so that regression cannot recur silently.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ORBIT = ROOT / "orbit-browser" / "src"
INDEX = ORBIT / "index.html"

_CLASS_ATTR = re.compile(r"""class\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_CSS_HREF = re.compile(r"""<link[^>]+href\s*=\s*"(css/[^"]+\.css)\"""")
_CSS_CLASS = re.compile(r"\.([A-Za-z][\w-]*)")


def _used_classes(html: str) -> set[str]:
    used: set[str] = set()
    for m in _CLASS_ATTR.finditer(html):
        raw = m.group(1) or m.group(2) or ""
        used.update(raw.split())
    return used


def _linked_stylesheets(html: str) -> list[str]:
    return _CSS_HREF.findall(html)


def _defined_classes(orbit: Path, hrefs: list[str]) -> set[str]:
    defined: set[str] = set()
    for href in hrefs:
        path = orbit / href
        if not path.exists():
            continue
        defined.update(_CSS_CLASS.findall(path.read_text(encoding="utf-8")))
    return defined


pytestmark = pytest.mark.skipif(not INDEX.exists(), reason="orbit-browser not present")


def test_every_shell_class_is_styled():
    html = INDEX.read_text(encoding="utf-8")
    hrefs = _linked_stylesheets(html)
    assert hrefs, "index.html links no stylesheets"

    used = _used_classes(html)
    missing = sorted(used - _defined_classes(ORBIT, hrefs))

    assert not missing, (
        "index.html uses classes no linked stylesheet defines "
        f"({len(missing)}): " + ", ".join("." + c for c in missing)
    )


def test_shell_stylesheet_is_linked_last():
    hrefs = _linked_stylesheets(INDEX.read_text(encoding="utf-8"))
    assert hrefs[-1] == "css/orbit-shell.css", (
        "orbit-shell.css must be linked last so it overrides the legacy "
        f"shell rules (got {hrefs[-1]!r})"
    )


def test_shell_stylesheet_owns_the_grid():
    css = (ORBIT / "css" / "orbit-shell.css").read_text(encoding="utf-8")
    for selector in (".app", ".rail", ".sidebar", ".main", ".assistant"):
        assert re.search(
            re.escape(selector) + r"(?![\w-])", css
        ), f"orbit-shell.css does not define {selector}"
