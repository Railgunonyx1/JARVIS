"""ProjectContext — where the agent works: root, language, framework, VCS.

Tools resolve paths relative to this context instead of guessing. Detected
once per CLI run so path resolution is consistent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

_LANGUAGE_MARKERS = {
    "python": ["pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "Pipfile", "poetry.lock"],
    "typescript": ["tsconfig.json"],
    "javascript": ["package.json", "package-lock.json", "yarn.lock", ".nvmrc"],
    "go": ["go.mod", "go.sum"],
    "rust": ["Cargo.toml", "Cargo.lock"],
    "java": ["pom.xml", "build.gradle", "settings.gradle"],
    "ruby": ["Gemfile"],
    "php": ["composer.json"],
}

_CONFIG_MARKERS = [
    "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "Pipfile",
    "package.json", "tsconfig.json", "go.mod", "Cargo.toml", "pom.xml",
    "build.gradle", "Gemfile", "composer.json",
]


@dataclass
class ProjectContext:
    root_path: Path
    language: str = ""
    framework: str = ""
    git_root: Optional[Path] = None
    config_files: List[str] = field(default_factory=list)

    @classmethod
    def discover(cls, cwd: Optional[str] = None) -> "ProjectContext":
        cwd_path = Path(cwd or os.getcwd()).resolve()
        ctx = cls(root_path=cwd_path)
        ctx._detect_git(cwd_path)
        ctx._detect_language(cwd_path)
        return ctx

    def _detect_git(self, start: Path) -> None:
        for parent in [start, *start.parents]:
            if (parent / ".git").exists():
                self.git_root = parent
                return

    def _detect_language(self, root: Path) -> None:
        files = [f.name.lower() for f in root.iterdir() if f.is_file()]
        for lang, markers in _LANGUAGE_MARKERS.items():
            if any(marker.lower() in files for marker in markers):
                self.language = lang
                break
        if not self.language:
            if any(root.glob("*.csproj")) or any(root.glob("*.sln")):
                self.language = "csharp"
        self.config_files = [m for m in _CONFIG_MARKERS if m in files]
        self.framework = self._detect_framework(root, files)

    @staticmethod
    def _detect_framework(root: Path, files: List[str]) -> str:
        try:
            if "requirements.txt" in files:
                text = (root / "requirements.txt").read_text(encoding="utf-8", errors="ignore").lower()
                if "django" in text:
                    return "django"
                if "flask" in text:
                    return "flask"
            if "pyproject.toml" in files:
                text = (root / "pyproject.toml").read_text(encoding="utf-8", errors="ignore").lower()
                if "fastapi" in text:
                    return "fastapi"
                if "django" in text:
                    return "django"
                if "flask" in text:
                    return "flask"
            if "package.json" in files:
                text = (root / "package.json").read_text(encoding="utf-8", errors="ignore")
                if '"next"' in text:
                    return "next.js"
                if '"react"' in text:
                    return "react"
                if '"vue"' in text:
                    return "vue"
                if '"express"' in text:
                    return "express"
        except OSError:
            pass
        return ""

    def to_dict(self) -> dict:
        return {
            "root_path": str(self.root_path),
            "language": self.language,
            "framework": self.framework,
            "git_root": str(self.git_root) if self.git_root else None,
            "config_files": self.config_files,
        }
