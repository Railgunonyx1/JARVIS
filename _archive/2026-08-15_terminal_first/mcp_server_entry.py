"""
MCP Server entry point for JARVIS MK-X.
Run with: python -m mcp.server
Or: python -m jarvis_mcp
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add JARVIS root to path (this file lives in scripts/)
JARVIS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(JARVIS_ROOT))

from mcp.server import main

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    asyncio.run(main())
