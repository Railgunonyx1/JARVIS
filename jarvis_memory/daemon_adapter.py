"""JARVIS MK-X Daemon Adapter

Provides the Python daemon interface for the JARVIS MK-X system.
Handles WebSocket communication, agent execution, tool management,
and memory operations with sqlite-vec vector search fallback and OpenTelemetry tracing.
"""

import asyncio
import json
import logging
import os
import sys
import sqlite3
import numpy
from concurrent import futures
from typing import Any, Dict, List, Optional, Callable

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("jarvis_daemon")

# --- OpenTelemetry Tracing (lazy initialization) ---

_tracer = None

def get_tracer():
    """Get or initialize the OpenTelemetry tracer."""
    global _tracer
    if _tracer is None:
        from opentelemetry import trace as otel_trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        otel_trace.set_tracer_provider(TracerProvider())
        _tracer = otel_trace.get_tracer("jarvis_daemon")
        try:
            otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
            span_processor = BatchSpanProcessor(otlp_exporter)
            _tracer.get_tracer_provider().add_span_processor(span_processor)
        except Exception:
            logger.warning("OpenTelemetry OTLP exporter not available — running without export")
    return _tracer

# --- Vector Search (sqlite-vec fallback) ---

class VectorSearch:
    """Vector search using SQLite as local storage.
    
    Falls back to Python-based cosine similarity when the
    sqlite-vec extension is unavailable. Stores embeddings
    as JSON for later retrieval.
    
    Note: For production use with large-scale search,
    consider migrating to dedicated vector databases
    (sqlite-vec, Qdrant, Pinecone) when resource constraints
    allow. Current design fits JARVIS's 512 MB RAM constraint.
    """
    
    def __init__(self, db_path: str = "jarvis_memory/vector_store.db"):
        self.db_path = db_path
        self._init_db()
        
    def _init_db(self):
        """Initialize SQLite database with embeddings table."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS embeddings ("
            "id TEXT PRIMARY KEY, "
            "embedding JSON, "
            "metadata TEXT)"
        )
        conn.close()
        
    def add_embedding(self, id: str, embedding: List[float], metadata: Dict = None):
        """Add a vector embedding to the search index."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO embeddings (id, embedding, metadata) "
            "VALUES (?, ?, ?)",
            (id, json.dumps(embedding), str(metadata) if metadata else None)
        )
        conn.close()
        
    def semantic_search(self, query_embedding: List[float], k: int = 10) -> List[Dict]:
        """Perform semantic search against stored embeddings.
        
        Returns list of {id, distance} dicts computed via cosine similarity.
        Sorted by distance (lower = more similar), limited to k results.
        """
        query_arr = numpy.array(query_embedding, dtype=numpy.float64)
        query_norm = numpy.linalg.norm(query_arr)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT id, embedding FROM embeddings")
        results = []
        for row in cursor:
            try:
                stored_arr = numpy.array(json.loads(row[1]), dtype=numpy.float64)
                if stored_arr.size > 0 and query_norm > 0:
                    dot = numpy.dot(query_arr, stored_arr)
                    stored_norm = numpy.linalg.norm(stored_arr)
                    cosine = dot / (query_norm * stored_norm) if stored_norm > 0 else 0
                    distance = 1 - cosine  # distance = 1 - similarity
                    results.append({"id": row[0], "distance": float(distance)})
            except (json.JSONDecodeError, ValueError):
                continue
        conn.close()
        
        # Sort by distance (lower = more similar) and limit to k
        results.sort(key=lambda x: x["distance"])
        return results[:k]

# --- Memory Manager (MemoryFabric with VectorSearch fallback) ---

class MemoryManager:
    """High-level memory facade for the daemon.

    Uses the JARVIS Memory Fabric (sqlite + FTS5 + optional vector search)
    when importable; otherwise degrades to the in-file VectorSearch so the
    daemon never fails to start. Mirrors the Mem0 pattern: typed memories
    (fact / episode / procedure), hybrid search, consolidation, stats.
    """

    def __init__(self, db_path: str = "jarvis_memory/vector_store.db"):
        self.db_path = db_path
        self._fabric = None
        self._vector = VectorSearch(db_path)
        try:
            from memory.jarvis_memory_fabric import create_memory_fabric
            self._fabric = create_memory_fabric(db_path.replace("vector_store.db", "memory.db"))
            logger.info("Memory fabric initialized at %s", db_path.replace("vector_store.db", "memory.db"))
        except Exception as exc:
            logger.warning("Memory fabric unavailable (%s) — using vector fallback", exc)

    @property
    def available(self) -> bool:
        return self._fabric is not None

    def remember(
        self,
        *,
        type: str = "fact",
        content: str,
        subject: str = None,
        predicate: str = None,
        obj: str = None,
        importance: float = 0.5,
        session_id: str = None,
        task_id: str = None,
        source: str = None,
        **kwargs,
    ) -> Optional[str]:
        if self._fabric is not None:
            return self._fabric.remember(
                type=type,
                content=content,
                subject=subject,
                predicate=predicate,
                obj=obj,
                importance=importance,
                session_id=session_id,
                task_id=task_id,
                source=source,
                **kwargs,
            )
        # Fallback: store content as a pseudo-embedding of character codes
        embedding = [ord(c) % 100 / 100.0 for c in content[:64]] + [0.0] * (768 - 64)
        mid = f"mem_{abs(hash(content)):x}"
        self._vector.add_embedding(mid, embedding, {"content": content, "subject": subject})
        return mid

    def search(self, query: str = None, *, limit: int = 15, **filters) -> List[Dict]:
        if self._fabric is not None:
            return self._fabric.search(query=query, limit=limit, **filters)
        if query:
            embedding = [ord(c) % 100 / 100.0 for c in query[:64]] + [0.0] * (768 - 64)
            hits = self._vector.semantic_search(embedding, k=limit)
            out = []
            for h in hits:
                conn = sqlite3.connect(self.db_path)
                row = conn.execute(
                    "SELECT metadata FROM embeddings WHERE id = ?", (h["id"],)
                ).fetchone()
                conn.close()
                if row:
                    try:
                        meta = json.loads(row[0].replace("'", '"')) if row[0] else {}
                    except (ValueError, AttributeError):
                        meta = {"content": row[0]}
                    out.append({"id": h["id"], "distance": h["distance"], **meta})
            return out
        return []

    def recall(self, memory_item_id: str) -> Optional[Dict]:
        if self._fabric is not None:
            return self._fabric.recall(memory_item_id)
        return None

    def forget(self, memory_item_id: str) -> bool:
        if self._fabric is not None:
            return self._fabric.forget(memory_item_id)
        return False

    def stats(self) -> Dict:
        if self._fabric is not None:
            return self._fabric.stats()
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        conn.close()
        return {"total_memories": count, "backend": "vector_fallback"}

    def consolidate(self) -> Dict:
        if self._fabric is not None:
            return self._fabric.consolidate()
        return {"status": "noop", "reason": "vector fallback has nothing to consolidate"}

# --- Core Types ---

AgentState = str
STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_COMPLETED = "completed"
STATE_CANCELLED = "cancelled"
STATE_FAILED = "failed"

TaskStatus = str
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"
STATUS_FAILED = "failed"

# --- Daemon Configuration ---

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_HEARTBEAT_INTERVAL = 30.0
DEFAULT_HEARTBEAT_TIMEOUT = 60.0

# --- WebSocket Server ---

class WebSocketManager:
    """Manages WebSocket connections and message broadcasting."""
    
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.clients: set = set()
        self.messages: asyncio.Queue = asyncio.Queue()
        self.server = None
        
    async def start(self):
        """Start the WebSocket server."""
        import websockets
        self.server = await websockets.serve(
            self._handle_client, self.host, self.port
        )
        logger.info(f"WebSocket server started on {self.host}:{self.port}")
        
    async def stop(self):
        """Stop the WebSocket server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        logger.info("WebSocket server stopped")
        
    async def _handle_client(self, websocket, path=None):
        """Handle a new WebSocket client connection."""
        self.clients.add(websocket)
        logger.info(f"Client connected. Total clients: {len(self.clients)}")
        try:
            async for message in websocket:
                await self.messages.put((websocket, message))
        finally:
            self.clients.discard(websocket)
            logger.info(f"Client disconnected. Total clients: {len(self.clients)}")
            
    async def broadcast(self, message: str):
        """Broadcast a message to all connected clients."""
        if self.clients:
            await asyncio.gather(
                *[client.send(message) for client in self.clients],
                return_exceptions=True,
            )
            
    async def send_to(self, websocket, message: str):
        """Send a message to a specific client."""
        try:
            await websocket.send(message)
        except Exception:
            self.clients.discard(websocket)
            
    def get_messages(self) -> asyncio.Queue:
        """Get the messages queue."""
        return self.messages

# --- Agent State Manager ---

class AgentStateManager:
    """Manages agent states and task execution."""
    
    def __init__(self):
        self.agent_states: Dict[str, AgentState] = {}
        self.task_states: Dict[str, TaskStatus] = {}
        self.task_results: Dict[str, Any] = {}
        self.task_observers: Dict[str, List[Callable]] = {}
        
    def set_agent_state(self, agent_id: str, state: AgentState):
        """Set the state of an agent."""
        self.agent_states[agent_id] = state
        logger.info(f"Agent {agent_id} state set to {state}")
        
    def get_agent_state(self, agent_id: str) -> AgentState:
        """Get the state of an agent."""
        return self.agent_states.get(agent_id, STATE_IDLE)
        
    def set_task_status(self, task_id: str, status: TaskStatus):
        """Set the status of a task."""
        self.task_states[task_id] = status
        logger.info(f"Task {task_id} status set to {status}")
        
    def get_task_status(self, task_id: str) -> TaskStatus:
        """Get the status of a task."""
        return self.task_states.get(task_id, STATUS_PENDING)
        
    def set_task_result(self, task_id: str, result: Any):
        """Set the result of a task."""
        self.task_results[task_id] = result
        logger.info(f"Task {task_id} result set")
        
    def get_task_result(self, task_id: str) -> Any:
        """Get the result of a task."""
        return self.task_results.get(task_id)
        
    def register_observer(self, task_id: str, observer: Callable):
        """Register an observer for task status changes."""
        if task_id not in self.task_observers:
            self.task_observers[task_id] = []
        self.task_observers[task_id].append(observer)
        
    def _notify_observers(self, task_id: str, status: TaskStatus, result: Any = None):
        """Notify all observers of a task status change."""
        for observer in self.task_observers.get(task_id, []):
            try:
                observer(status, result)
            except Exception:
                pass

# --- Daemon Main ---

class JarvisDaemon:
    """Main daemon class that orchestrates the JARVIS MK-X system."""
    
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.ws_manager = WebSocketManager(host, port)
        self.agent_manager = AgentStateManager()
        self.memory = MemoryManager("jarvis_memory/vector_store.db")
        self.running = False
        
    async def start(self):
        """Start the daemon."""
        await self.ws_manager.start()
        self.running = True
        logger.info("JARVIS MK-X Daemon started")
        
    async def stop(self):
        """Stop the daemon."""
        self.running = False
        await self.ws_manager.stop()
        logger.info("JARVIS MK-X Daemon stopped")
        
    async def process_messages(self):
        """Process incoming WebSocket messages."""
        messages_queue = self.ws_manager.get_messages()
        while self.running:
            try:
                websocket, message = await asyncio.wait_for(
                    messages_queue.get(), timeout=1.0
                )
                await self._handle_message(websocket, message)
            except asyncio.TimeoutError:
                continue
                
    async def _handle_message(self, websocket, message: str):
        """Handle a WebSocket message."""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")
            
            if msg_type == "get_status":
                await self._handle_get_status(websocket, data)
            elif msg_type == "set_state":
                await self._handle_set_state(websocket, data)
            elif msg_type == "get_task_status":
                await self._handle_get_task_status(websocket, data)
            elif msg_type == "execute_task":
                await self._handle_execute_task(websocket, data)
            elif msg_type == "semantic_search":
                await self._handle_semantic_search(websocket, data)
            elif msg_type == "remember":
                await self._handle_remember(websocket, data)
            elif msg_type == "memory_search":
                await self._handle_memory_search(websocket, data)
            elif msg_type == "recall":
                await self._handle_recall(websocket, data)
            elif msg_type == "forget":
                await self._handle_forget(websocket, data)
            elif msg_type == "memory_stats":
                await self._handle_memory_stats(websocket, data)
            elif msg_type == "consolidate":
                await self._handle_consolidate(websocket, data)
            elif msg_type == "ping":
                await self._handle_ping(websocket, data)
            else:
                logger.warning(f"Unknown message type: {msg_type}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON message: {message}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            
    async def _handle_get_status(self, websocket, data: dict):
        """Handle get_status message."""
        agent_id = data.get("agent_id", "default")
        state = self.agent_manager.get_agent_state(agent_id)
        await self.ws_manager.send_to(websocket, json.dumps({
            "type": "status_response",
            "agent_id": agent_id,
            "state": state,
        }))
        
    async def _handle_set_state(self, websocket, data: dict):
        """Handle set_state message."""
        agent_id = data.get("agent_id", "default")
        state = data.get("state", STATE_IDLE)
        self.agent_manager.set_agent_state(agent_id, state)
        await self.ws_manager.broadcast(json.dumps({
            "type": "state_updated",
            "agent_id": agent_id,
            "state": state,
        }))
        
    async def _handle_get_task_status(self, websocket, data: dict):
        """Handle get_task_status message."""
        task_id = data.get("task_id", "default")
        status = self.agent_manager.get_task_status(task_id)
        result = self.agent_manager.get_task_result(task_id)
        await self.ws_manager.send_to(websocket, json.dumps({
            "type": "task_status_response",
            "task_id": task_id,
            "status": status,
            "result": result,
        }))
        
    async def _handle_execute_task(self, websocket, data: dict):
        """Handle execute_task message."""
        task_id = data.get("task_id", "default")
        goal = data.get("goal", "")

        self.agent_manager.set_task_status(task_id, STATUS_RUNNING)

        # Record the task goal as an episode memory (fire-and-forget)
        try:
            self.memory.remember(
                type="episode",
                content=f"Task executed: {goal}",
                subject="JARVIS",
                predicate="executed",
                obj=goal,
                importance=0.6,
                task_id=task_id,
                source="daemon.execute_task",
            )
        except Exception:
            logger.exception("Failed to record task episode")

        # Simulate task execution
        await asyncio.sleep(2)  # Simulate work

        self.agent_manager.set_task_status(task_id, STATUS_COMPLETED)
        self.agent_manager.set_task_result(task_id, {
            "output": f"Task completed: {goal}",
            "duration": 2.0,
        })

        await self.ws_manager.send_to(websocket, json.dumps({
            "type": "task_completed",
            "task_id": task_id,
            "status": STATUS_COMPLETED,
            "result": {"output": f"Task completed: {goal}", "duration": 2.0},
        }))

    async def _handle_semantic_search(self, websocket, data: dict):
        """Handle semantic_search message (text-based hybrid search)."""
        query = data.get("query", "")
        k = data.get("k", 10)

        # Use the memory fabric (FTS5 + metadata) with the real query text
        results = self.memory.search(query=query or None, limit=k)

        await self.ws_manager.send_to(websocket, json.dumps({
            "type": "semantic_search_response",
            "query": query,
            "results": results,
            "k": k,
        }))

    async def _handle_remember(self, websocket, data: dict):
        """Handle remember message — store a memory."""
        mid = self.memory.remember(
            type=data.get("memory_type", "fact"),
            content=data.get("content", ""),
            subject=data.get("subject"),
            predicate=data.get("predicate"),
            obj=data.get("object"),
            importance=data.get("importance", 0.5),
            session_id=data.get("session_id"),
            task_id=data.get("task_id"),
            source=data.get("source", "daemon"),
        )
        await self.ws_manager.send_to(websocket, json.dumps({
            "type": "remember_response",
            "memory_id": mid,
            "stored": mid is not None,
        }))

    async def _handle_memory_search(self, websocket, data: dict):
        """Handle memory_search message — hybrid memory retrieval."""
        results = self.memory.search(
            query=data.get("query"),
            subject=data.get("subject"),
            type=data.get("type"),
            limit=data.get("limit", 15),
        )
        await self.ws_manager.send_to(websocket, json.dumps({
            "type": "memory_search_response",
            "query": data.get("query"),
            "results": results,
            "count": len(results),
        }))

    async def _handle_recall(self, websocket, data: dict):
        """Handle recall message — fetch a single memory by id."""
        record = self.memory.recall(data.get("memory_id", ""))
        await self.ws_manager.send_to(websocket, json.dumps({
            "type": "recall_response",
            "memory_id": data.get("memory_id"),
            "record": record,
        }))

    async def _handle_forget(self, websocket, data: dict):
        """Handle forget message — soft-delete a memory."""
        ok = self.memory.forget(data.get("memory_id", ""))
        await self.ws_manager.send_to(websocket, json.dumps({
            "type": "forget_response",
            "memory_id": data.get("memory_id"),
            "forgotten": ok,
        }))

    async def _handle_memory_stats(self, websocket, data: dict):
        """Handle memory_stats message — memory usage snapshot."""
        stats = self.memory.stats()
        await self.ws_manager.send_to(websocket, json.dumps({
            "type": "memory_stats_response",
            "stats": stats,
        }))

    async def _handle_consolidate(self, websocket, data: dict):
        """Handle consolidate message — run dedup/conflict resolution."""
        result = self.memory.consolidate()
        await self.ws_manager.send_to(websocket, json.dumps({
            "type": "consolidate_response",
            "result": result,
        }))

    async def _handle_ping(self, websocket, data: dict):
        """Handle ping message — liveness check."""
        await self.ws_manager.send_to(websocket, json.dumps({
            "type": "pong",
            "memory_backend": "fabric" if self.memory.available else "vector_fallback",
        }))
        
    async def run(self):
        """Run the daemon main loop."""
        await self.start()
        await self.process_messages()

def main():
    """Main entry point for the daemon."""
    import argparse
    
    parser = argparse.ArgumentParser(description="JARVIS MK-X Daemon")
    parser.add_argument("--host", default=DEFAULT_HOST, help="WebSocket host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="WebSocket port")
    parser.add_argument("--health", action="store_true", help="Run health check and exit")
    
    args = parser.parse_args()
    
    daemon = JarvisDaemon(host=args.host, port=args.port)
    
    async def run_daemon():
        await daemon.start()
        # Process messages in background
        import concurrent.futures
        loop = asyncio.get_event_loop()
        with futures.ThreadPoolExecutor() as executor:
            loop.run_in_executor(executor, lambda: asyncio.run(daemon.process_messages()))
        # Keep running
        try:
            while daemon.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        await daemon.stop()
    
    try:
        asyncio.run(run_daemon())
    except KeyboardInterrupt:
        logger.info("Daemon interrupted by user")
    except Exception as e:
        logger.error(f"Daemon error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()