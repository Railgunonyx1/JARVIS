"""stdlib-only fast one-shot CLI (no typer/rich).

``python -m cli.fast "goal"`` connects to the project's resident daemon
(starting it if needed) and streams the run to stdout. Imports only the
standard library plus the light daemon modules, so a warm daemon turns a
command into: interpreter start + one loopback round trip.

Output modes:

* default — one human-readable summary line (events go to stderr with ``-v``)
* ``--json`` — NDJSON: one ``{"event": ...}`` line per observer event, then a
  final ``{"result": ...}`` line

Exit codes: 0 on success, 1 on any failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

__all__ = ["run_fast", "main"]


def run_fast(entry: dict, goal: str, mode: str | None = None,
             on_event: Callable[[str, dict], None] | None = None) -> dict:
    """Run ``goal`` against a daemon registry entry; return the result dict.

    Raises :class:`daemon.fastclient.FastError` on connection/protocol/run
    failure. ``entry`` must contain ``port`` and ``token`` (``host`` optional,
    default 127.0.0.1).
    """
    from daemon.fastclient import FastClient

    host = entry.get("host", "127.0.0.1")
    with FastClient(host=host, port=int(entry["port"]),
                    token=str(entry.get("token", ""))) as client:
        client.connect()
        return client.run(goal, mode=mode, on_event=on_event)


def _resolve_entry(project_dir: str, timeout: float = 30.0) -> dict | None:
    from daemon.lifecycle import find_matching, start_daemon

    entry = find_matching(project_dir)
    if entry is not None:
        return entry
    return start_daemon(project_dir, timeout=timeout)


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
        description="Fast stdlib-only one-shot agent CLI (daemon-backed).")
    parser.add_argument("goal", help="task or request to run")
    parser.add_argument("--mode", default=None, choices=("plan", "controlled", "smart", "agent"),
                        help="permission/autonomy mode")
    parser.add_argument("--json", action="store_true",
                        help="emit NDJSON events + result on stdout")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="stream observer events to stderr")
    parser.add_argument("--project-dir", default=None,
                        help="project to attach a daemon to (default: cwd)")
    args = parser.parse_args(argv)

    project = str(Path(args.project_dir).resolve()) if args.project_dir \
        else str(Path.cwd().resolve())

    entry = _resolve_entry(project)
    if entry is None:
        print("daemon failed to start — check ~/.jarvis/daemon.log",
              file=sys.stderr)
        return 1

    def _on_event(name: str, data: dict) -> None:
        if args.json:
            print(json.dumps({"event": name, "data": data}, default=str))
        elif args.verbose:
            print(f"> {name}", file=sys.stderr)

    try:
        result = run_fast(entry, args.goal, mode=args.mode, on_event=_on_event)
    except Exception as exc:  # FastError + anything the kernel raised
        print(f"error: {exc}", file=sys.stderr)
        return 1

    (_print_json if args.json else _print_human)(result)
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
