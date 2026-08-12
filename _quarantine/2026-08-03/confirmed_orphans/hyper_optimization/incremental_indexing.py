"""Incremental Indexing — Only index changed files via git diff.

Instead of re-indexing the entire project:
  Git Diff → Changed Files → Update Index
"""
import hashlib
import logging
import sqlite3
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("optimization_system.incremental_indexing")


@dataclass
class FileIndex:
    """Indexed state of a single file."""
    file_path: str
    content_hash: str
    indexed_at: float
    size_bytes: int = 0
    line_count: int = 0
    last_modified: float = 0.0


class IncrementalIndexer:
    """Index only changed files using git diff or file hash comparison.

    Features:
    - Git-aware: uses `git diff` to find changed files
    - Fallback: hash-based change detection
    - SQLite-backed index persistence
    - Supports incremental re-indexing
    """

    def __init__(self, project_path: str = ".", db_path: str = "cache/file_index.db"):
        self._project_path = str(Path(project_path).resolve())
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._indexed_files: dict[str, FileIndex] = {}
        self._init_db()
        self._load_index()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_index (
                    file_path TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    indexed_at REAL NOT NULL,
                    size_bytes INTEGER DEFAULT 0,
                    line_count INTEGER DEFAULT 0,
                    last_modified REAL DEFAULT 0
                )
            """)
            conn.commit()
            conn.close()

    def _load_index(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute("SELECT file_path, content_hash, indexed_at, size_bytes, line_count, last_modified FROM file_index").fetchall()
            conn.close()
            for row in rows:
                self._indexed_files[row[0]] = FileIndex(
                    file_path=row[0], content_hash=row[1],
                    indexed_at=row[2], size_bytes=row[3],
                    line_count=row[4], last_modified=row[5],
                )

    def get_changed_files(self) -> list[str]:
        """Get list of files changed since last index, using git or hash comparison."""
        # Try git first
        git_files = self._get_git_changed_files()
        if git_files is not None:
            return git_files

        # Fallback to hash-based detection
        return self._get_hash_changed_files()

    def _get_git_changed_files(self) -> list[str] | None:
        """Use git diff to find changed files."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=self._project_path,
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                files = [f for f in result.stdout.strip().split("\n") if f]
                # Also include untracked files
                result2 = subprocess.run(
                    ["git", "ls-files", "--others", "--exclude-standard"],
                    cwd=self._project_path,
                    capture_output=True, text=True, timeout=5
                )
                if result2.returncode == 0:
                    files.extend(f for f in result2.stdout.strip().split("\n") if f)
                return files
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def _get_hash_changed_files(self) -> list[str]:
        """Compare file hashes to find changed files."""
        changed = []
        project_dir = Path(self._project_path)
        for item in project_dir.rglob("*"):
            if not item.is_file():
                continue
            parts = item.relative_to(project_dir).parts
            if any(p.startswith(".") for p in parts):
                continue
            if any(p in ("node_modules", "__pycache__", "venv", ".git") for p in parts):
                continue

            rel = str(item.relative_to(project_dir))
            try:
                content = item.read_bytes()
                content_hash = hashlib.md5(content).hexdigest()
            except (OSError, PermissionError):
                continue

            existing = self._indexed_files.get(rel)
            if existing is None or existing.content_hash != content_hash:
                changed.append(rel)

        return changed

    def index_file(self, file_path: str) -> FileIndex | None:
        """Index a single file."""
        full_path = Path(self._project_path) / file_path
        try:
            content = full_path.read_bytes()
            content_hash = hashlib.md5(content).hexdigest()
            stat = full_path.stat()

            file_index = FileIndex(
                file_path=file_path,
                content_hash=content_hash,
                indexed_at=time.time(),
                size_bytes=stat.st_size,
                line_count=content.count(b"\n") + 1,
                last_modified=stat.st_mtime,
            )

            with self._lock:
                self._indexed_files[file_path] = file_index
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    "INSERT OR REPLACE INTO file_index (file_path, content_hash, indexed_at, size_bytes, line_count, last_modified) VALUES (?, ?, ?, ?, ?, ?)",
                    (file_path, content_hash, file_index.indexed_at, file_index.size_bytes, file_index.line_count, file_index.last_modified)
                )
                conn.commit()
                conn.close()

            return file_index
        except (OSError, PermissionError) as e:
            logger.debug("Cannot index %s: %s", file_path, e)
            return None

    def index_changed_files(self) -> dict[str, Any]:
        """Index only changed files. Returns indexing report."""
        start = time.time()
        changed = self.get_changed_files()
        indexed = 0
        errors = 0

        for file_path in changed:
            result = self.index_file(file_path)
            if result:
                indexed += 1
            else:
                errors += 1

        elapsed_ms = (time.time() - start) * 1000

        report = {
            "changed_detected": len(changed),
            "indexed": indexed,
            "errors": errors,
            "elapsed_ms": round(elapsed_ms, 1),
            "total_indexed": len(self._indexed_files),
        }

        if indexed > 0:
            logger.info("Incremental index: %d files updated in %.0fms", indexed, elapsed_ms)

        return report

    def get_index_size(self) -> int:
        with self._lock:
            return len(self._indexed_files)

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            total_size = sum(f.size_bytes for f in self._indexed_files.values())
            return {
                "indexed_files": len(self._indexed_files),
                "total_size_bytes": total_size,
                "project_path": self._project_path,
                "db_path": self._db_path,
            }


_indexer_instance: IncrementalIndexer | None = None


def get_incremental_indexer(project_path: str = ".") -> IncrementalIndexer:
    global _indexer_instance
    if _indexer_instance is None:
        _indexer_instance = IncrementalIndexer(project_path=project_path)
    return _indexer_instance
