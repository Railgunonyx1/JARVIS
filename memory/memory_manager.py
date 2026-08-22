"""Long-term memory manager — JSON-backed persistent memory with category support."""

import json
import logging
from datetime import datetime
from threading import Lock

from core.utils import get_project_root

logger = logging.getLogger("jarvis.memory.memory_manager")

MEMORY_PATH = get_project_root() / "memory" / "long_term.json"
_lock = Lock()
MAX_VALUE_LENGTH = 380
MEMORY_MAX_CHARS = 2200

_store = None
_cache: dict | None = None
_cache_version: int = 0  # bumped on every save to detect stale reads


def _get_store():
    global _store
    if _store is None:
        from memory.store import MemoryStore
        _store = MemoryStore()
    return _store


_EMPTY = {"identity": {}, "preferences": {}, "priorities": {}, "projects": {}, "relationships": {}, "wishes": {}, "notes": {}}  # noqa: E501


def load_memory() -> dict:
    """Load memory from disk, with cache protection.

    Cache is validated under the lock to prevent stale reads when
    another thread has called save_memory() concurrently.
    """
    global _cache, _cache_version
    with _lock:
        if _cache is not None:
            return _cache
        if not MEMORY_PATH.exists():
            _cache = dict(_EMPTY)
            return _cache
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k in _EMPTY:
                    data.setdefault(k, {})
                _cache = data
                return data
        except Exception as e:
            logger.error("Load error: %s", e)
    _cache = dict(_EMPTY)
    return _cache


def save_memory(memory: dict) -> None:
    """Atomically persist memory to disk.

    Writes to a temp file, fsyncs, then os.replace() for crash safety.
    Keeps a .bak backup for recovery from corruption.
    """
    import os
    import tempfile

    if not isinstance(memory, dict):
        return
    # Trim oldest entries if over limit
    blob = json.dumps(memory, ensure_ascii=False)
    if len(blob) > MEMORY_MAX_CHARS:
        entries = []
        for cat, items in memory.items():
            if isinstance(items, dict):
                for k, v in items.items():
                    if isinstance(v, dict) and "value" in v:
                        entries.append((cat, k, v))
        entries.sort(key=lambda t: t[2].get("updated", "0000"))
        for cat, key, _ in entries:
            if len(blob) <= MEMORY_MAX_CHARS:
                break
            del memory[cat][key]
            blob = json.dumps(memory, ensure_ascii=False)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        # Atomic write: temp file -> fsync -> replace -> backup
        fd, tmp_path = tempfile.mkstemp(
            dir=str(MEMORY_PATH.parent), suffix=".tmp", prefix=".mem_",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                tmp.write(json.dumps(memory, indent=2, ensure_ascii=False))
                tmp.flush()
                os.fsync(tmp.fileno())
            # Keep backup of previous version
            if MEMORY_PATH.exists():
                try:
                    bak = MEMORY_PATH.with_suffix(".json.bak")
                    if bak.exists():
                        bak.unlink()
                    MEMORY_PATH.rename(bak)
                except OSError:
                    pass  # backup is best-effort
            os.replace(tmp_path, str(MEMORY_PATH))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    global _cache
    _cache = None


def _truncate(val: str) -> str:
    return val[:MAX_VALUE_LENGTH].rstrip() + "..." if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH else val


def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            new_val = _truncate(str(value["value"] if isinstance(value, dict) else value))
            entry = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            if target.get(key, {}) != entry:
                target[key] = entry
                changed = True
    return changed


def update_memory(memory_update: dict) -> dict:
    """Update memory and sync to SQLite."""
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        try:
            store = _get_store()
            for cat, items in memory_update.items():
                if isinstance(items, dict):
                    for key, entry in items.items():
                        val = entry.get("value") if isinstance(entry, dict) else entry
                        if val:
                            store.store(str(key), str(val), category=cat)
        except Exception as e:
            logger.error("SQLite sync failed — memory saved to JSON but search index may be stale: %s", e)
    return memory


def format_memory_for_prompt(memory: dict | None) -> str:
    if not memory:
        return ""
    sections = [
        ("identity", "Identity"),
        ("preferences", "Preferences"),
        ("priorities", "Priorities"),
        ("projects", "Active Projects"),
        ("relationships", "People"),
        ("wishes", "Wishes / Plans"),
        ("notes", "Notes"),
    ]
    lines = []
    for cat, label in sections:
        items = memory.get(cat, {})
        if not items:
            continue
        lines.append(f"\n{label}:" if lines else f"{label}:")
        for key, entry in list(items.items())[:12]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")
    if not lines:
        return ""
    result = "[WHAT YOU KNOW ABOUT THIS PERSON]\n" + "\n".join(lines)
    return (result[:1997] + "...") if len(result) > 2000 else result + "\n"


def remember(key: str, value: str, category: str = "notes") -> str:
    if category not in {"identity", "preferences", "projects", "relationships", "wishes", "notes"}:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    memory = load_memory()
    cat = memory.get(category, {})
    if key in cat:
        del cat[key]
        save_memory(memory)
        # Sync deletion to SQLite so search() doesn't return forgotten items
        try:
            store = _get_store()
            store.delete(str(key))
        except Exception as e:
            logger.warning("SQLite sync failed on forget: %s", e)
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"


forget_memory = forget
