"""Code intelligence tools — structural code analysis for the agent."""

from __future__ import annotations

import ast
import logging
import subprocess
import sys
from pathlib import Path

from tools.schema import ToolResult, tool_result, truncate

logger = logging.getLogger("jarvis.tools.code_intel")

_MAX_OUTPUT = 8000


def _run_grep(pattern: str, path: str = ".", include: str = "",
              max_results: int = 200) -> tuple[int, str, str]:
    """Run ripgrep and return (returncode, stdout, stderr)."""
    cmd = ["grep", "-rn", "--include", include or "*", pattern, path] if include else ["grep", "-rn", pattern, path]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
            cwd=str(Path.cwd()), check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", "grep not available"
    except subprocess.TimeoutExpired:
        return -1, "", "search timed out"
    except Exception as e:
        return -1, "", str(e)


async def code_symbol(params: dict) -> ToolResult:
    """Find symbol definitions (classes, functions, variables) by name.

    Parameters
    ----------
    name : str
        Symbol name to search for.
    path : str
        Directory to search in. Default project root.
    """
    name = params.get("name", "")
    if not name:
        return tool_result(False, error="name is required")
    search_path = params.get("path", ".")
    # Search for class/function/variable definitions
    patterns = [
        rf"(class|def)\s+{name}\b",
        rf"{name}\s*[=:]\s*",
        rf"(class|def)\s+{name}\s*\(",
    ]
    results = []
    for pattern in patterns:
        code, out, _ = _run_grep(pattern, search_path, "*.py")
        if code == 0 and out:
            for line in out.splitlines()[:20]:
                if line not in results:
                    results.append(line)
    if not results:
        # Fallback: just search for the name
        code, out, _ = _run_grep(rf"\b{name}\b", search_path)
        if code == 0 and out:
            results = out.splitlines()[:20]
    if not results:
        return tool_result(False, error=f"symbol '{name}' not found")
    output = "\n".join(results)
    return tool_result(True, output=truncate(output, _MAX_OUTPUT))


async def code_references(params: dict) -> ToolResult:
    """Find all references/usages of a symbol.

    Parameters
    ----------
    name : str
        Symbol name to find references for.
    path : str
        Directory to search in.
    """
    name = params.get("name", "")
    if not name:
        return tool_result(False, error="name is required")
    search_path = params.get("path", ".")
    code, out, err = _run_grep(rf"\b{name}\b", search_path)
    if code != 0 or not out:
        return tool_result(False, error=f"no references found for '{name}'")
    lines = out.splitlines()
    output = "\n".join(lines[:50])
    return tool_result(True, output=truncate(output, _MAX_OUTPUT))


async def code_imports(params: dict) -> ToolResult:
    """Show all imports in a Python file.

    Parameters
    ----------
    path : str
        Python file to analyze.
    """
    path = params.get("path", "")
    if not path:
        return tool_result(False, error="path is required")
    file_path = Path(path)
    if not file_path.exists():
        file_path = Path.cwd() / path
    if not file_path.exists():
        return tool_result(False, error=f"file not found: {path}")
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(content)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = ", ".join(
                    alias.name + (f" as {alias.asname}" if alias.asname else "")
                    for alias in node.names
                )
                level = "." * (node.level or 0)
                imports.append(f"from {level}{module} import {names}")
        if not imports:
            return tool_result(True, output="No imports found.")
        output = "\n".join(imports)
        return tool_result(True, output=output)
    except SyntaxError as e:
        return tool_result(False, error=f"Syntax error in {path}: {e}")


async def code_typecheck(params: dict) -> ToolResult:
    """Run Python type checking on a file or directory.

    Parameters
    ----------
    path : str
        File or directory to check. Default project root.
    """
    check_path = params.get("path", ".")
    # Try mypy first, fall back to py_compile
    code, out, err = _run_mypy(check_path)
    if code is not None:
        output = out or err or "No issues found."
        return tool_result(code == 0, output=truncate(output, _MAX_OUTPUT))
    # Fallback: py_compile
    return await _py_compile(check_path)


def _run_mypy(path: str) -> tuple[int | None, str, str]:
    """Try running mypy. Returns (None, '', '') if not available."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mypy", "--no-error-summary", "--hide-error-context", path],
            capture_output=True, text=True, timeout=30,
            cwd=str(Path.cwd()), check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, "", ""


async def _py_compile(path: str) -> ToolResult:
    """Compile-check Python files."""
    file_path = Path(path)
    if file_path.is_file():
        files = [file_path]
    elif file_path.is_dir():
        files = list(file_path.rglob("*.py"))[:50]
    else:
        return tool_result(False, error=f"path not found: {path}")
    errors = []
    for f in files:
        try:
            import py_compile
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(str(e))
    if errors:
        return tool_result(False, output="\n".join(errors[:20]))
    return tool_result(True, output=f"All {len(files)} files compile OK.")


async def code_definition(params: dict) -> ToolResult:
    name = params.get("name", "")
    if not name:
        return tool_result(False, error="name is required")
    search_path = params.get("path", ".")
    patterns = [
        rf"(class|def)\s+{name}\b",
        rf"{name}\s*=\s",
    ]
    results = []
    for pattern in patterns:
        code, out, _ = _run_grep(pattern, search_path, "*.py")
        if code == 0 and out:
            for line in out.splitlines()[:20]:
                if line not in results:
                    results.append(line)
    if not results:
        return tool_result(False, error=f"no definition found for '{name}'")
    return tool_result(True, output=truncate("\n".join(results), _MAX_OUTPUT))


async def code_callers(params: dict) -> ToolResult:
    name = params.get("name", "")
    if not name:
        return tool_result(False, error="name is required")
    search_path = params.get("path", ".")
    code, out, err = _run_grep(rf"{name}\s*\(", search_path, "*.py")
    if code != 0 or not out:
        return tool_result(False, error=f"no callers found for '{name}'")
    lines = [line for line in out.splitlines() if name in line and "def " + name not in line]
    if not lines:
        lines = out.splitlines()
    return tool_result(True, output=truncate("\n".join(lines[:30]), _MAX_OUTPUT))


async def code_callees(params: dict) -> ToolResult:
    file_path = params.get("file_path", "")
    function_name = params.get("function_name", "")
    if not file_path or not function_name:
        return tool_result(False, error="file_path and function_name are required")
    path = Path(file_path)
    if not path.exists():
        path = Path.cwd() / file_path
    if not path.exists():
        return tool_result(False, error=f"file not found: {file_path}")
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(content)
    except (SyntaxError, OSError) as e:
        return tool_result(False, error=f"cannot parse {file_path}: {e}")
    callees = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        callees.add(child.func.id)
                    elif isinstance(child.func, ast.Attribute):
                        callees.add(child.func.attr)
            break
    if not callees:
        return tool_result(True, output=f"No function calls found in '{function_name}'.")
    return tool_result(True, output="\n".join(sorted(callees)))


async def code_ast(params: dict) -> ToolResult:
    file_path = params.get("file_path", "")
    if not file_path:
        return tool_result(False, error="file_path is required")
    path = Path(file_path)
    if not path.exists():
        path = Path.cwd() / file_path
    if not path.exists():
        return tool_result(False, error=f"file not found: {file_path}")
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(content)
    except (SyntaxError, OSError) as e:
        return tool_result(False, error=f"cannot parse {file_path}: {e}")
    lines = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            bases = ", ".join(
                b.id if isinstance(b, ast.Name) else "..."
                for b in node.bases
            )
            methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            lines.append(f"class {node.name}({bases}):")
            for m in methods:
                lines.append(f"  def {m}()")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.append(f"{'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}def {node.name}()")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                lines.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = ", ".join(a.name for a in node.names)
            lines.append(f"from {module} import {names}")
    if not lines:
        return tool_result(True, output="(empty file)")
    return tool_result(True, output=truncate("\n".join(lines), _MAX_OUTPUT))
