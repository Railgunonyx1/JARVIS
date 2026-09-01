"""
Mode Manager — handles execution modes and permission resolution.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import toml

from core.capability_registry import Capability, get_all_capabilities

_CAPABILITY_REGISTRY = get_all_capabilities()

logger = logging.getLogger("jarvis.mode")


class ExecutionMode(str):
    PLAN = "plan"
    CONTROLLED = "controlled"
    SMART = "smart"
    AGENT = "agent"


# Legacy planner/executor tool names (underscore) mapped to their capability
# registry equivalents (dot-separated). Resolution lets both the executor
# permission gate and the planner validation agree with the mode configs.
EXEC_TOOL_ALIASES = {
    "open_app": ["app.launch", "app.list"],
    "web_search": ["web.search"],
    "file_controller": ["filesystem.read", "filesystem.write", "filesystem.list"],
    "computer_control": ["input.keyboard", "input.mouse"],
    "computer_settings": ["system.query", "system.volume"],
    "desktop_control": ["desktop.control"],
    "process_manager": ["process.list", "process.kill", "process.start"],
    "shell": ["shell.run", "shell.execute", "terminal.write"],
    "window_manager": ["window.list", "window.focus", "window.close",
                       "window.minimize", "window.maximize", "window.resize", "window.move"],
    "clipboard": ["clipboard.read", "clipboard.write", "clipboard.clear"],
    "service_manager": ["service.list", "service.start", "service.stop", "service.restart"],
    "startup_manager": ["startup.manage"],
    "task_scheduler": ["task.list", "task.manage", "schedule.create", "schedule.list"],
    "network": ["network.info", "network.status"],
    "display": ["display.manage"],
    "audio": ["audio.list", "audio.record", "media.control", "media.volume", "system.volume"],
    "disk": ["filesystem.list", "filesystem.read", "system.query"],
    "screen": ["screen.capture", "screen.analyze"],
    "screen_analyzer": ["screen.analyze", "screen.capture"],
    "browser": ["browser.control", "web.open", "web.navigate", "web.search"],
    "generated_code": ["filesystem.write"],
}


@dataclass
class ModePermissions:
    allowed: set[str] = field(default_factory=set)
    blocked: set[str] = field(default_factory=set)
    confirmation_required: set[str] = field(default_factory=set)
    sandbox: bool = False


@dataclass
class ModeConfig:
    name: str
    permissions: ModePermissions


class ModeManager:
    """Manages execution modes and capability permissions."""

    def __init__(self, config_dir: Path | None = None):
        if config_dir is None:
            config_dir = Path(__file__).resolve().parent.parent / "config" / "modes"
        self.config_dir = config_dir
        self.current_mode = ExecutionMode.SMART
        self._mode_configs: dict[ExecutionMode, ModeConfig] = {}
        self._load_all_modes()

    def _load_all_modes(self) -> None:
        """Load all mode configurations from TOML files."""
        if not self.config_dir.exists():
            logger.warning("Mode config directory not found: %s", self.config_dir)
            return

        for toml_file in self.config_dir.glob("*.toml"):
            mode_name = toml_file.stem
            try:
                data = toml.load(toml_file)
                mode_config = self._parse_mode_config(mode_name, data)
                self._mode_configs[ExecutionMode(mode_name)] = mode_config
                logger.info("Loaded mode: %s", mode_name)
            except Exception as e:
                logger.error("Failed to load mode %s: %s", mode_name, e)

    def _parse_mode_config(self, mode_name: str, data: dict[str, Any]) -> ModeConfig:
        """Parse mode configuration from TOML data."""
        perms = data.get("permissions", {})
        permissions = ModePermissions(
            allowed=set(perms.get("allowed", [])),
            blocked=set(perms.get("blocked", [])),
            confirmation_required=set(perms.get("confirmation_required", [])),
            sandbox=perms.get("sandbox", False),
        )
        return ModeConfig(name=mode_name, permissions=permissions)

    def set_mode(self, mode: ExecutionMode) -> bool:
        """Set the current execution mode."""
        if mode not in self._mode_configs:
            logger.warning("Unknown mode: %s", mode)
            return False
        self.current_mode = mode
        logger.info("Execution mode set to: %s", mode)
        return True

    def get_mode(self) -> ExecutionMode:
        """Get current execution mode."""
        return self.current_mode

    def get_mode_config(self, mode: ExecutionMode | None = None) -> ModeConfig | None:
        """Get configuration for a mode (defaults to current)."""
        mode = mode or self.current_mode
        return self._mode_configs.get(mode)

    def _resolve(self, capability: str) -> list[str]:
        """Expand a legacy underscore tool name to its capability names."""
        return EXEC_TOOL_ALIASES.get(capability, [capability])

    def is_allowed(self, capability: str, mode: ExecutionMode | None = None) -> bool:
        """Check if a capability is allowed in the given mode."""
        for cap in self._resolve(capability):
            if self._is_allowed_cap(cap, mode):
                return True
        return False

    def _is_allowed_cap(self, capability: str, mode: ExecutionMode | None = None) -> bool:
        config = self.get_mode_config(mode)
        if not config:
            return False

        perms = config.permissions

        # Wildcard allow
        if "*" in perms.allowed:
            return capability not in perms.blocked

        # Explicit allow
        if capability in perms.allowed:
            return capability not in perms.blocked

        return False

    def is_blocked(self, capability: str, mode: ExecutionMode | None = None) -> bool:
        """Check if a capability is explicitly blocked."""
        config = self.get_mode_config(mode)
        if not config:
            return True
        for cap in self._resolve(capability):
            if cap in config.permissions.blocked:
                return True
        return False

    def requires_confirmation(self, capability: str, mode: ExecutionMode | None = None) -> bool:
        """Check if a capability requires confirmation."""
        config = self.get_mode_config(mode)
        if not config:
            return True
        for cap in self._resolve(capability):
            if cap in config.permissions.confirmation_required:
                return True
        return False

    def get_allowed_capabilities(self, mode: ExecutionMode | None = None) -> list[Capability]:
        """Get all allowed capabilities for a mode as Capability objects."""
        mode = mode or self.current_mode
        allowed_names = []
        for cap_name in _CAPABILITY_REGISTRY:
            if self.is_allowed(cap_name, mode):
                allowed_names.append(cap_name)
        return [_CAPABILITY_REGISTRY[name] for name in allowed_names]

    def get_available_tool_names(self, mode: ExecutionMode | None = None) -> list[str]:
        """Get tool names available in current mode (for planner)."""
        return [cap.name for cap in self.get_allowed_capabilities(mode)]

    def get_confirmation_required(self, capability: str, mode: ExecutionMode | None = None) -> bool:
        """Check if capability requires confirmation (includes registry default)."""
        # Check mode config first
        if self.requires_confirmation(capability, mode):
            return True
        # Fall back to capability registry default
        for cap in self._resolve(capability):
            reg = _CAPABILITY_REGISTRY.get(cap)
            if reg:
                return reg.requires_confirmation
        return True  # Unknown = confirm

    def is_sandboxed(self, mode: ExecutionMode | None = None) -> bool:
        """Check if mode runs in sandbox."""
        config = self.get_mode_config(mode)
        return config.permissions.sandbox if config else False

    def get_mode_summary(self) -> dict[str, Any]:
        """Get summary of current mode for UI/diagnostics."""
        config = self.get_mode_config()
        if not config:
            return {"mode": self.current_mode, "error": "No config loaded"}

        allowed_caps = self.get_allowed_capabilities()
        return {
            "mode": self.current_mode,
            "allowed_count": len(allowed_caps),
            "blocked_count": len(config.permissions.blocked),
            "confirmation_count": len(config.permissions.confirmation_required),
            "sandbox": config.permissions.sandbox,
            "allowed_categories": list(set(c.category.value for c in allowed_caps)),
        }


# Global singleton
_mode_manager: ModeManager | None = None


def get_mode_manager() -> ModeManager:
    global _mode_manager
    if _mode_manager is None:
        _mode_manager = ModeManager()
    return _mode_manager


def set_execution_mode(mode: ExecutionMode) -> bool:
    return get_mode_manager().set_mode(mode)


def get_current_mode() -> ExecutionMode:
    return get_mode_manager().get_mode()
