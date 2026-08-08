"""Plugin Marketplace — registry, discovery, and installation for JARVIS plugins.

Works with existing PluginManager to discover, download, and install
plugins from local or remote sources.
"""

import json
import time
import logging
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("jarvis.core.plugin_market")

PLUGIN_DIR = Path.home() / ".jarvis" / "plugins"
MARKETPLACE_INDEX = PLUGIN_DIR / "marketplace.json"


@dataclass
class PluginMarketEntry:
    """Metadata for a discoverable plugin."""
    id: str
    name: str
    version: str
    author: str
    description: str
    source: str  # "local" | "url" | "github"
    url: str = ""
    permissions: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    installed: bool = False
    installed_version: str = ""
    updated_at: float = field(default_factory=time.time)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


class PluginMarketplace:
    """Discovers, indexes, and installs plugins."""

    def __init__(self, plugin_manager=None, plugin_dir: Optional[Path] = None):
        self._pm = plugin_manager
        self._plugin_dir = plugin_dir or PLUGIN_DIR
        self._plugin_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, PluginMarketEntry] = {}
        self._load_index()

    def _load_index(self):
        if MARKETPLACE_INDEX.exists():
            try:
                data = json.loads(MARKETPLACE_INDEX.read_text(encoding="utf-8"))
                for entry in data:
                    e = PluginMarketEntry.from_dict(entry)
                    self._index[e.id] = e
            except Exception as e:
                logger.warning("Marketplace index load failed: %s", e)

    def _save_index(self):
        MARKETPLACE_INDEX.parent.mkdir(parents=True, exist_ok=True)
        data = [e.to_dict() for e in self._index.values()]
        MARKETPLACE_INDEX.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── Registration ───────────────────────────

    def register(self, entry: PluginMarketEntry):
        """Register a plugin in the marketplace."""
        self._index[entry.id] = entry
        self._save_index()
        logger.info("Registered plugin: %s v%s", entry.name, entry.version)

    def unregister(self, plugin_id: str):
        self._index.pop(plugin_id, None)
        self._save_index()

    # ── Discovery ──────────────────────────────

    def discover_local(self):
        """Scan the plugin directory for .py or .zip plugin files."""
        count = 0
        for f in self._plugin_dir.iterdir():
            if f.suffix in (".py", ".zip") and not f.name.startswith("_"):
                plugin_id = f.stem
                if plugin_id not in self._index:
                    manifest_path = f.with_suffix(".json")
                    if manifest_path.exists():
                        try:
                            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                            self._index[plugin_id] = PluginMarketEntry(
                                id=plugin_id,
                                name=manifest.get("name", plugin_id),
                                version=manifest.get("version", "0.1.0"),
                                author=manifest.get("author", "unknown"),
                                description=manifest.get("description", ""),
                                source="local",
                                permissions=manifest.get("permissions", []),
                                capabilities=manifest.get("capabilities", []),
                                dependencies=manifest.get("dependencies", []),
                                installed=True,
                                installed_version=manifest.get("version", "0.1.0"),
                            )
                            count += 1
                        except Exception as e:
                            logger.debug("Skipping %s: %s", f.name, e)
        if count:
            self._save_index()
        return count

    def search(self, query: str = "") -> List[PluginMarketEntry]:
        """Search indexed plugins by name, author, or description."""
        query = query.lower().strip()
        results = []
        for entry in self._index.values():
            if not query:
                results.append(entry)
            elif (query in entry.name.lower()
                  or query in entry.author.lower()
                  or query in entry.description.lower()):
                results.append(entry)
        return results

    def list_installed(self) -> List[PluginMarketEntry]:
        return [e for e in self._index.values() if e.installed]

    def list_available(self) -> List[PluginMarketEntry]:
        return [e for e in self._index.values() if not e.installed]

    def get(self, plugin_id: str) -> Optional[PluginMarketEntry]:
        return self._index.get(plugin_id)

    # ── Installation ───────────────────────────

    def install(self, plugin_id: str) -> bool:
        """Install a plugin from the marketplace index."""
        entry = self._index.get(plugin_id)
        if not entry:
            logger.error("Plugin %s not found in marketplace", plugin_id)
            return False
        if entry.installed:
            logger.warning("Plugin %s already installed", plugin_id)
            return True

        if entry.source == "local":
            # For local plugins, just mark as installed if file exists
            plugin_file = self._plugin_dir / f"{plugin_id}.py"
            if plugin_file.exists():
                entry.installed = True
                entry.installed_version = entry.version
                self._save_index()
                logger.info("Installed plugin: %s", plugin_id)
                return True
            logger.error("Plugin file not found: %s", plugin_file)
            return False

        elif entry.source == "url" and entry.url:
            try:
                import urllib.request
                dest = self._plugin_dir / f"{plugin_id}.py"
                urllib.request.urlretrieve(entry.url, dest)
                entry.installed = True
                entry.installed_version = entry.version
                self._save_index()
                logger.info("Downloaded and installed: %s", plugin_id)
                return True
            except Exception as e:
                logger.error("Download failed for %s: %s", plugin_id, e)
                return False

        elif entry.source == "github":
            logger.warning("GitHub install not yet implemented for %s", plugin_id)
            return False

        return False

    def uninstall(self, plugin_id: str) -> bool:
        entry = self._index.get(plugin_id)
        if not entry or not entry.installed:
            return False
        plugin_file = self._plugin_dir / f"{plugin_id}.py"
        if plugin_file.exists():
            plugin_file.unlink()
        entry.installed = False
        entry.installed_version = ""
        self._save_index()
        logger.info("Uninstalled plugin: %s", plugin_id)
        return True

    def get_stats(self) -> dict:
        total = len(self._index)
        installed = sum(1 for e in self._index.values() if e.installed)
        return {"total": total, "installed": installed, "available": total - installed}
