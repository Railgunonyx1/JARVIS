"""PDF tools — split/merge/extract/text/tables via pypdf + pdfplumber.

Derived from the repo-mine list (py-pdf/pypdf, jsvine/pdfplumber): the agent
can now read, split, merge and pull tables out of PDFs directly instead of
shelling out. All operations write only under the project root; extraction is
read-only.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from tools.schema import ToolResult, truncate

logger = logging.getLogger("jarvis.tools.pdf")

MAX_OUTPUT = 12000
MAX_BYTES = 100 * 1024 * 1024  # refuse absurd PDFs before parsing


def _root() -> Path:
    from core.project import ProjectContext
    return ProjectContext.discover().root_path


def _resolve(path_str: str) -> Path:
    """Resolve a user path against the project root (abs allowed inside)."""
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = _root() / p
    return p


def _check_readable(p: Path) -> ToolResult | None:
    if not p.exists():
        return ToolResult(success=False, error=f"Not found: {p}")
    if not p.is_file():
        return ToolResult(success=False, error=f"Not a file: {p}")
    if p.stat().st_size > MAX_BYTES:
        return ToolResult(success=False, error=f"File too large (> {MAX_BYTES // (1024*1024)} MB): {p}")
    return None


def _safe_dest(dest: Path) -> ToolResult | None:
    """Writes must land inside the project root."""
    try:
        dest.resolve().relative_to(_root().resolve())
    except ValueError:
        return ToolResult(success=False, error=f"Destination must be inside the project root: {dest}")
    return None


# ----------------------------------------------------------------- extract

def pdf_extract_text(args: dict[str, Any]) -> ToolResult:
    """Extract text from a PDF (all pages or a page range)."""
    path = _resolve(str(args.get("path", "")))
    if err := _check_readable(path):
        return err
    pages = args.get("pages")
    try:
        from pypdf import PdfReader
    except ImportError:
        return ToolResult(success=False, error="pypdf not installed (pip install pypdf)")

    try:
        reader = PdfReader(str(path))
        n = len(reader.pages)
        idx = range(n) if pages in (None, "") else _page_range(pages, n)
    except Exception as e:  # noqa: BLE001
        return ToolResult(success=False, error=f"Cannot read PDF: {e}")
    if not idx:
        return ToolResult(success=False, error=f"No valid pages in range '{pages}' (PDF has {n} pages).")

    parts: list[str] = []
    for i in idx:
        try:
            parts.append(f"--- page {i + 1} ---\n{reader.pages[i].extract_text() or ''}")
        except Exception as e:  # noqa: BLE001
            parts.append(f"--- page {i + 1} --- (extract failed: {e})")

    text = "\n\n".join(parts).strip()
    if not any(len(p.split("\n", 1)[-1].strip()) > 0 for p in parts):
        return ToolResult(success=False, error="No extractable text (scanned PDF? try OCR pipeline later).")
    return ToolResult(
        success=True,
        output=truncate(text, MAX_OUTPUT),
        metadata={"pages": n, "pages_extracted": len(parts), "path": str(path)},
    )


def _page_range(spec: str, n: int) -> list[int]:
    """Parse '0', '2-4', '1,3,5-7' (1-based) into valid indices."""
    out: set[int] = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            lo, hi = int(a) - 1, int(b) - 1
            out.update(range(max(0, lo), min(hi, n - 1) + 1))
        else:
            i = int(part) - 1
            if 0 <= i < n:
                out.add(i)
    return sorted(out)


def pdf_extract_tables(args: dict[str, Any]) -> ToolResult:
    """Pull tables out of a PDF page range via pdfplumber (markdown-ish)."""
    path = _resolve(str(args.get("path", "")))
    if err := _check_readable(path):
        return err
    try:
        import pdfplumber
    except ImportError:
        return ToolResult(success=False, error="pdfplumber not installed (pip install pdfplumber)")

    pages = args.get("pages")
    try:
        chunks: list[str] = []
        n_tables = 0
        with pdfplumber.open(str(path)) as pdf:
            n = len(pdf.pages)
            idx = range(n) if pages in (None, "") else _page_range(pages, n)
            for i in idx:
                page = pdf.pages[i]
                for t_idx, table in enumerate(page.extract_tables() or []):
                    n_tables += 1
                    rows = ["| " + " | ".join(str(c) if c is not None else "" for c in row) + " |"
                            for row in table]
                    chunks.append(f"### table {t_idx + 1} (page {i + 1}, {len(table)} rows)\n" + "\n".join(rows))
    except Exception as e:  # noqa: BLE001
        return ToolResult(success=False, error=f"pdfplumber failed: {e}")

    if not n_tables:
        return ToolResult(success=False, error="No tables detected in the given pages.")
    return ToolResult(
        success=True,
        output=truncate("\n\n".join(chunks), MAX_OUTPUT),
        metadata={"tables": n_tables, "path": str(path)},
    )


# ------------------------------------------------------------- split/merge

def pdf_split(args: dict[str, Any]) -> ToolResult:
    """Split a PDF into single pages or ranges (writes PDFs under root)."""
    path = _resolve(str(args.get("path", "")))
    if err := _check_readable(path):
        return err
    dest_dir = _resolve(str(args.get("dest", "")) or path.with_suffix(""))
    if err := _safe_dest(dest_dir):
        return err
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return ToolResult(success=False, error="pypdf not installed")

    every = int(args.get("every", 1))  # pages per output file
    if every < 1:
        return ToolResult(success=False, error="'every' must be >= 1")
    try:
        reader = PdfReader(str(path))
        n = len(reader.pages)
        dest_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for start in range(0, n, every):
            writer = PdfWriter()
            for i in range(start, min(start + every, n)):
                writer.add_page(reader.pages[i])
            out = dest_dir / f"{path.stem}_p{start + 1:04d}-{min(start + every, n):04d}.pdf"
            with open(out, "wb") as fh:
                writer.write(fh)
            written.append(str(out.relative_to(_root())))
    except Exception as e:  # noqa: BLE001
        return ToolResult(success=False, error=f"Split failed: {e}")
    return ToolResult(
        success=True,
        output=f"Split {n} pages into {len(written)} files under {dest_dir.name}/",
        metadata={"files": written, "pages": n},
    )


def pdf_merge(args: dict[str, Any]) -> ToolResult:
    """Merge multiple PDFs into one (writes under the project root)."""
    paths_raw = args.get("paths") or []
    if isinstance(paths_raw, str):
        paths_raw = [p.strip() for p in paths_raw.split(",") if p.strip()]
    if len(paths_raw) < 2:
        return ToolResult(success=False, error="Provide at least two PDF paths in 'paths'.")

    resolved = [_resolve(str(p)) for p in paths_raw]
    for p in resolved:
        if err := _check_readable(p):
            return err

    dest = _resolve(str(args.get("dest", "")) or (_root() / "merged.pdf"))
    if err := _safe_dest(dest):
        return err
    try:
        from pypdf import PdfWriter
    except ImportError:
        return ToolResult(success=False, error="pypdf not installed")

    try:
        writer = PdfWriter()
        for p in resolved:
            writer.append(str(p))
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fh:
            writer.write(fh)
    except Exception as e:  # noqa: BLE001
        return ToolResult(success=False, error=f"Merge failed: {e}")
    return ToolResult(
        success=True,
        output=f"Merged {len(resolved)} PDFs ({len(resolved)} sources) -> {dest.name}",
        metadata={"dest": str(dest.relative_to(_root())), "sources": [str(p) for p in resolved]},
    )


__all__ = [
    "pdf_extract_text",
    "pdf_extract_tables",
    "pdf_split",
    "pdf_merge",
]
