# JARVIS MK-X — Architecture Recommendations

## Structural Improvements for Scale and Maintainability

---

## 1. Vector Database Migration (Highest Priority)

**Current:** O(n) full scan with `json.loads()` per row
**Problem:** Won't scale past 1000 memories
**Recommendation:** Migrate to FAISS, sqlite-vec, or ChromaDB

```python
# NEW: memory/vector_index.py
import numpy as np

class VectorIndex:
    def __init__(self, dimension=384):
        self.dimension = dimension
        self.embeddings = np.empty((0, dimension), dtype=np.float32)
        self.metadata = []
        self._index = None  # FAISS index
    
    def load_from_sqlite(self, db_path: str):
        """Load all embeddings into memory at startup."""
        import sqlite3
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT id, text, embedding FROM vector_memories").fetchall()
        
        for row_id, text, embedding_json in rows:
            embedding = np.array(json.loads(embedding_json), dtype=np.float32)
            self.embeddings = np.vstack([self.embeddings, embedding.reshape(1, -1)])
            self.metadata.append({"id": row_id, "text": text})
        
        # Build FAISS index
        import faiss
        self._index = faiss.IndexFlatIP(self.dimension)  # Inner product = cosine for normalized vectors
        faiss.normalize_L2(self.embeddings)
        self._index.add(self.embeddings)
    
    def search(self, query_embedding: np.ndarray, k: int = 5) -> list:
        """O(log n) approximate nearest neighbor search."""
        query = query_embedding.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(query)
        
        distances, indices = self._index.search(query, k)
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx >= 0:
                results.append({
                    "text": self.metadata[idx]["text"],
                    "score": float(dist),
                    "id": self.metadata[idx]["id"]
                })
        return results
```

**Implementation:** 
1. Install `faiss-cpu` or `sqlite-vec`
2. Create migration script to convert existing embeddings
3. Load index at startup (one-time cost)
4. Replace all `search_similar()` calls

---

## 2. Persistent HTTP Clients

**Current:** New connection per request
**Problem:** 50-200ms overhead per LLM/STT/TTS call
**Recommendation:** `httpx.AsyncClient()` for application lifetime

```python
# NEW: providers/http_client.py
import httpx

class HttpClient:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10
                ),
                http2=True  # Enable HTTP/2 if supported
            )
        return cls._instance
    
    @property
    def client(self):
        return self._client
    
    async def close(self):
        await self._client.aclose()
```

**Implementation:** Replace all `httpx.post()` / `requests.post()` with `HttpClient().client.post()`.

---

## 3. Binary WebSocket Audio

**Current:** WAV → Base64 → JSON → SSE → decode → play
**Problem:** 33% payload increase, encoding/decoding overhead
**Recommendation:** Binary WebSocket frames for audio

```python
# NEW: web/audio_ws.py
import websockets
import asyncio

class AudioWebSocket:
    def __init__(self):
        self._clients = set()
    
    async def handler(self, websocket, path):
        self._clients.add(websocket)
        try:
            async for message in websocket:
                pass  # Client messages (if any)
        finally:
            self._clients.remove(websocket)
    
    async def broadcast_audio(self, audio_bytes: bytes):
        """Send binary audio to all connected clients."""
        for client in self._clients.copy():
            try:
                await client.send(audio_bytes)  # Binary frame
            except websockets.exceptions.ConnectionClosed:
                self._clients.discard(client)
```

**Frontend:**
```javascript
const audioWs = new WebSocket(`ws://${host}/audio`);
audioWs.binaryType = 'arraybuffer';

audioWs.onmessage = (event) => {
    const audioBlob = new Blob([event.data], { type: 'audio/wav' });
    const audioUrl = URL.createObjectURL(audioBlob);
    const audio = new Audio(audioUrl);
    audio.play();
};
```

---

## 4. Incremental Prompt Assembly

**Current:** Rebuild system prompt + memory + history every request
**Problem:** Redundant computation
**Recommendation:** Mutable prompt object, update only changed sections

```python
# NEW: core/prompt_builder.py
class PromptBuilder:
    def __init__(self):
        self._system_prompt = None
        self._memory_context = None
        self._world_state = None
        self._history = []
    
    def set_system_prompt(self, prompt: str):
        self._system_prompt = prompt
    
    def set_memory(self, memory: str):
        self._memory_context = memory
    
    def set_world_state(self, state: dict):
        self._world_state = state
    
    def add_turn(self, role: str, content: str):
        self._history.append({"role": role, "content": content})
        if len(self._history) > 20:
            self._history = self._history[-10:]  # Keep last 10
    
    def build(self, user_message: str) -> list:
        """Build messages without rebuilding unchanged parts."""
        messages = []
        
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        
        if self._memory_context:
            messages.append({"role": "system", "content": f"Memory:\n{self._memory_context}"})
        
        messages.extend(self._history)
        messages.append({"role": "user", "content": user_message})
        
        return messages
```

---

## 5. Speculative Execution

**Current:** Wait for STT to finish before starting context/memory
**Problem:** Sequential execution wastes time
**Recommendation:** Start parallel work as soon as intent is detected

```python
# In process_text_streaming():
async def process_text_streaming(self, text: str, ...):
    # Start these in parallel IMMEDIATELY
    intent_task = asyncio.create_task(self._intent_router.classify(text))
    context_task = asyncio.create_task(self._context_engine.get_history())
    memory_task = asyncio.create_task(self._memory.search_similar(text))
    
    # Wait for intent first (needed for routing)
    intent = await intent_task
    
    # Context and memory may already be done
    context = await context_task
    memory = await memory_task
    
    # Now proceed with LLM...
```

---

## 6. Background Embedding Generation

**Current:** Generate embeddings during request path
**Problem:** User waits for embedding computation
**Recommendation:** Queue embeddings for background processing

```python
# NEW: memory/embedding_queue.py
class EmbeddingQueue:
    def __init__(self):
        self._queue = asyncio.Queue()
        self._worker_task = None
    
    async def start(self):
        self._worker_task = asyncio.create_task(self._worker())
    
    async def _worker(self):
        while True:
            text, category = await self._queue.get()
            try:
                embedding = await self._generate_embedding(text)
                await self._store_embedding(text, embedding, category)
            except Exception as e:
                logger.error(f"Embedding failed: {e}")
            self._queue.task_done()
    
    async def enqueue(self, text: str, category: str = "conversation"):
        await self._queue.put((text, category))
```

---

## 7. Provider Warm-up

**Current:** Cold start on first request
**Problem:** First request has high latency
**Recommendation:** Initialize providers at startup

```python
# In startup sequence:
async def warm_up_providers():
    """Perform lightweight requests to warm up connections."""
    tasks = [
        warm_up_groq(),
        warm_up_openrouter(),
        warm_up_piper(),
        warm_up_vector_index(),
    ]
    await asyncio.gather(*tasks)

async def warm_up_groq():
    """Send minimal request to establish connection."""
    try:
        await groq_provider.chat([{"role": "user", "content": "ping"}])
    except Exception:
        pass  # Connection established even if request fails
```

---

## 8. Lazy Module Loading

**Current:** Heavy imports at startup
**Problem:** 500-2000ms startup, 50-200MB RAM
**Recommendation:** Lazy loading pattern

```python
# NEW: core/lazy_imports.py
class LazyModule:
    def __init__(self, module_name):
        self._module_name = module_name
        self._module = None
    
    def __getattr__(self, name):
        if self._module is None:
            import importlib
            self._module = importlib.import_module(self._module_name)
        return getattr(self._module, name)

# Usage:
cv2 = LazyModule("cv2")
mediapipe = LazyModule("mediapipe")
```

---

## 9. Metrics Collection

**Current:** Ad-hoc timing
**Problem:** No unified metrics
**Recommendation:** Centralized metrics with instrumentation

```python
# NEW: core/metrics.py
import time
from collections import defaultdict

class Metrics:
    def __init__(self):
        self._timers = defaultdict(list)
        self._counters = defaultdict(int)
    
    def timer(self, name: str):
        """Context manager for timing."""
        return TimerContext(self, name)
    
    def increment(self, name: str):
        self._counters[name] += 1
    
    def record(self, name: str, value_ms: float):
        self._timers[name].append(value_ms)
    
    def get_percentiles(self, name: str) -> dict:
        values = sorted(self._timers[name])
        n = len(values)
        if n == 0:
            return {}
        return {
            "p50": values[n // 2],
            "p90": values[int(n * 0.9)],
            "p99": values[int(n * 0.99)],
            "count": n
        }

class TimerContext:
    def __init__(self, metrics: Metrics, name: str):
        self._metrics = metrics
        self._name = name
        self._start = None
    
    def __enter__(self):
        self._start = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        elapsed = (time.perf_counter() - self._start) * 1000
        self._metrics.record(self._name, elapsed)
```

**Usage:**
```python
with metrics.timer("llm.ttft"):
    first_token = await llm.generate(messages)
```

---

## Implementation Priority

1. **Immediate** (Phase 1, 1-2 hours): Quick wins from `03_quick_wins.md`
2. **Core Architecture** (Phase 2, 4-6 hours): Persistent HTTP, vector DB, incremental prompts
3. **Advanced Features** (Phase 3, 8-12 hours): Binary WebSocket, speculative execution, metrics
4. **Scale Preparation** (Phase 4, 12+ hours): Provider warm-up, lazy loading, background embedding

**Total estimated effort:** 25-35 hours for full implementation
**Expected outcome:** 50-70% latency reduction, 10x easier maintenance, scales to 100k+ memories
