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
    def __init__(self, renderer: "Renderer", bridge=None) -> None:
        self.renderer = renderer
        self.bridge = bridge
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
            if self.bridge is not None:
                self.bridge.pull_status()
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
                status_cmd(args)
                r.print("Modes: agent | plan | controlled | smart")
                return
            try:
                m = Mode(args[0].upper())
            except ValueError:
                r.print_error("Unknown mode", "Use: agent | plan | controlled | smart")
                return
            if self.bridge is not None and self.bridge.loop is not None:
                self.bridge.loop.permissions.set_mode(m.value.lower())
                self.bridge.pull_status()
            else:
                r.set_mode(m)
            r.print_success(f"Mode → {m.value}  ({MODE_HELP[m]})")

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
            if self.bridge is not None and self.bridge.loop is not None:
                reg = self.bridge.loop.registry
                r.print("REGISTERED TOOLS")
                for tool in reg.list():
                    r.print(f"  {tool.name} — {tool.description}")
                return
            if not r.state.events:
                r.print("No events yet.")
                return
            r.print(r.render_activity())

        def memory_cmd(args: List[str]) -> None:
            if self.bridge is not None:
                query = args[0] if args else ""
                self.bridge.refresh_memory(query)
            r.set_workspace("memory")
            r.layout_mgr.set_mode("memory")
            r.print(r.render_memory())

        def audit_cmd(args: List[str]) -> None:
            if self.bridge is not None:
                limit = 12
                if args and args[0].isdigit():
                    limit = int(args[0])
                self.bridge.refresh_audit(limit)
            r.set_workspace("audit")
            r.layout_mgr.set_mode("audit")
            r.print(r.render_audit())

        def code_cmd(args: List[str]) -> None:
            if self.bridge is not None:
                self.bridge.refresh_code(path=args[0] if args else "")
            r.set_workspace("code")
            r.layout_mgr.set_mode("code")
            r.print(r.render_code_header())
            r.print(r.render_code_files())
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

        def model_cmd(args: List[str]) -> None:
            s = r.state
            if args:
                r.print_error("model switching not wired", "Only status is available in this session")
                return
            r.print(f"Model    : {s.model}")
            r.print(f"Tokens   : {s.tokens_used}/{s.tokens_limit}")

        def context_cmd(args: List[str]) -> None:
            if self.bridge is None:
                r.print_error("Context backend not connected", "Run the interactive session to enable it.")
                return
            loop = self.bridge.loop
            report = loop.context_manager.last_report if loop is not None else None
            if report is None:
                r.print("No context report yet — run a task first")
                return
            data = report.to_dict()
            r.print(f"[context] {data['total_tokens']}/{data['total_budget']} tokens"
                    + (" [compacted]" if data["compacted"] else ""))
            for section in data.get("sections", []):
                ratio = section["ratio"]
                bar = "█" * max(0, int(ratio * 12)) + "░" * max(0, 12 - int(ratio * 12))
                r.print(f"  {section['section']:<9} {bar} {section['tokens']}/{section['budget']}")

        def sessions_cmd(args: List[str]) -> None:
            from core.event_store import get_event_store

            traces = get_event_store().recent_traces(limit=10)
            if not traces:
                r.print("No task history yet")
                return
            r.print("RECENT TASKS")
            for trace in traces:
                ts = __import__("time").strftime("%Y-%m-%d %H:%M:%S",
                                                 __import__("time").localtime(trace["timestamp"]))
                r.print(f"  {trace['trace_id']}  {ts}")

        def resume_cmd(args: List[str]) -> None:
            if self.bridge is None or self.bridge.loop is None:
                r.print_error("Session backend not connected", "Run the interactive session to enable it.")
                return
            goal = getattr(self.bridge.loop, "_last_goal", None)
            if not goal:
                r.print_error("No previous goal to resume")
                return
            r.print_success(f"Will resume: {goal[:80]}")
            # The REPL loop re-runs this via its own dispatch path.

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
        self._register(Command("model", "Show model + token status", model_cmd))
        self._register(Command("context", "Show context window", context_cmd))
        self._register(Command("sessions", "List recent tasks", sessions_cmd))
        self._register(Command("resume", "Resume the last goal", resume_cmd))
        self._register(Command("permissions", "Show permission/mode status", status_cmd, ["perms"]))

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
