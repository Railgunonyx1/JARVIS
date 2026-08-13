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
            (id, json_lib.dumps(embedding), str(metadata) if metadata else None)
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
                stored_arr = numpy.array(json_lib.loads(row[1]), dtype=numpy.float64)
                if stored_arr.size > 0 and query_norm > 0:
                    dot = numpy.dot(query_arr, stored_arr)
                    stored_norm = numpy.linalg.norm(stored_arr)
                    cosine = dot / (query_norm * stored_norm) if stored_norm > 0 else 0
                    distance = 1 - cosine  # distance = 1 - similarity
                    results.append({"id": row[0], "distance": float(distance)})
            except (json_lib.JSONDecodeError, ValueError):
                continue
        conn.close()
        
        # Sort by distance (lower = more similar) and limit to k
        results.sort(key=lambda x: x["distance"])
        return results[:k]

# --- OpenTelemetry Tracing ---

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
            
    async def get_messages(self) -> asyncio.Queue:
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
        self.vector_search = VectorSearch("jarvis_memory/vector_store.db")
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
        """Handle semantic_search message."""
        query = data.get("query", "")
        k = data.get("k", 10)
        
        # Perform vector search
        results = self.vector_search.semantic_search([0.1] * 768, k=k)
        
        await self.ws_manager.send_to(websocket, json.dumps({
            "type": "semantic_search_response",
            "query": query,
            "results": results,
            "k": k,
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