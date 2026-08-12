"""Hierarchical + Searchable Capability Registry.

Tree structure with lazy branch discovery. Plugins add branches
via atomic merge. Searchable by tags, risk, permissions, cost.

The old flat CAPABILITY_REGISTRY dict is preserved as a compatibility
shim built from the tree.
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("jarvis.capability.v2")


# ── Enums (preserved from v1 for backward compat) ──────────────

class CapabilityRisk(Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CapabilityCategory(Enum):
    APP = "app"
    MEDIA = "media"
    SYSTEM = "system"
    CLIPBOARD = "clipboard"
    WINDOW = "window"
    MEMORY = "memory"
    WEB = "web"
    FILESYSTEM = "filesystem"
    TERMINAL = "terminal"
    PROCESS = "process"
    SERVICE = "service"
    REGISTRY = "registry"
    SHELL = "shell"
    PACKAGE = "package"
    NETWORK = "network"
    DISPLAY = "display"
    AUDIO = "audio"
    STARTUP = "startup"
    TASK = "task"
    SCHEDULE = "schedule"
    EXTERNAL = "external"
    AI = "ai"


# ── Core data model ────────────────────────────────────────────

@dataclass
class Capability:
    name: str
    category: CapabilityCategory
    risk: CapabilityRisk
    description: str = ""
    requires_confirmation: bool = False
    is_destructive: bool = False
    affected_resources: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    cost: float = 0.0
    latency: str = "medium"
    provider: str = ""
    examples: list[str] = field(default_factory=list)


@dataclass
class _BranchNode:
    name: str
    capabilities: dict[str, Capability] = field(default_factory=dict)
    children: dict[str, "_BranchNode"] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def flatten(self, prefix: str = "") -> dict[str, Capability]:
        result = {}
        full_prefix = f"{prefix}.{self.name}" if prefix else self.name
        for c in self.capabilities.values():
            result[c.name] = c
        for child in self.children.values():
            result.update(child.flatten(full_prefix))
        return result


class CapabilityTree:
    """Immutable tree of capabilities. Atomic merge for plugin branches."""

    def __init__(self):
        self._root = _BranchNode(name="")
        self._flat_cache: dict[str, Capability] = {}
        self._dirty = True

    # ── Build from flat dict ────────────────────────────────────

    @classmethod
    def from_registry(cls, registry: dict[str, Capability]) -> "CapabilityTree":
        tree = cls()
        for cap in registry.values():
            tree._insert_into_tree(cap)
        tree._rebuild_cache()
        return tree

    def _insert_into_tree(self, cap: Capability):
        parts = cap.name.split(".")
        node = self._root
        for i, part in enumerate(parts[:-1]):
            if part not in node.children:
                node.children[part] = _BranchNode(name=part)
            node = node.children[part]
        leaf = parts[-1]
        node.capabilities[leaf] = cap

    # ── Atomic merge (for plugins) ──────────────────────────────

    def merge(self, branch: "CapabilityTree") -> bool:
        try:
            self._merge_node(self._root, branch._root)
            self._dirty = True
            self._rebuild_cache()
            return True
        except Exception as e:
            logger.error("Capability merge failed: %s", e)
            return False

    def _merge_node(self, target: _BranchNode, source: _BranchNode):
        for name, child in source.children.items():
            if name in target.children:
                self._merge_node(target.children[name], child)
            else:
                target.children[name] = child
        for name, cap in source.capabilities.items():
            if name not in target.capabilities:
                target.capabilities[name] = cap

    # ── Build branch (for plugins) ──────────────────────────────

    @staticmethod
    def build_branch(caps: list[Capability]) -> "CapabilityTree":
        tree = CapabilityTree()
        for cap in caps:
            tree._insert_into_tree(cap)
        return tree

    # ── Resolution ──────────────────────────────────────────────

    def resolve(self, path: str) -> Capability | None:
        self._ensure_cache()
        return self._flat_cache.get(path)

    def subtree(self, prefix: str) -> dict[str, Capability]:
        self._ensure_cache()
        return {k: v for k, v in self._flat_cache.items()
                if k.startswith(prefix)}

    # ── Search ──────────────────────────────────────────────────

    def search(self, tags: list[str] | None = None,
               risk: CapabilityRisk | None = None,
               max_risk: CapabilityRisk | None = None,
               permissions: list[str] | None = None,
               max_cost: float | None = None,
               latency: str | None = None) -> list[Capability]:
        self._ensure_cache()
        results = list(self._flat_cache.values())

        if tags:
            tag_set = set(tags)
            results = [c for c in results if tag_set & set(c.tags)]

        if risk:
            results = [c for c in results if c.risk == risk]

        if max_risk:
            risk_order = {r: i for i, r in enumerate(CapabilityRisk)}
            results = [c for c in results
                       if risk_order.get(c.risk, 99) <= risk_order.get(max_risk, 99)]

        if permissions:
            perm_set = set(permissions)
            results = [c for c in results if perm_set & set(c.permissions)]

        if max_cost is not None:
            results = [c for c in results if c.cost <= max_cost]

        if latency:
            lat_order = {"low": 0, "medium": 1, "high": 2}
            results = [c for c in results
                       if lat_order.get(c.latency, 99) <= lat_order.get(latency, 99)]

        return results

    def query(self, tags: list[str] | None = None,
              risk: CapabilityRisk | None = None,
              permissions: list[str] | None = None) -> list[str]:
        results = self.search(tags=tags, risk=risk, permissions=permissions)
        return [c.name for c in results]

    # ── Stats ───────────────────────────────────────────────────

    def count(self) -> int:
        self._ensure_cache()
        return len(self._flat_cache)

    def get_stats(self) -> dict[str, Any]:
        self._ensure_cache()
        by_risk = {}
        for c in self._flat_cache.values():
            by_risk.setdefault(c.risk.value, 0)
            by_risk[c.risk.value] += 1
        return {
            "total": len(self._flat_cache),
            "by_risk": by_risk,
            "tree_depth": self._max_depth(self._root),
        }

    # ── Internal ────────────────────────────────────────────────

    def _ensure_cache(self):
        if self._dirty:
            self._rebuild_cache()

    def _rebuild_cache(self):
        self._flat_cache = self._root.flatten()
        self._dirty = False

    @staticmethod
    def _max_depth(node: _BranchNode) -> int:
        if not node.children:
            return 1
        return 1 + max(CapabilityTree._max_depth(c) for c in node.children.values())


# ── Flat registry (backward compatibility) ─────────────────────
# Built from the tree. Same content as the old CAPABILITY_REGISTRY.

_FLAT_REGISTRY: dict[str, Capability] = {
    # App
    "app.launch": Capability(name="app.launch", category=CapabilityCategory.APP, risk=CapabilityRisk.SAFE, description="Launch installed applications", tags=["app", "launch"]),
    "app.close": Capability(name="app.close", category=CapabilityCategory.APP, risk=CapabilityRisk.LOW, description="Close running applications", is_destructive=True, tags=["app", "close"]),
    "app.list": Capability(name="app.list", category=CapabilityCategory.APP, risk=CapabilityRisk.SAFE, description="List installed applications", tags=["app", "list"]),
    # Media
    "media.control": Capability(name="media.control", category=CapabilityCategory.MEDIA, risk=CapabilityRisk.SAFE, description="Control media playback", tags=["media", "playback"]),
    "media.volume": Capability(name="media.volume", category=CapabilityCategory.MEDIA, risk=CapabilityRisk.SAFE, description="Adjust media volume", tags=["media", "volume"]),
    # System
    "system.volume": Capability(name="system.volume", category=CapabilityCategory.SYSTEM, risk=CapabilityRisk.SAFE, description="Adjust system volume", tags=["system", "volume"]),
    "system.query": Capability(name="system.query", category=CapabilityCategory.SYSTEM, risk=CapabilityRisk.SAFE, description="Query system information", tags=["system", "query"]),
    "system.shutdown": Capability(name="system.shutdown", category=CapabilityCategory.SYSTEM, risk=CapabilityRisk.CRITICAL, description="Shutdown the computer", requires_confirmation=True, is_destructive=True, affected_resources=["system"], tags=["system", "power", "dangerous"]),
    "system.restart": Capability(name="system.restart", category=CapabilityCategory.SYSTEM, risk=CapabilityRisk.CRITICAL, description="Restart the computer", requires_confirmation=True, is_destructive=True, affected_resources=["system"], tags=["system", "power", "dangerous"]),
    "system.sleep": Capability(name="system.sleep", category=CapabilityCategory.SYSTEM, risk=CapabilityRisk.MEDIUM, description="Put system to sleep", requires_confirmation=True, tags=["system", "power"]),
    # Clipboard
    "clipboard.read": Capability(name="clipboard.read", category=CapabilityCategory.CLIPBOARD, risk=CapabilityRisk.LOW, description="Read clipboard contents", tags=["clipboard", "read"]),
    "clipboard.write": Capability(name="clipboard.write", category=CapabilityCategory.CLIPBOARD, risk=CapabilityRisk.LOW, description="Write to clipboard", tags=["clipboard", "write"]),
    "clipboard.clear": Capability(name="clipboard.clear", category=CapabilityCategory.CLIPBOARD, risk=CapabilityRisk.LOW, description="Clear clipboard", tags=["clipboard", "clear"]),
    # Window
    "window.list": Capability(name="window.list", category=CapabilityCategory.WINDOW, risk=CapabilityRisk.SAFE, description="List open windows", tags=["window", "list"]),
    "window.focus": Capability(name="window.focus", category=CapabilityCategory.WINDOW, risk=CapabilityRisk.LOW, description="Focus a window", tags=["window", "focus"]),
    "window.close": Capability(name="window.close", category=CapabilityCategory.WINDOW, risk=CapabilityRisk.LOW, description="Close a window", tags=["window", "close"]),
    "window.minimize": Capability(name="window.minimize", category=CapabilityCategory.WINDOW, risk=CapabilityRisk.LOW, description="Minimize a window", tags=["window", "minimize"]),
    "window.maximize": Capability(name="window.maximize", category=CapabilityCategory.WINDOW, risk=CapabilityRisk.LOW, description="Maximize a window", tags=["window", "maximize"]),
    "window.resize": Capability(name="window.resize", category=CapabilityCategory.WINDOW, risk=CapabilityRisk.LOW, description="Resize a window", tags=["window", "resize"]),
    "window.move": Capability(name="window.move", category=CapabilityCategory.WINDOW, risk=CapabilityRisk.LOW, description="Move a window", tags=["window", "move"]),
    # Memory
    "memory.store": Capability(name="memory.store", category=CapabilityCategory.MEMORY, risk=CapabilityRisk.SAFE, description="Store information in memory", tags=["memory", "store"]),
    "memory.recall": Capability(name="memory.recall", category=CapabilityCategory.MEMORY, risk=CapabilityRisk.SAFE, description="Recall stored information", tags=["memory", "recall"]),
    "memory.clear": Capability(name="memory.clear", category=CapabilityCategory.MEMORY, risk=CapabilityRisk.LOW, description="Clear memory", is_destructive=True, tags=["memory", "clear"]),
    "memory.forget": Capability(name="memory.forget", category=CapabilityCategory.MEMORY, risk=CapabilityRisk.LOW, description="Forget specific information", tags=["memory", "forget"]),
    "memory.vector_store": Capability(name="memory.vector_store", category=CapabilityCategory.MEMORY, risk=CapabilityRisk.SAFE, description="Store vector embedding", tags=["memory", "vector"]),
    "memory.vector_query": Capability(name="memory.vector_query", category=CapabilityCategory.MEMORY, risk=CapabilityRisk.SAFE, description="Query semantic memory", tags=["memory", "vector", "search"]),
    # Web
    "web.search": Capability(name="web.search", category=CapabilityCategory.WEB, risk=CapabilityRisk.SAFE, description="Search the web", tags=["web", "search"]),
    "web.open": Capability(name="web.open", category=CapabilityCategory.WEB, risk=CapabilityRisk.SAFE, description="Open a URL in browser", tags=["web", "open"]),
    "web.navigate": Capability(name="web.navigate", category=CapabilityCategory.WEB, risk=CapabilityRisk.SAFE, description="Navigate browser to URL", tags=["web", "navigate"]),
    "web.scrape": Capability(name="web.scrape", category=CapabilityCategory.WEB, risk=CapabilityRisk.MEDIUM, description="Scrape web page content", tags=["web", "scrape"]),
    # Filesystem
    "filesystem.read": Capability(name="filesystem.read", category=CapabilityCategory.FILESYSTEM, risk=CapabilityRisk.SAFE, description="Read files", tags=["filesystem", "read"]),
    "filesystem.write": Capability(name="filesystem.write", category=CapabilityCategory.FILESYSTEM, risk=CapabilityRisk.HIGH, description="Write to files", requires_confirmation=True, affected_resources=["filesystem"], tags=["filesystem", "write", "dangerous"]),
    "filesystem.delete": Capability(name="filesystem.delete", category=CapabilityCategory.FILESYSTEM, risk=CapabilityRisk.CRITICAL, description="Delete files", requires_confirmation=True, is_destructive=True, affected_resources=["filesystem"], tags=["filesystem", "delete", "dangerous"]),
    "filesystem.list": Capability(name="filesystem.list", category=CapabilityCategory.FILESYSTEM, risk=CapabilityRisk.SAFE, description="List files in directory", tags=["filesystem", "list"]),
    "filesystem.copy": Capability(name="filesystem.copy", category=CapabilityCategory.FILESYSTEM, risk=CapabilityRisk.MEDIUM, description="Copy files", requires_confirmation=True, tags=["filesystem", "copy"]),
    "filesystem.move": Capability(name="filesystem.move", category=CapabilityCategory.FILESYSTEM, risk=CapabilityRisk.MEDIUM, description="Move or rename files", requires_confirmation=True, tags=["filesystem", "move"]),
    # Terminal
    "terminal.list": Capability(name="terminal.list", category=CapabilityCategory.TERMINAL, risk=CapabilityRisk.SAFE, description="List active terminals", tags=["terminal", "list"]),
    "terminal.write": Capability(name="terminal.write", category=CapabilityCategory.TERMINAL, risk=CapabilityRisk.HIGH, description="Write to terminal", requires_confirmation=True, tags=["terminal", "write", "dangerous"]),
    # Process
    "process.list": Capability(name="process.list", category=CapabilityCategory.PROCESS, risk=CapabilityRisk.SAFE, description="List running processes", tags=["process", "list"]),
    "process.kill": Capability(name="process.kill", category=CapabilityCategory.PROCESS, risk=CapabilityRisk.HIGH, description="Kill a process", requires_confirmation=True, is_destructive=True, tags=["process", "kill", "dangerous"]),
    "process.start": Capability(name="process.start", category=CapabilityCategory.PROCESS, risk=CapabilityRisk.MEDIUM, description="Start a process", tags=["process", "start"]),
    # Service
    "service.list": Capability(name="service.list", category=CapabilityCategory.SERVICE, risk=CapabilityRisk.SAFE, description="List services", tags=["service", "list"]),
    "service.start": Capability(name="service.start", category=CapabilityCategory.SERVICE, risk=CapabilityRisk.MEDIUM, description="Start a service", tags=["service", "start"]),
    "service.stop": Capability(name="service.stop", category=CapabilityCategory.SERVICE, risk=CapabilityRisk.MEDIUM, description="Stop a service", requires_confirmation=True, tags=["service", "stop"]),
    "service.restart": Capability(name="service.restart", category=CapabilityCategory.SERVICE, risk=CapabilityRisk.MEDIUM, description="Restart a service", requires_confirmation=True, tags=["service", "restart"]),
    # Shell
    "shell.execute": Capability(name="shell.execute", category=CapabilityCategory.SHELL, risk=CapabilityRisk.CRITICAL, description="Execute shell command", requires_confirmation=True, is_destructive=True, affected_resources=["system"], tags=["shell", "execute", "dangerous"]),
    "shell.run": Capability(name="shell.run", category=CapabilityCategory.SHELL, risk=CapabilityRisk.CRITICAL, description="Run shell command (alias)", requires_confirmation=True, is_destructive=True, tags=["shell", "execute", "dangerous"]),
    # Package
    "package.install": Capability(name="package.install", category=CapabilityCategory.PACKAGE, risk=CapabilityRisk.HIGH, description="Install software packages", requires_confirmation=True, is_destructive=True, affected_resources=["filesystem"], tags=["package", "install", "dangerous"]),
    "package.uninstall": Capability(name="package.uninstall", category=CapabilityCategory.PACKAGE, risk=CapabilityRisk.HIGH, description="Uninstall software packages", requires_confirmation=True, is_destructive=True, affected_resources=["filesystem"], tags=["package", "uninstall", "dangerous"]),
    # Desktop
    "desktop.control": Capability(name="desktop.control", category=CapabilityCategory.DISPLAY, risk=CapabilityRisk.MEDIUM, description="Control desktop automation", requires_confirmation=True, tags=["desktop", "automation"]),
    # Browser
    "browser.control": Capability(name="browser.control", category=CapabilityCategory.WEB, risk=CapabilityRisk.MEDIUM, description="Control browser via keyboard shortcuts", requires_confirmation=True, tags=["browser", "control"]),
    # Screen
    "screen.capture": Capability(name="screen.capture", category=CapabilityCategory.DISPLAY, risk=CapabilityRisk.MEDIUM, description="Capture and analyze screen", tags=["screen", "capture", "vision"]),
    "screen.analyze": Capability(name="screen.analyze", category=CapabilityCategory.DISPLAY, risk=CapabilityRisk.MEDIUM, description="Analyze screen content", tags=["screen", "analyze", "vision"]),
    # Audio
    "audio.list": Capability(name="audio.list", category=CapabilityCategory.AUDIO, risk=CapabilityRisk.SAFE, description="List audio devices", tags=["audio", "list"]),
    "audio.record": Capability(name="audio.record", category=CapabilityCategory.AUDIO, risk=CapabilityRisk.LOW, description="Record audio", tags=["audio", "record"]),
    # Input
    "input.keyboard": Capability(name="input.keyboard", category=CapabilityCategory.SYSTEM, risk=CapabilityRisk.MEDIUM, description="Simulate keyboard input", requires_confirmation=True, tags=["input", "keyboard"]),
    "input.mouse": Capability(name="input.mouse", category=CapabilityCategory.SYSTEM, risk=CapabilityRisk.MEDIUM, description="Simulate mouse input", requires_confirmation=True, tags=["input", "mouse"]),
    # Network
    "network.status": Capability(name="network.status", category=CapabilityCategory.NETWORK, risk=CapabilityRisk.SAFE, description="Get network status", tags=["network", "status"]),
    "network.info": Capability(name="network.info", category=CapabilityCategory.NETWORK, risk=CapabilityRisk.SAFE, description="Get network information", tags=["network", "info"]),
    # Display
    "display.manage": Capability(name="display.manage", category=CapabilityCategory.DISPLAY, risk=CapabilityRisk.MEDIUM, description="Manage display settings", tags=["display", "manage"]),
    # Startup
    "startup.manage": Capability(name="startup.manage", category=CapabilityCategory.STARTUP, risk=CapabilityRisk.MEDIUM, description="Manage startup programs", requires_confirmation=True, tags=["startup", "manage"]),
    # Task
    "task.list": Capability(name="task.list", category=CapabilityCategory.TASK, risk=CapabilityRisk.SAFE, description="List scheduled tasks", tags=["task", "list"]),
    "task.manage": Capability(name="task.manage", category=CapabilityCategory.TASK, risk=CapabilityRisk.MEDIUM, description="Manage scheduled tasks", requires_confirmation=True, tags=["task", "manage"]),
    # AI
    "ai.llm.query": Capability(name="ai.llm.query", category=CapabilityCategory.AI, risk=CapabilityRisk.SAFE, description="Query LLM for reasoning", tags=["ai", "llm", "reasoning"]),
    "ai.vision.analyze": Capability(name="ai.vision.analyze", category=CapabilityCategory.AI, risk=CapabilityRisk.SAFE, description="Analyze image with vision model", tags=["ai", "vision", "image"]),
    "ai.embedding.create": Capability(name="ai.embedding.create", category=CapabilityCategory.AI, risk=CapabilityRisk.SAFE, description="Create text embeddings", tags=["ai", "embedding"]),
    # Scheduling
    "schedule.create": Capability(name="schedule.create", category=CapabilityCategory.SCHEDULE, risk=CapabilityRisk.MEDIUM, description="Create scheduled task", tags=["schedule", "create"]),
    "schedule.list": Capability(name="schedule.list", category=CapabilityCategory.SCHEDULE, risk=CapabilityRisk.SAFE, description="List scheduled tasks", tags=["schedule", "list"]),
    "schedule.delete": Capability(name="schedule.delete", category=CapabilityCategory.SCHEDULE, risk=CapabilityRisk.MEDIUM, description="Delete scheduled task", requires_confirmation=True, tags=["schedule", "delete"]),
}

# Build tree from flat registry
_tree: CapabilityTree | None = None


def _get_tree() -> CapabilityTree:
    global _tree
    if _tree is None:
        _tree = CapabilityTree.from_registry(_FLAT_REGISTRY)
    return _tree


# ── Public API (v1 compatibility) ──────────────────────────────

def get_capability(name: str) -> Capability | None:
    return _FLAT_REGISTRY.get(name)


def get_all_capabilities() -> dict[str, Capability]:
    return _FLAT_REGISTRY.copy()


def get_capabilities_by_category(category: CapabilityCategory) -> list[Capability]:
    return [c for c in _FLAT_REGISTRY.values() if c.category == category]


def get_capabilities_by_risk(risk: CapabilityRisk) -> list[Capability]:
    return [c for c in _FLAT_REGISTRY.values() if c.risk == risk]


def get_destructive_capabilities() -> list[Capability]:
    return [c for c in _FLAT_REGISTRY.values() if c.is_destructive]


# ── New tree API ───────────────────────────────────────────────

def resolve_capability(path: str) -> Capability | None:
    """Resolve a capability by dot path (e.g., 'AI.LLM.query')."""
    return _get_tree().resolve(path)


def search_capabilities(tags: list[str] | None = None,
                        risk: CapabilityRisk | None = None,
                        max_risk: CapabilityRisk | None = None,
                        permissions: list[str] | None = None,
                        max_cost: float | None = None,
                        latency: str | None = None) -> list[Capability]:
    """Search capabilities by tags, risk, permissions, cost, latency."""
    return _get_tree().search(tags=tags, risk=risk, max_risk=max_risk,
                              permissions=permissions, max_cost=max_cost, latency=latency)


def get_capability_tree() -> CapabilityTree:
    return _get_tree()


def merge_capabilities(caps: list[Capability]) -> bool:
    """Register new capabilities via atomic merge (for plugins)."""
    branch = CapabilityTree.build_branch(caps)
    return _get_tree().merge(branch)
