"""Factory: registers all built-in action handlers in the ActionRegistry."""
from core.action_handlers import (
    AudioHandler,
    BrowserHandler,
    ClipboardHandler,
    DesktopControlHandler,
    DiskHandler,
    DisplayHandler,
    FileHandler,
    InputHandler,
    NetworkHandler,
    OpenAppHandler,
    ProcessHandler,
    ScreenAnalyzerHandler,
    ScreenCaptureHandler,
    ServiceHandler,
    SettingsHandler,
    ShellHandler,
    StartupHandler,
    SystemStatusHandler,
    TaskHandler,
    VectorQueryHandler,
    WebSearchHandler,
    WindowHandler,
)
from core.action_registry import ActionRegistry


def register_all_actions(registry: ActionRegistry):
    registry.register("vision.screen_capture", ScreenCaptureHandler)
    registry.register("action.screen_analyzer", ScreenAnalyzerHandler)
    registry.register("action.browser", BrowserHandler)
    registry.register("action.desktop_control", DesktopControlHandler)
    registry.register("action.open", OpenAppHandler)
    registry.register("action.search", WebSearchHandler)
    registry.register("query.status", SystemStatusHandler)
    registry.register("action.file", FileHandler)
    registry.register("action.process", ProcessHandler)
    registry.register("action.shell", ShellHandler)
    registry.register("action.window", WindowHandler)
    registry.register("action.clipboard", ClipboardHandler)
    registry.register("action.settings", SettingsHandler)
    registry.register("action.input", InputHandler)
    registry.register("action.network", NetworkHandler)
    registry.register("action.service", ServiceHandler)
    registry.register("action.disk", DiskHandler)
    registry.register("action.audio", AudioHandler)
    registry.register("action.display", DisplayHandler)
    registry.register("action.startup", StartupHandler)
    registry.register("action.tasks", TaskHandler)
    registry.register("memory.vector_query", VectorQueryHandler)
