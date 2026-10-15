"""J-Browser — command-line client (headless/headed agent browser).

Runs J-Browser as a self-contained client against the existing JARVIS kernel
without requiring a native shell: open URLs, list/operate tabs, read page
context, screenshot, or run an interactive REPL. All operations go through
the same ``BrowserController`` / backend as the agent tools.

Usage:
    python -m apps.jbrowser open <url> [--headed]
    python -m apps.jbrowser tabs
    python -m apps.jbrowser read [tab_id]
    python -m apps.jbrowser screenshot [tab_id]
    python -m apps.jbrowser status
    python -m apps.jbrowser repl
"""

from __future__ import annotations

import argparse
import sys

from jbrowser.backend.playwright import PlaywrightBackend
from jbrowser.controller import BrowserController, get_controller, reset_controller


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jbrowser", description="J-Browser agent browser client")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_open(sp):
        sp.add_argument("url")
        sp.add_argument("--headed", action="store_true", help="Launch headed (visible) Chromium")

    add_open(sub.add_parser("open"))
    sub.add_parser("tabs")
    sp_read = sub.add_parser("read")
    sp_read.add_argument("tab_id", nargs="?", default=None)
    sp_shot = sub.add_parser("screenshot")
    sp_shot.add_argument("tab_id", nargs="?", default=None)
    sub.add_parser("status")
    sub.add_parser("repl")
    return p


def _run(args: argparse.Namespace) -> int:
    if args.cmd == "open":
        controller = BrowserController(
            backend=PlaywrightBackend(headless=not args.headed)
        )
        _set_singleton(controller)
        result = controller.navigate(args.url)
        print(f"Title: {result['title']}")
        print(f"URL:   {result['url']}")
        ctx = controller.read()
        print("\n" + ctx.to_prompt_block())
        return 0
    if args.cmd == "tabs":
        tabs = get_controller().list_tabs()
        if not tabs:
            print("No open tabs. Use 'jbrowser open <url>' first.")
            return 0
        for t in tabs:
            marker = "ACTIVE" if t.get("active") else "     "
            print(f"{marker} {t.get('tab_id')} [{t.get('session_id')}] {t.get('url')}")
        return 0
    if args.cmd == "read":
        ctx = get_controller().read(args.tab_id)
        print(ctx.to_prompt_block())
        return 0
    if args.cmd == "screenshot":
        path = get_controller().screenshot(args.tab_id)
        print(path)
        return 0
    if args.cmd == "status":
        for k, v in get_controller().status().items():
            print(f"{k}: {v}")
        return 0
    if args.cmd == "repl":
        return _repl()
    print(f"unknown command: {args.cmd}")
    return 2


def _set_singleton(controller: BrowserController) -> None:
    import jbrowser.controller as ctlmod
    ctlmod._controller = controller


def _repl() -> int:
    controller = get_controller()
    print("J-Browser REPL. Commands: open <url> | read | tabs | status | screenshot | exit")
    while True:
        try:
            line = input("jbrowser> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("exit", "quit"):
            break
        parts = line.split(None, 1)
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ""
        try:
            if cmd == "open":
                r = controller.navigate(arg)
                print(r["title"], "|", r["url"])
            elif cmd == "read":
                print(controller.read().to_prompt_block())
            elif cmd == "tabs":
                for t in controller.list_tabs():
                    print(t.get("tab_id"), t.get("url"))
            elif cmd == "status":
                print(controller.status())
            elif cmd == "screenshot":
                print(controller.screenshot())
            else:
                print(f"unknown: {cmd}")
        except Exception as e:
            print(f"error: {e}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    try:
        return _run(args)
    except Exception as exc:  # noqa: BLE001 - CLI should report errors cleanly
        print(f"jbrowser error: {exc}", file=sys.stderr)
        return 1
    finally:
        reset_controller()


if __name__ == "__main__":
    raise SystemExit(main())
