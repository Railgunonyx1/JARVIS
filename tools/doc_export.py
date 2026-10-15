"""Document → Markdown export (markitdown concept).

Converts local documents to Markdown so research agents can read them and
outputs can be re-published. Supported inputs, best-effort by availability:
  .docx  via python-docx (headings, paragraphs, list items)
  .html  via markdownify (structure-preserving)
  .pdf   via pypdf text extraction (fenced per page)
  .txt/.md/.csv/.json/.ipynb passthrough or light wrapping
Writes the .md file next to the source (or to 'dest') and returns a preview.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from tools.schema import ToolResult, truncate

logger = logging.getLogger("jarvis.tools.doc_export")

MAX_PREVIEW = 2500
MAX_BYTES = 100 * 1024 * 1024

_TEXTUAL = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".toml", ".yaml", ".yml", ".xml"}


def _root() -> Path:
    from core.project import ProjectContext
    return ProjectContext.discover().root_path


def _resolve(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = _root() / p
    return p


def doc_to_markdown(args: dict[str, Any]) -> ToolResult:
    """Convert a document to Markdown and save it as <name>.md."""
    path = _resolve(str(args.get("path", "")))
    if not path.exists() or not path.is_file():
        return ToolResult(success=False, error=f"Not found: {path}")
    if path.stat().st_size > MAX_BYTES:
        return ToolResult(success=False, error="File too large to convert.")

    ext = path.suffix.lower()
    try:
        if ext == ".docx":
            md, meta = _docx_to_md(path)
        elif ext in (".html", ".htm"):
            md, meta = _html_to_md(path)
        elif ext == ".pdf":
            md, meta = _pdf_to_md(path)
        elif ext == ".ipynb":
            md, meta = _ipynb_to_md(path)
        elif ext in _TEXTUAL:
            md, meta = _textual_to_md(path, ext)
        elif ext == ".xlsx":
            md, meta = _xlsx_to_md(path)
        else:
            return ToolResult(success=False, error=f"Unsupported type '{ext}' (try docx/html/pdf/ipynb/txt/csv/json/xlsx).")
    except ImportError as e:
        return ToolResult(success=False, error=f"Missing dependency: {e}")
    except Exception as e:  # noqa: BLE001
        return ToolResult(success=False, error=f"Conversion failed: {e}")

    dest_raw = str(args.get("dest", "")).strip()
    dest = _resolve(dest_raw) if dest_raw else path.with_suffix(".md")
    try:
        dest.resolve().relative_to(_root().resolve())
    except ValueError:
        return ToolResult(success=False, error="Destination must be inside the project root.")
    if dest.suffix.lower() != ".md":
        dest = dest.with_suffix(".md")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(md, encoding="utf-8")

    rel = dest.relative_to(_root())
    return ToolResult(
        success=True,
        output=truncate(
            f"Converted {path.name} -> {rel} ({len(md)} chars)\n\n{md[:MAX_PREVIEW]}",
            4000,
        ),
        metadata={"dest": str(rel), "source_ext": ext, "chars": len(md), **meta},
    )


# ------------------------------------------------------------- converters

def _docx_to_md(path: Path) -> tuple[str, dict]:
    import docx  # python-docx

    doc = docx.Document(str(path))
    lines: list[str] = []
    for para in doc.paragraphs:
        style = (para.style.name or "").lower()
        text = para.text.strip()
        if not text:
            continue
        if style.startswith("heading 1"):
            lines.append(f"# {text}")
        elif style.startswith("heading 2"):
            lines.append(f"## {text}")
        elif style.startswith("heading 3"):
            lines.append(f"### {text}")
        elif style.startswith("heading"):
            lines.append(f"#### {text}")
        elif "list" in style:
            lines.append(f"- {text}")
        else:
            lines.append(text)
    meta = {"paragraphs": len(lines)}
    if doc.tables:
        for t_idx, table in enumerate(doc.tables):
            lines.append(f"\n### table {t_idx + 1}\n")
            for row in table.rows:
                lines.append("| " + " | ".join(c.text.strip() for c in row.cells) + " |")
        meta["tables"] = len(doc.tables)
    return "\n\n".join(lines), meta


def _html_to_md(path: Path) -> tuple[str, dict]:
    from markdownify import markdownify as md_fn

    html = path.read_text(encoding="utf-8", errors="replace")
    return md_fn(html, heading_style="ATX").strip(), {}


def _pdf_to_md(path: Path) -> tuple[str, dict]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts = [f"--- page {i + 1} ---\n{p.extract_text() or ''}" for i, p in enumerate(reader.pages)]
    return "\n\n".join(parts).strip(), {"pages": len(reader.pages)}


def _ipynb_to_md(path: Path) -> tuple[str, dict]:
    nb = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    lines: list[str] = []
    n_code = n_md = 0
    for cell in nb.get("cells", []):
        src = "".join(cell.get("source", []))
        if cell.get("cell_type") == "markdown":
            n_md += 1
            lines.append(src)
        elif cell.get("cell_type") == "code":
            n_code += 1
            lang = (nb.get("metadata", {}).get("kernelspec", {}).get("language") or "python")
            lines.append(f"```{lang}\n{src}\n```")
    return "\n\n".join(lines), {"cells": n_code + n_md, "code": n_code}


def _textual_to_md(path: Path, ext: str) -> tuple[str, dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if ext == ".json":
        try:
            text = json.dumps(json.loads(text), indent=2)
        except Exception:  # noqa: BLE001
            pass
    if ext == ".md":
        return text, {}
    fence = {"csv": "", "json": "json", ".log": ""}.get(ext.lstrip("."), "")
    if ext in (".csv", ".log") or not fence:
        return text, {}
    return f"```{fence}\n{text}\n```", {}


def _xlsx_to_md(path: Path) -> tuple[str, dict]:
    """Excel → Markdown tables via openpyxl (commonly installed with pdf stack)."""
    try:
        from openpyxl import load_workbook
    except ImportError as e:
        raise ImportError("openpyxl (pip install openpyxl)") from e
    wb = load_workbook(str(path), read_only=True, data_only=True)
    lines: list[str] = []
    for ws in wb.worksheets:
        lines.append(f"## {ws.title}\n")
        for row in ws.iter_rows(values_only=True):
            if any(v is not None for v in row):
                lines.append("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
        lines.append("")
    return "\n".join(lines).strip(), {"sheets": len(wb.worksheets)}


__all__ = ["doc_to_markdown"]
