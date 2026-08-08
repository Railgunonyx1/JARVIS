"""Action handlers — bridge between ActionRegistry and existing action modules.

Each handler wraps the existing module function for backward compatibility.
"""
import asyncio
import logging
from typing import Optional

from core.action_registry import ActionHandler

logger = logging.getLogger("jarvis.actions")

# ── Screen Capture ──────────────────────────────────────────────

class ScreenCaptureHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        try:
            from actions.screen_capture import analyze_screen
            key = (api_keys or {}).get("gemini", "")
            return await asyncio.to_thread(analyze_screen, prompt=text, api_key=key)
        except Exception as e:
            logger.error("screen_capture failed: %s", e)
            return f"Screen analysis failed: {e}"

# ── Screen Analyzer ─────────────────────────────────────────────

class ScreenAnalyzerHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.screen_analyzer import screen_analyze
        return await asyncio.to_thread(screen_analyze, intent.entities)

# ── Browser ─────────────────────────────────────────────────────

class BrowserHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.browser_control import browser_action
        return await asyncio.to_thread(browser_action, intent.entities)

# ── Desktop Control ─────────────────────────────────────────────

class DesktopControlHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        try:
            from actions.desktop_automation import execute_desktop_action
            return await asyncio.to_thread(execute_desktop_action, action=text)
        except Exception as e:
            logger.error("desktop_control failed: %s", e)
            return f"Desktop action failed: {e}"

# ── Open App ────────────────────────────────────────────────────

class OpenAppHandler(ActionHandler):
    def __init__(self):
        self._fn = None

    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        app_name = intent.entities.get("app", "")
        if not app_name:
            return None
        try:
            if self._fn is None:
                from actions.open_app import open_app as _open_app
                self._fn = _open_app
            return await asyncio.to_thread(self._fn, parameters={"app_name": app_name})
        except Exception as e:
            return f"Failed to open {app_name}: {e}"

# ── Web Search ──────────────────────────────────────────────────

class WebSearchHandler(ActionHandler):
    def __init__(self):
        self._fn = None

    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        query = intent.entities.get("query", text)
        if not query:
            return None
        try:
            if self._fn is None:
                from actions.web_search import web_search as _web_search
                self._fn = _web_search
            key = (api_keys or {}).get("gemini", "")
            return await asyncio.to_thread(
                self._fn, parameters={"query": query, "mode": "search"},
                api_key=key,
            )
        except Exception as e:
            return f"Search failed: {e}"

# ── System Status ───────────────────────────────────────────────

class SystemStatusHandler(ActionHandler):
    def __init__(self):
        self._fn = None

    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        try:
            if self._fn is None:
                from actions.system_monitor import get_system_status as _get_system_status
                self._fn = _get_system_status
            s = await asyncio.to_thread(self._fn)
            lines = [
                f"CPU: {s['cpu_percent']}%",
                f"RAM: {s['ram_percent']}% ({s['ram_used_gb']}/{s['ram_total_gb']} GB)",
            ]
            if s.get("cpu_temp_c"):
                lines.append(f"Temp: {s['cpu_temp_c']}C")
            if s.get("gpu_percent") is not None:
                lines.append(f"GPU: {s['gpu_percent']}%")
            lines.extend([f"Uptime: {s['uptime']}", f"Processes: {s['process_count']}"])
            return "\n".join(lines)
        except Exception:
            return "System status unavailable."

# ── File Manager ────────────────────────────────────────────────

class FileHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.file_manager import file_action
        action_name = intent.entities.get("action", "list")
        return await asyncio.to_thread(file_action, action_name, intent.entities)

# ── Process Manager ─────────────────────────────────────────────

class ProcessHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.process_manager import process_action
        action_name = intent.entities.get("action", "list")
        return await asyncio.to_thread(process_action, action_name, intent.entities)

# ── Shell ───────────────────────────────────────────────────────

class ShellHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.shell_exec import shell_action
        action_name = intent.entities.get("action", "run")
        return await asyncio.to_thread(shell_action, action_name, intent.entities)

# ── Window Manager ──────────────────────────────────────────────

class WindowHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.window_manager import window_action
        action_name = intent.entities.get("action", "list")
        return await asyncio.to_thread(window_action, action_name, intent.entities)

# ── Clipboard ───────────────────────────────────────────────────

class ClipboardHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.clipboard_manager import clipboard_action
        action_name = intent.entities.get("action", "read")
        return await asyncio.to_thread(clipboard_action, action_name, intent.entities)

# ── System Settings ─────────────────────────────────────────────

class SettingsHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.system_settings import settings_action
        action_name = intent.entities.get("action", "")
        return await asyncio.to_thread(settings_action, action_name, intent.entities)

# ── Input Control ───────────────────────────────────────────────

class InputHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.input_control import input_action
        action_name = intent.entities.get("action", "")
        return await asyncio.to_thread(input_action, action_name, intent.entities)

# ── Network Manager ─────────────────────────────────────────────

class NetworkHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.network_manager import network_action
        action_name = intent.entities.get("action", "status")
        return await asyncio.to_thread(network_action, action_name, intent.entities)

# ── Service Manager ─────────────────────────────────────────────

class ServiceHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.service_manager import service_action
        action_name = intent.entities.get("action", "list")
        return await asyncio.to_thread(service_action, action_name, intent.entities)

# ── Disk Manager ────────────────────────────────────────────────

class DiskHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.disk_manager import disk_action
        action_name = intent.entities.get("action", "info")
        return await asyncio.to_thread(disk_action, action_name, intent.entities)

# ── Audio Manager ───────────────────────────────────────────────

class AudioHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.audio_manager import audio_action
        action_name = intent.entities.get("action", "devices")
        return await asyncio.to_thread(audio_action, action_name, intent.entities)

# ── Display Manager ─────────────────────────────────────────────

class DisplayHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.display_manager import display_action
        action_name = intent.entities.get("action", "")
        return await asyncio.to_thread(display_action, action_name, intent.entities)

# ── Startup Manager ─────────────────────────────────────────────

class StartupHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.startup_manager import startup_action
        action_name = intent.entities.get("action", "list")
        return await asyncio.to_thread(startup_action, action_name, intent.entities)

# ── Task Scheduler ──────────────────────────────────────────────

class TaskHandler(ActionHandler):
    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        from actions.task_scheduler import task_action
        action_name = intent.entities.get("action", "list")
        return await asyncio.to_thread(task_action, action_name, intent.entities)


# ── Vector Query (memory recall) ────────────────────────────────

class VectorQueryHandler(ActionHandler):
    """Queries vector memory. Requires vector_memory to be set on the instance."""

    async def handle(self, intent, text: str, api_keys: dict = None) -> Optional[str]:
        query = intent.entities.get("query", text)
        if not query:
            return None
        vm = getattr(self, "vector_memory", None)
        if vm:
            try:
                matches = vm.search_similar(query, top_k=3)
                if matches:
                    formatted = "\n".join(
                        [f"• {m['text']} (relevance: {int(m['score']*100)}%)" for m in matches]
                    )
                    return f"Here is what I recalled from semantic memory, sir:\n{formatted}"
            except Exception as e:
                logger.error("vector_query failed: %s", e)
        return "No matching memories found in vector memory."
