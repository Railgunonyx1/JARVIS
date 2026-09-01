"""Backwards-compatible memory facade.

Stage 1 moved the memory system to a unified API (``memory.api``). This
module keeps the old import paths working:

    from memory.mem import Mem, get_mem

``Mem`` is now an alias for ``MemoryAPI`` and ``get_mem`` returns the same
process-wide singleton as before.
"""

from __future__ import annotations

from memory.api import Mem, MemoryAPI, get_mem

__all__ = ["Mem", "MemoryAPI", "get_mem"]
