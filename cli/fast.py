"""stdlib-only fast one-shot CLI (no typer/rich).

``python -m cli.fast "goal"`` runs one goal in-process against the real
agent engine, streaming observer events to stdout. Imports only the
standard library plus the engine modules, so a single request avoids the
full typer/rich REPL startup.

Output modes:

* default — one human-readable summary line (events go to stderr with ``-v``)
* ``--json`` — NDJSON: one ``{"event": ...}`` line per observer event, then a
  final ``{"result": ...}`` line

Exit codes: 0 on success, 1 on any failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable

__all__ = ["run_fast", "main"]


async def _run_one(goal: str, mode: str | None = None,
                   on_event: Callable[[str, dict], None] | None = None) -> dict:
    """Run ``goal`` in-process through the real agent engine."""
    from cli.main import _build_loop

    loop = _build_loop(mode or "agent", 10, None, None)
    if on_event is not None:
        loop.observer.on_event = on_event
    result = await loop.run(goal, session_id="", on_chunk=None)
    return _result_dict(result)


def _result_dict(result) -> dict:
    return {
        "success": bool(result.success),
        "response": result.response,
        "trace_id": getattr(result, "trace_id", ""),
        "error": result.error,
    }


def run_fast(goal: str, mode: str | None = None,
             on_event: Callable[[str, dict], None] | None = None) -> dict:
    """Run ``goal`` in-process; return the result dict."""
    return asyncio.run(_run_one(goal, mode=mode, on_event=on_event))


def _print_human(result: dict) -> None:
    success = bool(result.get("success"))
    trace = result.get("trace_id", "")
    marker = "ok" if success else "failed"
    print(f"{marker}: {trace}" if trace else marker)


def _print_json(result: dict) -> None:
    print(json.dumps({"result": result}, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="Fast stdlib-only one-shot agent CLI (in-process).")
    parser.add_argument("goal", help="task or request to run")
    parser.add_argument("--mode", default=None, choices=("plan", "controlled", "smart", "agent"),
                        help="permission/autonomy mode")
    parser.add_argument("--json", action="store_true",
                        help="emit NDJSON events + result on stdout")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="stream observer events to stderr")
    parser.add_argument("--project-dir", default=None,
                        help="project root (default: cwd)")
    args = parser.parse_args(argv)

    def _on_event(name: str, data: dict) -> None:
        if args.json:
            print(json.dumps({"event": name, "data": data}, default=str))
        elif args.verbose:
            print(f"> {name}", file=sys.stderr)

    try:
        result = run_fast(args.goal, mode=args.mode, on_event=_on_event)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    (_print_json if args.json else _print_human)(result)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
