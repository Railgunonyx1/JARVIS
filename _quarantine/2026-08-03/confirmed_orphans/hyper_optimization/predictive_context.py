"""Predictive Context Loading — Load project context before user asks.

User opens VS Code → Project loads automatically.
User starts coding → Relevant files pre-loaded.
"""
import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("optimization_system.predictive_context")


@dataclass
class ProjectContext:
    """Pre-loaded context for a project."""
    project_path: str
    loaded_at: float = 0.0
    files_loaded: int = 0
    size_bytes: int = 0
    file_types: dict[str, int] = field(default_factory=dict)
    key_files: list[str] = field(default_factory=list)
    is_ready: bool = False


class PredictiveContextLoader:
    """Predict and pre-load project context based on user behavior.

    Monitors:
    - Recently opened files/directories
    - Frequently accessed files
    - Time-of-day patterns
    - Active project detection
    """

    KEY_FILE_PATTERNS = [
        "README.md", "package.json", "requirements.txt", "Cargo.toml",
        "pyproject.toml", "setup.py", "Makefile", "Dockerfile",
        "src/main.py", "src/index.ts", "src/App.tsx",
        "app.py", "main.py", "index.py", "server.py",
    ]

    def __init__(self, base_path: str = None):
        self._base_path = base_path or os.getcwd()
        self._loaded_projects: dict[str, ProjectContext] = {}
        self._recent_dirs: list[str] = []
        self._access_patterns: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()
        self._preload_count = 0

    def detect_active_project(self) -> str | None:
        """Detect the most likely active project directory."""
        with self._lock:
            if self._recent_dirs:
                return self._recent_dirs[-1]
        return self._base_path

    def preload_project(self, project_path: str) -> ProjectContext:
        """Pre-load project context: scan files, count types, find key files."""
        project_path = str(Path(project_path).resolve())

        with self._lock:
            if project_path in self._loaded_projects:
                return self._loaded_projects[project_path]

        context = ProjectContext(project_path=project_path, loaded_at=time.time())

        try:
            project_dir = Path(project_path)
            if not project_dir.exists():
                return context

            files_loaded = 0
            total_size = 0
            file_types: dict[str, int] = defaultdict(int)
            key_files = []

            for item in project_dir.rglob("*"):
                if item.is_file():
                    # Skip hidden dirs and common large dirs
                    parts = item.relative_to(project_dir).parts
                    if any(p.startswith(".") for p in parts):
                        continue
                    if any(p in ("node_modules", "__pycache__", "venv", ".git", "dist", "build") for p in parts):
                        continue

                    files_loaded += 1
                    try:
                        total_size += item.stat().st_size
                    except OSError:
                        pass

                    ext = item.suffix.lower()
                    file_types[ext] = file_types.get(ext, 0) + 1

                    rel = str(item.relative_to(project_dir))
                    if rel in self.KEY_FILE_PATTERNS:
                        key_files.append(rel)

                    if files_loaded > 5000:
                        break

            context.files_loaded = files_loaded
            context.size_bytes = total_size
            context.file_types = dict(file_types)
            context.key_files = key_files
            context.is_ready = True

            with self._lock:
                self._loaded_projects[project_path] = context
                self._recent_dirs.append(project_path)
                if len(self._recent_dirs) > 10:
                    self._recent_dirs = self._recent_dirs[-10:]

            self._preload_count += 1
            logger.info("Pre-loaded project: %s (%d files, %dKB)",
                        project_path, files_loaded, total_size // 1024)

        except Exception as e:
            logger.debug("Preload failed for %s: %s", project_path, e)

        return context

    def record_file_access(self, file_path: str) -> None:
        """Record that a file was accessed (for pattern learning)."""
        with self._lock:
            self._access_patterns[file_path] += 1
            parent = str(Path(file_path).parent)
            if parent not in self._recent_dirs:
                self._recent_dirs.append(parent)

    def get_predictions(self) -> list[str]:
        """Predict which files/projects will be needed next."""
        with self._lock:
            # Return most frequently accessed files
            sorted_files = sorted(
                self._access_patterns.items(),
                key=lambda x: x[1], reverse=True
            )
            return [f for f, _ in sorted_files[:20]]

    def get_project_context(self, project_path: str) -> ProjectContext | None:
        return self._loaded_projects.get(str(Path(project_path).resolve()))

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            total_files = sum(c.files_loaded for c in self._loaded_projects.values())
            return {
                "loaded_projects": len(self._loaded_projects),
                "total_files_loaded": total_files,
                "preload_count": self._preload_count,
                "recent_dirs": len(self._recent_dirs),
                "tracked_files": len(self._access_patterns),
            }


_predictive_instance: PredictiveContextLoader | None = None


def get_predictive_context_loader() -> PredictiveContextLoader:
    global _predictive_instance
    if _predictive_instance is None:
        _predictive_instance = PredictiveContextLoader()
    return _predictive_instance
