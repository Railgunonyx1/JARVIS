"""Zero-Copy Manager: Shared buffer system to avoid unnecessary data copying."""

import logging
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger("jarvis.hyper_opt.zero_copy_manager")


class SharedBuffer:
    """A shared memory buffer that multiple consumers can read without copying."""

    def __init__(self, name: str, size_bytes: int):
        self._name = name
        self._data = bytearray(size_bytes)
        self._size = size_bytes
        self._valid_size = 0
        self._ref_count = 0
        self._last_access = time.time()
        self._created_at = time.time()
        self._lock = threading.RLock()

    def write(self, data: bytes):
        with self._lock:
            data_len = len(data)
            if data_len > self._size:
                self._resize_internal(data_len)
            self._data[:data_len] = data
            self._valid_size = data_len
            self._last_access = time.time()

    def read(self, offset: int = 0, length: Optional[int] = None) -> memoryview:
        with self._lock:
            self._last_access = time.time()
            if length is None:
                length = self._valid_size - offset
            if offset < 0 or offset > self._valid_size:
                raise ValueError(f"Offset {offset} out of range (valid_size={self._valid_size})")
            end = offset + length
            if end > self._valid_size:
                raise ValueError(f"Read range {offset}:{end} exceeds valid_size={self._valid_size}")
            return memoryview(self._data)[offset:end]

    def _resize_internal(self, new_size: int):
        new_data = bytearray(new_size)
        copy_len = min(self._valid_size, new_size)
        new_data[:copy_len] = self._data[:copy_len]
        self._data = new_data
        self._size = new_size
        if self._valid_size > new_size:
            self._valid_size = new_size

    def resize(self, new_size: int):
        with self._lock:
            self._resize_internal(new_size)

    def increment_ref(self):
        with self._lock:
            self._ref_count += 1

    def decrement_ref(self) -> int:
        with self._lock:
            self._ref_count = max(0, self._ref_count - 1)
            return self._ref_count

    @property
    def size(self) -> int:
        return self._size

    @property
    def valid_size(self) -> int:
        return self._valid_size

    @property
    def name(self) -> str:
        return self._name

    @property
    def last_access(self) -> float:
        return self._last_access

    @property
    def ref_count(self) -> int:
        return self._ref_count


class ZeroCopyManager:
    """Manages shared memory buffers for zero-copy data sharing between components."""

    def __init__(self):
        self._buffers: Dict[str, SharedBuffer] = {}
        self._lock = threading.RLock()
        self._stats = {
            "creates": 0,
            "reads": 0,
            "writes": 0,
            "bytes_saved": 0,
        }

    def create_buffer(self, name: str, size_bytes: int) -> SharedBuffer:
        with self._lock:
            if name in self._buffers:
                existing = self._buffers[name]
                if existing.size < size_bytes:
                    existing.resize(size_bytes)
                return existing
            buf = SharedBuffer(name, size_bytes)
            self._buffers[name] = buf
            self._stats["creates"] += 1
            logger.debug("Created buffer '%s' (%d bytes)", name, size_bytes)
            return buf

    def get_buffer(self, name: str) -> Optional[SharedBuffer]:
        with self._lock:
            buf = self._buffers.get(name)
            if buf is not None:
                buf.increment_ref()
            return buf

    def release_buffer(self, name: str):
        with self._lock:
            buf = self._buffers.get(name)
            if buf is not None:
                remaining = buf.decrement_ref()

    def read_from_buffer(self, name: str, offset: int = 0, length: Optional[int] = None) -> Optional[memoryview]:
        with self._lock:
            buf = self._buffers.get(name)
        if buf is None:
            return None
        self._stats["reads"] += 1
        return buf.read(offset, length)

    def write_to_buffer(self, name: str, data: bytes) -> bool:
        with self._lock:
            buf = self._buffers.get(name)
        if buf is None:
            return False
        self._stats["writes"] += 1
        self._stats["bytes_saved"] += len(data)
        buf.write(data)
        return True

    def remove_buffer(self, name: str) -> bool:
        with self._lock:
            if name in self._buffers:
                del self._buffers[name]
                logger.debug("Removed buffer '%s'", name)
                return True
            return False

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "creates": self._stats["creates"],
                "reads": self._stats["reads"],
                "writes": self._stats["writes"],
                "bytes_saved": self._stats["bytes_saved"],
                "total_buffers": len(self._buffers),
            }

    def cleanup(self, max_age_seconds: float = 300):
        with self._lock:
            now = time.time()
            stale = [
                name for name, buf in self._buffers.items()
                if (now - buf.last_access) > max_age_seconds and buf.ref_count == 0
            ]
            for name in stale:
                del self._buffers[name]
            if stale:
                logger.info("Cleaned up %d stale buffers", len(stale))

    def list_buffers(self) -> list:
        with self._lock:
            return [
                {"name": b.name, "size": b.size, "valid_size": b.valid_size, "ref_count": b.ref_count}
                for b in self._buffers.values()
            ]


_instance: Optional[ZeroCopyManager] = None
_instance_lock = threading.RLock()


def get_zero_copy_manager() -> ZeroCopyManager:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = ZeroCopyManager()
            logger.info("Created ZeroCopyManager singleton")
        return _instance
