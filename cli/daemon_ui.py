"""JARVIS MK-X — Claude-Code-style UI integrated with the existing daemon.

Connects to the daemon's UI WebSocket bridge (ws://127.0.0.1:8787/ws) and uses
the existing ``cli.bridge.AgentBridge`` + ``cli.renderer.Renderer`` to render
a Claude-Code-style terminal interface.

Key design points:
- No second transport, no IPC module, no named pipes.
- Pure WebSocket client against the daemon's existing UI bridge.
- Events flow: daemon UI bridge → cli.bridge.AgentBridge → cli.renderer.Renderer → Rich terminal display.
- Claude-Code-style features: streaming, tool lifecycle, permission prompts,
  compact context indicator, code change rendering.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.text import Text

from cli.bridge import AgentBridge
from cli.renderer import Renderer
from cli.layout import LayoutManager, LayoutMode, LayoutConfig
from cli.models import Mode, AppState, ConfirmationRequest, RiskLevel

logger = logging.getLogger("jarvis.daemon_ui")

# ── Daemon UI WebSocket protocol constants ──────────────────────────────────

WS_URL_BASE = "ws://127.0.0.1"

# Mapping from daemon UI frame types to cli.bridge event names.
# The bridge's _translate() dispatches these to the appropriate handlers.
DAEMON_TO_BRIDGE_EVENT: Dict[str, str] = {
    "tool.call": "step.started",
    "tool.result": "step.completed",
    "chat.delta": "agent.delta",  # handled via stream_delta in renderer
    "chat.message": "assistant.message",
    "chat.done": "task.finished",
    "agent.event": "task.started",  # simplified phase tracking
    "log": "system.message",
    "telemetry": "telemetry.update",
    "provider.status": "provider.update",
    "mode.set": "permission.observed",
    "provider.select": "provider.update",
}


def _map_daemon_frame(frame_type: str, payload: dict) -> Optional[tuple[str, dict]]:
    """Convert a daemon UI frame into (bridge_event_name, bridge_payload).

    The cli.bridge.AgentBridge._translate() expects event names such as:
      - task.started
      - step.started
      - step.completed
      - permission.observed
      - task.finished
      - task.cancelled
      - context.compacted
    """
    event_name = DAEMON_TO_BRIDGE_EVENT.get(frame_type)
    if event_name is None:
        # Unknown frame type — skip it; the bridge has broad exception safety.
        return None

    # Extract the inner payload; daemon frames nest their content under .payload
    inner = payload.get("payload", {}) if isinstance(payload, dict) else {}
    # Ensure we always pass a dict
    if not isinstance(inner, dict):
        inner = {}
    return event_name, inner


# ── Core UI adapter ────────────────────────────────────────────────────────

class DaemonUI:
    """Bridge between daemon UI WebSocket and JARVIS CLI renderer.

    Responsibilities:
    - Open WS connection to daemon's UI bridge
    - Normalize frames → AgentBridge events
    - Pull status / models on demand
    - Exposes submit_goal() for sending user goals to the running daemon
    """

    def __init__(self, console: Console | None = None,
                 ui_port: int = 8787, project_dir: str | None = None) -> None:
        self.console = console or Console(highlight=False, emoji=False)
        self.ui_port = ui_port
        self.project_dir = str(Path(project_dir).resolve()) if project_dir else str(Path.cwd().resolve())
        self.ws: Any = None  # websocket client
        self.bridge = AgentBridge(renderer=Renderer(console=self.console))
        # The bridge's renderer.state is our single source of truth for display
        self.app_state: AppState = self.bridge.state
        self._running = False

    # ── WebSocket connection ───────────────────────────────────────────────

    async def _connect(self) -> bool:
        """Connect to the daemon's UI WebSocket bridge."""
        try:
            import websockets
            self.ws = await websockets.connect(f"ws://127.0.0.1:{self.ui_port}/ws")
            logger.info("Connected to daemon UI bridge on port %s", self.ui_port)
            # Send initial hello
            await self.ws.send(json.dumps({"type": "hello", "payload": {}}))
            return True
        except ImportError:
            self.console.print("[error]Missing 'websockets' package. "
                               "Run: pip install websockets")
            return False
        except Exception as exc:
            self.console.print(f"[error]Failed to connect to daemon UI: {exc}")
            return False

    async def _disconnect(self) -> None:
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

    async def _handle_frame(self, frame: dict) -> None:
        """Process a single UI WebSocket frame.

        Maps the frame to an AgentBridge event and lets the bridge update
        the shared AppState (which the renderer reads).
        """
        ftype = frame.get("type", "")
        payload = frame.get("payload", {}) or {}

        logger.debug("UI frame: %s", ftype)

        mapped = _map_daemon_frame(ftype, payload)
        if mapped is None:
            return

        event_name, event_payload = mapped

        try:
            self.bridge.on_event(event_name, event_payload)
        except Exception as exc:
            logger.error("Bridge event %s failed: %s", event_name, exc)
            self.console.print(f"[error]UI event error: {exc}[/error]")

        # Pull refreshed status after each event so the status bar stays current
        # (lightweight — just reads from the daemon's current state)
        if event_name in ("task.started", "step.started", "step.completed",
                          "task.finished", "task.cancelled", "permission.observed"):
            await self._pull_status_lite()

    async def _pull_status_lite(self) -> None:
        """Lightweight status pull — just model + provider from daemon."""
        if not self.ws:
            return
        try:
            await self.ws.send(json.dumps({
                "type": "status.request",
                "payload": {}
            }))
        except Exception:
            pass

    # ── Public API ──────────────────────────────────────────────────────────

    async def run_interactive(self) -> None:
        """Main UI loop: receive daemon frames + process user input."""
        self._running = True

        # Connect to daemon
        connected = await self._connect()
        if not connected:
            return

        self.console.print("[bold cyan]JARVIS MK-X — daemon connected[/bold cyan]")
        self.console.print("[dim]Type /help for commands[/dim]")
        self.console.print("")

        try:
            async for raw in self.ws:
                try:
                    if raw is None:
                        break
                    frame = json.loads(raw) if isinstance(raw, str) else raw
                    await self._handle_frame(frame)
                except json.JSONDecodeError:
                    logger.warning("Malformed JSON from daemon UI")
                    self.console.print("[error]Malformed JSON from daemon[/error]")
                    continue
                except Exception as exc:
                    logger.error("Error handling UI frame: %s", exc)
                    self.console.print(f"[error]UI error: {exc}[/error]")

        except asyncio.CancelledError:
            logger.info("UI loop cancelled")
        except Exception as exc:
            logger.error("UI loop error: %s", exc)
            self.console.print(f"[error]UI loop error: {exc}[/error]")
        finally:
            self._running = False
            await self._disconnect()
            self.console.print("[dim]Daemon UI disconnected[/dim]")

    async def submit_goal(self, goal: str) -> None:
        """Submit a goal to the running daemon, streaming events back."""
        if not self.ws:
            self.console.print("[error]Not connected to daemon[/error]")
            return

        try:
            await self.ws.send(json.dumps({
                "type": "chat.send",
                "payload": {
                    "sessionId": "cli-session",
                    "text": goal,
                }
            }))
        except Exception as exc:
            self.console.print(f"[error]Failed to submit goal: {exc}[/error]")

    def render_status_bar(self) -> Text:
        """Render the Claude-style compact status bar at the bottom."""
        width = self.console.size.width
        sep = Text(" │ ", style="dim")
        parts: List[Text] = [
            Text("JARVIS", style="bold primary"),
            sep,
            Text(self.app_state.mode.value, style="jarvis.accent"),
        ]

        # Model/provider — show on wider terminals
        if width >= 70:
            model_label = self.app_state.model or "—"
            parts += [sep, Text(model_label, style="jarvis.secondary")]

        # Token usage — Claude-style compact indicator
        used, limit = self.app_state.tokens_used, self.app_state.tokens_limit
        if used > 0 and limit > 0:
            pct = used / limit * 100
            bar = "█" * max(1, int(pct / 10)) + "░" * max(0, 10 - int(pct / 10))
            token_str = f"[{''.join(bar)}] {used}/{limit}"
        else:
            token_str = f"{used}/{limit}"
        parts += [sep, Text(token_str, style="jarvis.dim")]

        # Connection indicator
        conn_style = "jarvis.success" if self.app_state.connection == "ONLINE" else "jarvis.warning"
        parts += [sep, Text(self.app_state.connection, style=conn_style)]

        # Timestamp
        from datetime import datetime
        now = datetime.now().strftime("%H:%M:%S")
        parts += [sep, Text(now, style="jarvis.dim")]

        return Text.assemble(*parts)

    def render_header(self) -> Text:
        """Render the top header bar — mirrors the Claude Code layout."""
        connected = getattr(self.app_state, 'connection', '') == 'ONLINE'
        dot = f"[green]● Connected[/green]" if connected else f"[red]● Offline[/red]"
        bits = [
            Text("JARVIS MK-X", style="bold cyan"),
            Text(dot, style="bold"),
        ]
        if self.app_state.mode:
            bits.append(Text(f"mode={self.app_state.mode}", style="magenta"))
        if self.app_state.model:
            bits.append(Text(self.app_state.model, style="yellow"))
        return Text("   │   ").join(bits)


# ── CLI entrypoint ──────────────────────────────────────────────────────────

async def _ui_main(ui_port: int = 8787, project_dir: str | None = None) -> None:
    """Entry point for the daemon-integrated Claude-Code UI."""
    console = Console(highlight=False, emoji=False)
    ui = DaemonUI(console=console, ui_port=ui_port, project_dir=project_dir)

    # Show connection banner
    console.print("[bold cyan]JARVIS MK-X[/bold cyan]")
    console.print("[dim]Connecting to daemon UI bridge...[/dim]")
    console.print("")

    # Run the interactive loop
    await ui.run_interactive()


def main() -> None:
    """CLI entry point."""
    import sys
    ui_port = 8787
    project_dir = None
    args = sys.argv[1:]

    # Parse simple args
    for i, arg in enumerate(args):
        if arg.startswith("--port="):
            try:
                ui_port = int(arg.split("=", 1)[1])
            except ValueError:
                pass
        elif arg.startswith("--project="):
            project_dir = arg.split("=", 1)[1]

    asyncio.run(_ui_main(ui_port=ui_port, project_dir=project_dir))


if __name__ == "__main__":
    main()