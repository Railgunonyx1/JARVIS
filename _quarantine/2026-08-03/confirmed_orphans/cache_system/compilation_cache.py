"""Cross-Session Compilation Cache — Cache Python AST, project graphs, imports, dependency trees.

Avoid rebuilding them every launch.
"""
import logging
import time
import json
import hashlib
import sqlite3
import ast
import threading
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger("cache_system.compilation_cache")


class CompilationCache:
    """Cache expensive parsing/analysis results across sessions.

    Stores:
    - Python AST trees (serialized as source hash → AST data)
    - Project file graphs
    - Import dependency trees
    - Tokenizer state
    """

    def __init__(self, db_path: str = "cache/compilation.db"):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._mem_cache: Dict[str, Any] = {}
        self._hits = 0
        self._misses = 0
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS compiled_cache (
                    cache_key TEXT NOT NULL,
                    category TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    ttl_seconds REAL DEFAULT 86400,
                    access_count INTEGER DEFAULT 0,
                    PRIMARY KEY (cache_key, category)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON compiled_cache(category)")
            conn.commit()
            conn.close()

    @staticmethod
    def _hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]

    def get(self, key: str, category: str = "default") -> Optional[Any]:
        cache_key = f"{category}:{key}"

        # Memory cache
        if cache_key in self._mem_cache:
            self._hits += 1
            return self._mem_cache[cache_key]

        # SQLite
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT data, created_at, ttl_seconds FROM compiled_cache WHERE cache_key = ? AND category = ?",
                (key, category)
            ).fetchone()
            if row:
                data_str, created_at, ttl = row
                if ttl > 0 and (time.time() - created_at) > ttl:
                    conn.execute("DELETE FROM compiled_cache WHERE cache_key = ? AND category = ?", (key, category))
                    conn.commit()
                    conn.close()
                    self._misses += 1
                    return None
                data = json.loads(data_str)
                conn.execute(
                    "UPDATE compiled_cache SET access_count = access_count + 1 WHERE cache_key = ? AND category = ?",
                    (key, category)
                )
                conn.commit()
                conn.close()
                self._mem_cache[cache_key] = data
                self._hits += 1
                return data
            conn.close()

        self._misses += 1
        return None

    def put(self, key: str, data: Any, category: str = "default", ttl_seconds: float = 86400) -> None:
        cache_key = f"{category}:{key}"
        self._mem_cache[cache_key] = data

        data_str = json.dumps(data, default=str)
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT OR REPLACE INTO compiled_cache (cache_key, category, data, created_at, ttl_seconds) VALUES (?, ?, ?, ?, ?)",
                (key, category, data_str, time.time(), ttl_seconds)
            )
            conn.commit()
            conn.close()

    def cache_ast(self, source_code: str, file_path: str = "") -> Dict[str, Any]:
        """Parse and cache AST analysis of Python source."""
        source_hash = self._hash(source_code)
        cached = self.get(source_hash, "ast")
        if cached is not None:
            return cached

        try:
            tree = ast.parse(source_code)
            analysis = {
                "functions": [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)],
                "classes": [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)],
                "imports": [],
                "line_count": len(source_code.split("\n")),
                "complexity_estimate": sum(1 for node in ast.walk(tree) if isinstance(node, (ast.If, ast.For, ast.While, ast.Try))),
                "file_path": file_path,
            }
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        analysis["imports"].append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        analysis["imports"].append(node.module)

            self.put(source_hash, analysis, "ast")
            return analysis
        except SyntaxError as e:
            return {"error": str(e)}

    def cache_file_graph(self, project_path: str, file_list: List[str]) -> Dict[str, Any]:
        """Cache project file dependency graph."""
        key = self._hash(project_path + str(sorted(file_list)))
        cached = self.get(key, "file_graph")
        if cached is not None:
            return cached

        graph = {
            "root": project_path,
            "files": file_list,
            "extensions": {},
            "total_size": 0,
        }
        for f in file_list:
            ext = Path(f).suffix
            graph["extensions"][ext] = graph["extensions"].get(ext, 0) + 1

        self.put(key, graph, "file_graph")
        return graph

    def cache_import_tree(self, module_name: str, imports: List[str]) -> None:
        """Cache import dependency tree for a module."""
        self.put(module_name, imports, "import_tree")

    def get_import_tree(self, module_name: str) -> Optional[List[str]]:
        return self.get(module_name, "import_tree")

    def get_size(self) -> Dict[str, int]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute(
                "SELECT category, COUNT(*) FROM compiled_cache GROUP BY category"
            ).fetchall()
            conn.close()
            return {row[0]: row[1] for row in rows}

    def get_stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "cached_items": sum(self.get_size().values()),
            "mem_cache_size": len(self._mem_cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(total, 1) * 100, 1),
            "categories": self.get_size(),
        }

    def clear(self, category: str = None) -> None:
        self._mem_cache.clear()
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            if category:
                conn.execute("DELETE FROM compiled_cache WHERE category = ?", (category,))
            else:
                conn.execute("DELETE FROM compiled_cache")
            conn.commit()
            conn.close()


_compilation_cache_instance: Optional[CompilationCache] = None


def get_compilation_cache() -> CompilationCache:
    global _compilation_cache_instance
    if _compilation_cache_instance is None:
        _compilation_cache_instance = CompilationCache()
    return _compilation_cache_instance
