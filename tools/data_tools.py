"""Data tools — CSV/JSON/TSV summaries, filters and conversion via pandas.

Derived from the repo-mine list (johnkerl/miller, dathere/qsv, jqlang/jq):
the agent can inspect and slice tabular data directly instead of dumping
raw files into context or shelling out. Read-only except data.convert.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from tools.schema import ToolResult, truncate

logger = logging.getLogger("jarvis.tools.data")

MAX_OUTPUT = 12000
MAX_BYTES = 200 * 1024 * 1024
MAX_ROWS_SHOWN = 50


def _root() -> Path:
    from core.project import ProjectContext
    return ProjectContext.discover().root_path


def _resolve(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = _root() / p
    return p


def _check(path: Path) -> ToolResult | None:
    if not path.exists():
        return ToolResult(success=False, error=f"Not found: {path}")
    if not path.is_file():
        return ToolResult(success=False, error=f"Not a file: {path}")
    if path.stat().st_size > MAX_BYTES:
        return ToolResult(success=False, error=f"File too large (> {MAX_BYTES // (1024*1024)} MB): {path}")
    return None


def _load(path: Path):
    """Read CSV/TSV/JSON/JSONL into a DataFrame; raises ValueError on unknown types."""
    import pandas as pd

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in (".tsv", ".tab"):
        return pd.read_csv(path, sep="\t")
    if suffix == ".json":
        return pd.read_json(path)
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True)
    raise ValueError(
        f"Unsupported data type '{suffix}' (supported: .csv .tsv .json .jsonl)"
    )


def _pandas() -> ToolResult | None:
    try:
        import pandas  # noqa: F401
    except ImportError:
        return ToolResult(success=False, error="pandas not installed (pip install pandas)")
    return None


# ------------------------------------------------------------------ stats

def data_stats(args: dict[str, Any]) -> ToolResult:
    """Column-level profile of a CSV/JSON file: dtypes, nulls, uniques, ranges."""
    if err := _pandas():
        return err
    import pandas as pd

    path = _resolve(str(args.get("path", "")))
    if err := _check(path):
        return err
    try:
        df = _load(path)
    except Exception as e:  # noqa: BLE001
        return ToolResult(success=False, error=f"Cannot parse {path.name}: {e}")

    lines = [
        f"file: {path.name}  rows: {len(df)}  columns: {len(df.columns)}",
        "",
    ]
    for col in df.columns:
        s = df[col]
        desc = f"  {col} [{s.dtype}] nulls={int(s.isna().sum())} unique={int(s.nunique(dropna=True))}"
        if pd.api.types.is_numeric_dtype(s) and s.notna().any():
            desc += f" min={s.min():.6g} max={s.max():.6g} mean={s.mean():.6g}"
        else:
            top = s.value_counts().head(1)
            if not top.empty:
                desc += f" top='{top.index[0]}' ({int(top.iloc[0])}x)"
        lines.append(desc)

    if len(df):
        lines.append("")
        try:
            num = df.select_dtypes("number")
            if len(num.columns) > 1:
                corr = num.corr().round(2)
                strongest = _strongest_corr(corr)
                if strongest:
                    lines.append(f"strongest numeric correlation: {strongest}")
        except Exception:  # noqa: BLE001
            pass
    return ToolResult(
        success=True,
        output=truncate("\n".join(lines), MAX_OUTPUT),
        metadata={"rows": len(df), "columns": len(df.columns), "path": str(path)},
    )


def _strongest_corr(corr) -> str | None:
    """Find the strongest |pairwise| correlation, excluding the diagonal."""
    best = (0.0, None)
    cols = list(corr.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            v = abs(float(corr.loc[a, b]))
            if v > best[0]:
                best = (v, f"{a} <-> {b} (r={corr.loc[a, b]:.2f})")
    return best[1]


# ------------------------------------------------------------------ query

def data_query(args: dict[str, Any]) -> ToolResult:
    """Filter rows with a pandas query expression and show a sample.

    Example: data.query(path="sales.csv", expr="revenue > 1000 and region == 'EMEA'")
    """
    if err := _pandas():
        return err
    path = _resolve(str(args.get("path", "")))
    expr = str(args.get("expr", "")).strip()
    if not expr:
        return ToolResult(success=False, error="expr is required (pandas query syntax)")
    if err := _check(path):
        return err
    try:
        df = _load(path)
    except Exception as e:  # noqa: BLE001
        return ToolResult(success=False, error=f"Cannot parse {path.name}: {e}")
    try:
        filtered = df.query(expr)
    except Exception as e:  # noqa: BLE001
        return ToolResult(
            success=False,
            error=f"Query failed: {e}. Column names: {list(df.columns)}",
        )
    sample = filtered.head(MAX_ROWS_SHOWN).to_string(index=False)
    body = f"{len(filtered)} of {len(df)} rows match.\n\n{sample if len(filtered) else ''}"
    return ToolResult(
        success=True,
        output=truncate(body, MAX_OUTPUT),
        metadata={"matched": len(filtered), "total": len(df), "path": str(path)},
    )


# ----------------------------------------------------------------- convert

def data_convert(args: dict[str, Any]) -> ToolResult:
    """Convert CSV/TSV/JSON/JSONL between formats (writes inside project root)."""
    if err := _pandas():
        return err
    path = _resolve(str(args.get("path", "")))
    if err := _check(path):
        return err
    dest = _resolve(str(args.get("dest", "")))
    if not str(args.get("dest", "")).strip():
        return ToolResult(success=False, error="dest is required (e.g. output.json)")
    try:
        dest.resolve().relative_to(_root().resolve())
    except ValueError:
        return ToolResult(success=False, error=f"Destination must be inside the project root: {dest}")
    try:
        df = _load(path)
    except ValueError as e:
        return ToolResult(success=False, error=str(e))
    except Exception as e:  # noqa: BLE001
        return ToolResult(success=False, error=f"Cannot parse {path.name}: {e}")

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        suffix = dest.suffix.lower()
        if suffix == ".csv":
            df.to_csv(dest, index=False)
        elif suffix == ".tsv":
            df.to_csv(dest, sep="\t", index=False)
        elif suffix == ".json":
            df.to_json(dest, orient="records", indent=2, force_ascii=False)
        elif suffix == ".jsonl":
            df.to_json(dest, orient="records", lines=True, force_ascii=False)
        else:
            return ToolResult(
                success=False,
                error=f"Unsupported dest type '{suffix}' (supported: .csv .tsv .json .jsonl)",
            )
    except Exception as e:  # noqa: BLE001
        return ToolResult(success=False, error=f"Convert failed: {e}")
    return ToolResult(
        success=True,
        output=f"Converted {len(df)} rows: {path.name} -> {dest.relative_to(_root())}",
        metadata={"rows": len(df), "dest": str(dest.relative_to(_root()))},
    )


__all__ = ["data_stats", "data_query", "data_convert"]
