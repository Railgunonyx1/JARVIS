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


def _get_store():
    global _store
    if _store is None:
        from memory.store import MemoryStore
        _store = MemoryStore()
    return _store


_EMPTY = {"identity": {}, "preferences": {}, "priorities": {}, "projects": {}, "relationships": {}, "wishes": {}, "notes": {}}  # noqa: E501


def load_memory() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    if not MEMORY_PATH.exists():
        _cache = dict(_EMPTY)
        return _cache
    with _lock:
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
        MEMORY_PATH.write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding="utf-8")
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
            logger.warning("SQLite sync failed: %s", e)
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
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"


forget_memory = forget
