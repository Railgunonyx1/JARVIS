"""Streaming Tool Execution — User sees real-time progress.

Instead of: Tool completes → LLM responds
Use:        Tool starts → LLM narrates → Tool streams output → User sees updates
"""
import asyncio
import logging
import threading
import time
from collections import deque
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger("reasoning_system.streaming_tool")


class ToolState(Enum):
    PENDING = auto()
    STARTING = auto()
    RUNNING = auto()
    STREAMING = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class ToolChunk:
    """A chunk of streaming output from a tool."""
    chunk_type: str  # "text", "progress", "result", "error", "status"
    content: str
    timestamp: float = 0.0
    sequence: int = 0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class StreamingTool:
    """A tool that streams output in real time."""
    name: str
    state: ToolState = ToolState.PENDING
    input_data: dict[str, Any] = field(default_factory=dict)
    chunks: list = field(default_factory=list)
    result: Any = None
    error: str | None = None
    started_at: float = 0.0
    completed_at: float = 0.0
    total_chunks: int = 0

    @property
    def latency_ms(self) -> float:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return 0.0


class StreamingToolExecutor:
    """Execute tools with real-time streaming output.

    Instead of waiting for the tool to finish:
    1. Tool starts → emits "starting" chunk
    2. Tool runs → emits progress chunks
    3. Tool finishes → emits "result" chunk

    User sees updates immediately instead of waiting.
    """

    def __init__(self):
        self._active_tools: dict[str, StreamingTool] = {}
        self._completed_tools: deque = deque(maxlen=100)
        self._lock = threading.Lock()
        self._sequence_counter = 0
        self._callbacks: dict[str, Callable] = {}

    def register_callback(self, tool_name: str, callback: Callable) -> None:
        """Register a callback for streaming chunks from a tool."""
        self._callbacks[tool_name] = callback

    async def execute_streaming(self, tool_name: str, tool_fn: Callable,
                                 input_data: dict[str, Any] = None,
                                 **kwargs) -> AsyncGenerator[ToolChunk, None]:
        """Execute a tool and yield streaming chunks."""
        tool = StreamingTool(
            name=tool_name,
            input_data=input_data or {},
            state=ToolState.STARTING,
            started_at=time.time(),
        )

        with self._lock:
            self._active_tools[tool_name] = tool

        # Emit starting chunk
        self._sequence_counter += 1
        chunk = ToolChunk(
            chunk_type="status",
            content=f"Starting {tool_name}...",
            sequence=self._sequence_counter,
        )
        tool.chunks.append(chunk)
        yield chunk

        try:
            tool.state = ToolState.RUNNING

            # Check if tool supports streaming
            if asyncio.iscoroutinefunction(tool_fn):
                if hasattr(tool_fn, '__aiter__'):
                    async for output in tool_fn(input_data or {}, **kwargs):
                        self._sequence_counter += 1
                        chunk = ToolChunk(
                            chunk_type="text",
                            content=str(output),
                            sequence=self._sequence_counter,
                        )
                        tool.chunks.append(chunk)
                        tool.total_chunks += 1
                        yield chunk
                else:
                    result = await tool_fn(input_data or {}, **kwargs)
                    self._sequence_counter += 1
                    chunk = ToolChunk(
                        chunk_type="result",
                        content=str(result),
                        sequence=self._sequence_counter,
                    )
                    tool.chunks.append(chunk)
                    tool.result = result
                    yield chunk
            else:
                # Sync function — run in thread
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: tool_fn(input_data or {}, **kwargs))
                self._sequence_counter += 1
                chunk = ToolChunk(
                    chunk_type="result",
                    content=str(result),
                    sequence=self._sequence_counter,
                )
                tool.chunks.append(chunk)
                tool.result = result
                yield chunk

            tool.state = ToolState.COMPLETED
            tool.completed_at = time.time()

            # Emit completion chunk
            self._sequence_counter += 1
            completion = ToolChunk(
                chunk_type="status",
                content=f"{tool_name} completed in {tool.latency_ms:.0f}ms",
                sequence=self._sequence_counter,
            )
            yield completion

        except Exception as e:
            tool.state = ToolState.FAILED
            tool.error = str(e)
            tool.completed_at = time.time()

            self._sequence_counter += 1
            error_chunk = ToolChunk(
                chunk_type="error",
                content=f"{tool_name} failed: {e}",
                sequence=self._sequence_counter,
            )
            yield error_chunk

        finally:
            with self._lock:
                self._active_tools.pop(tool_name, None)
                self._completed_tools.append(tool)

    def execute_sync(self, tool_name: str, tool_fn: Callable,
                     input_data: dict[str, Any] = None) -> dict[str, Any]:
        """Execute a tool synchronously with status tracking."""
        tool = StreamingTool(
            name=tool_name,
            input_data=input_data or {},
            state=ToolState.RUNNING,
            started_at=time.time(),
        )

        with self._lock:
            self._active_tools[tool_name] = tool

        try:
            result = tool_fn(input_data or {})
            tool.result = result
            tool.state = ToolState.COMPLETED
        except Exception as e:
            tool.error = str(e)
            tool.state = ToolState.FAILED
        finally:
            tool.completed_at = time.time()
            with self._lock:
                self._active_tools.pop(tool_name, None)
                self._completed_tools.append(tool)

        return {
            "tool": tool_name,
            "state": tool.state.name,
            "result": tool.result,
            "error": tool.error,
            "latency_ms": tool.latency_ms,
        }

    def get_active_tools(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                name: {
                    "state": tool.state.name,
                    "chunks": tool.total_chunks,
                    "started_at": tool.started_at,
                }
                for name, tool in self._active_tools.items()
            }

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            completed = list(self._completed_tools)
            total = len(completed)
            successful = sum(1 for t in completed if t.state == ToolState.COMPLETED)
            avg_latency = sum(t.latency_ms for t in completed) / max(total, 1)
            return {
                "active_tools": len(self._active_tools),
                "completed_tools": total,
                "successful": successful,
                "failed": total - successful,
                "avg_latency_ms": round(avg_latency, 1),
                "total_chunks_emitted": self._sequence_counter,
            }


_streaming_executor_instance: StreamingToolExecutor | None = None


def get_streaming_tool_executor() -> StreamingToolExecutor:
    global _streaming_executor_instance
    if _streaming_executor_instance is None:
        _streaming_executor_instance = StreamingToolExecutor()
    return _streaming_executor_instance
