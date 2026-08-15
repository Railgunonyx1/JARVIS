"""
JARVIS MK-X Commands + Command Palette

/command style for pure terminal.
Ctrl+K is the conceptual palette; these are the real entries.
Only commands that exist. No fake placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, TYPE_CHECKING

from .models import Mode, MODE_HELP

if TYPE_CHECKING:
    from .renderer import Renderer


@dataclass
class Command:
    name: str
    help: str
    handler: Callable[[List[str]], None]
    aliases: List[str] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.aliases is None:
            self.aliases = []


class CommandRegistry:
    def __init__(self, renderer: "Renderer") -> None:
        self.renderer = renderer
        self._commands: Dict[str, Command] = {}
        self._register_builtins()

    def _register(self, cmd: Command) -> None:
        self._commands[cmd.name] = cmd
        for a in cmd.aliases:
            self._commands[a] = cmd

    def _register_builtins(self) -> None:
        r = self.renderer

        def help_cmd(args: List[str]) -> None:
            lines = ["AVAILABLE COMMANDS", ""]
            seen = set()
            for name, cmd in sorted(self._commands.items()):
                if cmd.name in seen:
                    continue
                seen.add(cmd.name)
                aliases = f" ({', '.join(cmd.aliases)})" if cmd.aliases else ""
                lines.append(f"  /{cmd.name}{aliases}")
                lines.append(f"      {cmd.help}")
            lines += [
                "",
                "WORKSPACES (also via /workspace <name>)",
                "  chat  plan  code  activity  memory  audit",
                "",
                "MODES (real execution policies)",
            ]
            for m, desc in MODE_HELP.items():
                lines.append(f"  {m.value:12} {desc}")
            r.print("\n".join(lines))

        def status_cmd(args: List[str]) -> None:
            s = r.state
            r.print(f"Mode      : {s.mode.value}  ({MODE_HELP.get(s.mode, '')})")
            r.print(f"Model     : {s.model}")
            r.print(f"Tokens    : {s.tokens_used}/{s.tokens_limit}")
            r.print(f"Tools     : {s.tools_active} active")
            r.print(f"Memory    : {'on' if s.memory_enabled else 'off'}")
            r.print(f"Connection: {s.connection}")
            r.print(f"Workspace : {s.workspace}")
            r.print(f"Layout    : {r.layout_mgr.detect_mode().value}")

        def mode_cmd(args: List[str]) -> None:
            if not args:
                r.print(f"Current mode: {r.state.mode.value}")
                for m, desc in MODE_HELP.items():
                    r.print(f"  {m.value:12} {desc}")
                return
            try:
                m = Mode(args[0].upper())
                r.set_mode(m)
                r.print_success(f"Mode → {m.value}  ({MODE_HELP[m]})")
            except ValueError:
                r.print_error("Unknown mode", "Use: agent | plan | controlled | smart")

        def layout_cmd(args: List[str]) -> None:
            if not args:
                r.print(f"Current layout: {r.layout_mgr.detect_mode().value}")
                r.print("Available: minimal | normal | focus | plan | activity | code | memory | audit")
                return
            r.layout_mgr.set_mode(args[0].lower())
            r.set_workspace(args[0].lower() if args[0].lower() in ("code", "memory", "audit", "chat", "plan", "activity") else r.state.workspace)
            r.print_success(f"Layout → {args[0].lower()}")

        def workspace_cmd(args: List[str]) -> None:
            if not args:
                r.print(f"Current workspace: {r.state.workspace}")
                r.print("Available: chat | plan | code | activity | memory | audit")
                return
            name = args[0].lower()
            if name not in ("chat", "plan", "code", "activity", "memory", "audit"):
                r.print_error("Unknown workspace", "chat | plan | code | activity | memory | audit")
                return
            r.set_workspace(name)
            if name in ("code", "memory", "audit", "plan", "activity"):
                r.layout_mgr.set_mode(name)
            else:
                r.layout_mgr.clear_force()
                r.layout_mgr.set_mode("normal")
            r.print_success(f"Workspace → {name}")

        def clear_cmd(args: List[str]) -> None:
            r.state.messages.clear()
            r.clear()
            r.print_success("Conversation cleared")

        def tools_cmd(args: List[str]) -> None:
            if not r.state.events:
                r.print("No events yet.")
                return
            r.print(r.render_activity())

        def memory_cmd(args: List[str]) -> None:
            r.set_workspace("memory")
            r.layout_mgr.set_mode("memory")
            r.print(r.render_memory())

        def audit_cmd(args: List[str]) -> None:
            r.set_workspace("audit")
            r.layout_mgr.set_mode("audit")
            r.print(r.render_audit())

        def code_cmd(args: List[str]) -> None:
            r.set_workspace("code")
            r.layout_mgr.set_mode("code")
            r.print(r.render_code_header())
            r.print(r.render_code_buffer())

        def palette_cmd(args: List[str]) -> None:
            """Conceptual Ctrl+K surface."""
            r.print("COMMAND PALETTE")
            r.print("  chat       Conversation (default)")
            r.print("  plan       Plan panel focus")
            r.print("  code       Code workspace")
            r.print("  activity   Live event stream")
            r.print("  memory     Memory workspace")
            r.print("  audit      Audit / health")
            r.print("  mode       Execution policy")
            r.print("  status     Current state")
            r.print("  clear      Clear conversation")
            r.print("  exit       Quit")
            r.print("")
            r.print("Tip: /workspace <name>  or  /layout <name>")

        def exit_cmd(args: List[str]) -> None:
            raise SystemExit(0)

        def not_connected(name: str) -> Callable[[List[str]], None]:
            def _h(args: List[str]) -> None:
                r.print_error(f"{name} backend not connected", "Wire the real component first.")
            return _h

        self._register(Command("help", "Show commands, workspaces, modes", help_cmd, ["h", "?"]))
        self._register(Command("status", "Show current status", status_cmd, ["s"]))
        self._register(Command("mode", "Set execution policy (agent|plan|controlled|smart)", mode_cmd, ["m"]))
        self._register(Command("layout", "Change layout / workspace", layout_cmd, ["l"]))
        self._register(Command("workspace", "Switch workspace", workspace_cmd, ["ws"]))
        self._register(Command("palette", "Show command palette (Ctrl+K)", palette_cmd, ["k"]))
        self._register(Command("clear", "Clear conversation", clear_cmd, ["cls"]))
        self._register(Command("tools", "Show live activity stream", tools_cmd))
        self._register(Command("activity", "Show live activity stream", tools_cmd))
        self._register(Command("memory", "Open memory workspace", memory_cmd))
        self._register(Command("audit", "Open audit workspace", audit_cmd))
        self._register(Command("code", "Open code workspace", code_cmd))
        self._register(Command("exit", "Exit JARVIS", exit_cmd, ["quit", "q"]))
        self._register(Command("model", "Show / switch model", not_connected("Model")))
        self._register(Command("context", "Show context window", not_connected("Context")))
        self._register(Command("sessions", "List sessions", not_connected("Sessions")))
        self._register(Command("resume", "Resume a session", not_connected("Sessions")))

    def dispatch(self, line: str) -> bool:
        line = line.strip()
        if not line.startswith("/"):
            return False
        parts = line[1:].split()
        if not parts:
            return True
        name, args = parts[0].lower(), parts[1:]
        cmd = self._commands.get(name)
        if cmd is None:
            self.renderer.print_error(f"Unknown command: /{name}", "Type /help")
            return True
        try:
            cmd.handler(args)
        except SystemExit:
            raise
        except Exception as exc:
            self.renderer.print_error(f"Command failed: /{name}", str(exc))
        return True

    def list_commands(self) -> List[str]:
        return sorted({c.name for c in self._commands.values()})
