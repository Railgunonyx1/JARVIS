"""API collections — bruno-style file-based request runner (usebruno/bruno).

Bruno stores API collections as plain-text `.bru` files in the filesystem —
git-friendly, offline-first. JARVIS runs them by parsing the documented
core format (meta/method/url/headers/query/body blocks) and executing
through the shared pooled HTTP client. No npm/@usebruno/cli dependency.

Secrets: values written as ``{{SECRET_NAME}}`` matching a registered
env var are interpolated from the environment **without the value ever
entering the result output** — consistent with the secret.ref indirection
policy. Variable interpolation supports ``{{name}}`` from a provided
`vars` mapping with env fallback.

Security: this runner executes HTTP requests defined in repo files. Treat
collection files as untrusted input — SSRF matters, so loopback/private
targets require an explicit allow flag. Only standard methods are honored.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from tools.schema import ToolResult, truncate

logger = logging.getLogger("jarvis.tools.api_collections")

MAX_OUTPUT = 12000
ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}
_TIMEOUT_DEFAULT = 30.0
_TIMEOUT_MAX = 60.0
_VAR_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}")

# Hosts an agent may not probe without an explicit override.
_PRIVATE_HOST_RE = re.compile(
    r"^(localhost|127\.|10\.|192\.168\.|169\.254\.|0\.0\.0\.0|::1|\[::1\]|"
    r"172\.(1[6-9]|2\d|3[01])\.)",
    re.IGNORECASE,
)

_BLOCK_RE = re.compile(r"^(meta|headers|query|params|assert)\s*\{$", re.IGNORECASE)
_METHOD_RE = re.compile(r"^(get|post|put|patch|delete|head)\s*\{(.*)$", re.IGNORECASE)
_BODY_JSON_RE = re.compile(r"^body:json\s*\{(.*)$", re.IGNORECASE)


def _root() -> Path:
    from core.project import ProjectContext
    return ProjectContext.discover().root_path


def _resolve(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = _root() / p
    return p


def _interpolate(text: str, vars: dict[str, str]) -> str:
    """Replace {{var}} from the vars mapping, falling back to env.

    Secret values sourced from the environment are consumed for the request
    but never echoed back in results (only status/size are reported).
    """
    def repl(m: "re.Match[str]") -> str:
        name = m.group(1)
        if name in vars:
            return str(vars[name])
        if name.isupper() and name in os.environ:
            return os.environ[name]
        return m.group(0)  # unknown vars stay visible for debugging

    return _VAR_RE.sub(repl, text)


def _read_block(text: str, i: int) -> tuple[list[str], int]:
    """Read a `{ ... }` block starting after the opening line's `{`.

    Returns (raw lines inside the block, index after the closing brace line).
    """
    n = len(text)
    buf: list[str] = []
    depth = 1
    while i < n and depth > 0:
        nl = text.find("\n", i)
        line = text[i:nl] if nl != -1 else text[i:]
        i = nl + 1 if nl != -1 else n
        depth += line.count("{") - line.count("}")
        if depth > 0:
            buf.append(line)
        elif depth == 0:
            buf.append(line.rsplit("}", 1)[0])
    return buf, i


def _parse_bru(text: str) -> dict[str, Any]:
    """Parse the core .bru format conservatively:

        meta { name: get-user }
        get { url: https://api.example.com/users }
        headers { content-type: application/json }
        query { page: 1 }
        body:json { {"id": 1} }
    """
    req: dict[str, Any] = {"meta": {}, "headers": {}, "query": {}}
    method = "get"
    i = 0
    n = len(text)
    while i < n:
        nl = text.find("\n", i)
        line = (text[i:nl] if nl != -1 else text[i:]).strip()
        i = nl + 1 if nl != -1 else n
        if not line or line.startswith("#"):
            continue

        m = _METHOD_RE.match(line)
        if m:
            method = m.group(1).lower()
            rest = m.group(2).rstrip("}").strip()
            if rest:
                req["url"] = rest
            else:
                # Canonical .bru form: url (and body) live INSIDE the block.
                lines, i = _read_block(text, i)
                for bl in lines:
                    bl = bl.strip()
                    k, sep, v = bl.partition(":")
                    if sep and k.strip().lower() == "url":
                        req["url"] = v.strip()
                        break
            continue

        m = _BLOCK_RE.match(line)
        if m:
            block = m.group(1).lower()
            lines, i = _read_block(text, i)
            for bl in lines:
                bl = bl.strip().rstrip(",")
                if not bl:
                    continue
                k, sep, v = bl.partition(":")
                if not sep:
                    continue
                k = k.strip()
                v = v.strip().strip('"').strip()
                if block == "meta":
                    req["meta"][k] = v
                elif block in ("headers", "query"):
                    req[block][k] = v
                elif block == "params":
                    req.setdefault("params", {})[k] = v
            continue

        m = _BODY_JSON_RE.match(line)
        if m:
            first = m.group(1)
            buf = [first]
            while i < n:
                nl = text.find("\n", i)
                line2 = text[i:nl] if nl != -1 else text[i:]
                i = nl + 1 if nl != -1 else n
                if line2.strip() == "}":
                    break
                buf.append(line2)
            body_text = "\n".join(buf).strip()
            # The block's closing brace may be glued to the JSON tail (single-
            # line form). Only strip it when the remainder isn't valid JSON.
            if body_text:
                try:
                    json.loads(body_text)
                except ValueError:
                    if body_text.endswith("}"):
                        candidate = body_text[:-1].rstrip()
                        try:
                            json.loads(candidate)
                            body_text = candidate
                        except ValueError:
                            pass
                req["body_json"] = body_text
            continue

    req["method"] = method.upper()
    return req


def _iter_bru_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() == ".bru" else []
    return sorted(root.rglob("*.bru"))


def api_parse(args: dict[str, Any]) -> ToolResult:
    """Parse a .bru file and show the request it defines (no execution)."""
    path = _resolve(str(args.get("path", "")))
    if not path.exists() or not path.is_file():
        return ToolResult(success=False, error=f"Not found: {path}")
    try:
        req = _parse_bru(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return ToolResult(success=False, error=f"Parse failed: {e}")
    req["meta"]["file"] = path.name
    body = json.dumps(req, indent=2, ensure_ascii=False)
    return ToolResult(success=True, output=truncate(body, MAX_OUTPUT), metadata={"path": str(path)})


def api_run(args: dict[str, Any]) -> ToolResult:
    """Run a .bru request file or a collection folder of them.

    Args: path (required), vars (optional object of {{name}} -> value),
    allow_private (default false), timeout (seconds, cap 60).
    """
    target = str(args.get("path", "")).strip()
    if not target:
        return ToolResult(success=False, error="path is required (.bru file or collection folder)")
    p = _resolve(target)
    if not p.exists():
        return ToolResult(success=False, error=f"Not found: {p}")

    files = _iter_bru_files(p)
    if not files:
        return ToolResult(success=False, error=f"No .bru files found under {p}")

    vars_raw = args.get("vars") or {}
    if not isinstance(vars_raw, dict):
        return ToolResult(success=False, error="'vars' must be an object")
    allow_private = bool(args.get("allow_private", False))

    try:
        timeout = min(float(args.get("timeout", _TIMEOUT_DEFAULT)), _TIMEOUT_MAX)
    except (TypeError, ValueError):
        timeout = _TIMEOUT_DEFAULT

    from core.http_pool import get_client
    client = get_client()

    results: list[str] = []
    ok_count = 0
    for f in files:
        try:
            req = _parse_bru(f.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            results.append(f"✗ {f.name}: parse error ({e})")
            continue

        url = _interpolate(str(req.get("url", "")), vars_raw)
        method = str(req.get("method", "GET"))
        if not url:
            results.append(f"✗ {f.name}: no url defined")
            continue
        if method not in ALLOWED_METHODS:
            results.append(f"✗ {f.name}: method {method} not allowed")
            continue

        # SSRF guard: block loopback/private targets unless explicitly allowed
        host = re.split(r"[/?#]", re.sub(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", "", url))[0]
        if _PRIVATE_HOST_RE.match(host or "") and not allow_private:
            results.append(
                f"✗ {f.name}: private/loopback target '{host}' blocked "
                f"(allow_private=true to override)"
            )
            continue

        headers = {k: _interpolate(v, vars_raw) for k, v in req.get("headers", {}).items()}
        query = {k: _interpolate(v, vars_raw) for k, v in req.get("query", {}).items()}
        body = req.get("body_json")
        if isinstance(body, str) and body:
            body = _interpolate(body, vars_raw)

        try:
            resp = client.request(
                method, url, headers=headers or None, params=query or None,
                content=body.encode("utf-8") if isinstance(body, str) and body else None,
                timeout=timeout,
            )
            status = resp.status_code
            ok_flag = 200 <= status < 300
            ok_count += ok_flag
            size = len(resp.content or b"")
            results.append(
                f"{'✓' if ok_flag else '✗'} {f.stem}: {method} {url} -> {status} ({size} bytes)"
            )
        except Exception as e:  # noqa: BLE001
            results.append(f"✗ {f.stem}: request failed ({e})")

    total = len(files)
    summary = f"{ok_count}/{total} requests ok"
    return ToolResult(
        success=ok_count == total,
        output=truncate(summary + "\n" + "\n".join(results), MAX_OUTPUT),
        metadata={"total": total, "ok": ok_count, "path": str(p)},
    )


__all__ = ["api_parse", "api_run"]
