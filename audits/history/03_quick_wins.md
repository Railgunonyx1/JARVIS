# JARVIS MK-X — Quick Wins (30 Minutes or Less Each)

## Priority Fixes with Immediate Impact

> **Note:** Do NOT create a universal `async_sleep()` helper. Use explicit `await asyncio.sleep()` in async code and `time.sleep()` in sync code. The distinction is clearer and impossible to misuse.

---

### Fix #1: Wrap `_piper()` in `asyncio.to_thread()`
**Time:** ~5 minutes | **Impact:** Unblocks event loop during TTS

**File:** `pipeline/tts.py`
**Change:** Line ~143-160

```python
# BEFORE (blocks event loop):
async def _piper(text: str, voice: str | None = None) -> bytes | None:
    ...
    for chunk in model.synthesize(clean_text, audio_config):
        audio_bytes += chunk
    ...

# AFTER:
async def _piper(text: str, voice: str | None = None) -> bytes | None:
    ...
    def _synthesize():
        result = b""
        for chunk in model.synthesize(clean_text, audio_config):
            result += chunk
        return result
    audio_bytes = await asyncio.to_thread(_synthesize)
    ...
```

**Important:** Do NOT parallelize Piper synthesis. It's CPU-bound and parallel execution increases contention. Use a single dedicated worker thread.

---

### Fix #2: Persistent HTTP Client for LLM Providers
**Time:** ~20 minutes | **Impact:** Saves 50-200ms per request (DNS + TCP + TLS)

**Files:** `providers/groq_provider.py`, `providers/openrouter_provider.py`, `providers/zen_provider.py`

```python
# Add at module level or class init:
import httpx

# Store client as class/instance attribute:
self._client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0),
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
)

# Reuse for every request:
async def _call_api(self, messages, **kwargs):
    response = await self._client.post(
        self.api_url,
        json=payload,
        headers=self.headers
    )
    return response

# Cleanup on shutdown:
async def close(self):
    await self._client.aclose()
```

---

### Fix #3: Fire-and-Forget with Async Queue (Not create_task)
**Time:** ~15 minutes | **Impact:** Removes 1-5ms blocking per stream, bounded thread usage

**File:** `core/jarvis.py` + new `core/log_queue.py`

```python
# NEW: core/log_queue.py
import asyncio
from collections import deque

class LogQueue:
    def __init__(self, max_size=1000):
        self._queue = asyncio.Queue(maxsize=max_size)
        self._worker_task = None
    
    async def start(self):
        self._worker_task = asyncio.create_task(self._worker())
    
    async def _worker(self):
        while True:
            role, content = await self._queue.get()
            try:
                await asyncio.to_thread(memory.log_conversation, role, content)
            except Exception:
                pass  # Don't crash on logging failure
            self._queue.task_done()
    
    async def put(self, role: str, content: str):
        try:
            self._queue.put_nowait((role, content))
        except asyncio.QueueFull:
            pass  # Drop oldest or skip

# In jarvis.py:
log_queue = LogQueue()
await log_queue.start()

# Replace:
# memory.log_conversation(role, text)
# With:
await log_queue.put(role, text)
```

---

### Fix #4: Skip Markdown Cleanup During Streaming
**Time:** ~5 minutes | **Impact:** Removes 6 regex runs per token

**File:** `core/jarvis.py`

```python
# BEFORE (runs per token):
text = _strip_md(token)
yield ("text", text)

# AFTER (skip during streaming, clean at end):
yield ("text", token)  # Raw token

# Then at end of stream:
final_text = _strip_md(full_response)
```

**Note:** Keep `_strip_md()` for non-streaming responses and final display.

---

### Fix #5: Batch Frontend DOM Updates
**Time:** ~20 minutes | **Impact:** One browser repaint instead of dozens

**File:** `web/static/index.html`

```javascript
// BEFORE (per token):
function appendToken(token) {
    chatLog.innerHTML += token;  // Triggers repaint
}

// AFTER (batch with requestAnimationFrame):
let pendingTokens = [];
let rafPending = false;

function appendToken(token) {
    pendingTokens.push(token);
    if (!rafPending) {
        rafPending = true;
        requestAnimationFrame(flushTokens);
    }
}

function flushTokens() {
    if (pendingTokens.length > 0) {
        chatLog.innerHTML += pendingTokens.join('');
        pendingTokens = [];
    }
    rafPending = false;
}
```

---

### Fix #6: Replace Blocking Retry Loops
**Time:** ~15 minutes | **Impact:** Removes 300ms-7s blocking

**File:** `actions/open_app.py`

```python
# BEFORE (up to 7s blocking):
for attempt in range(10):
    time.sleep(0.3)
    if check_process():
        break

# AFTER (non-blocking with timeout):
async def _check_with_timeout(process_name, timeout=2.0):
    start = time.time()
    while time.time() - start < timeout:
        if _is_running(process_name):
            return True
        await asyncio.sleep(0.1)  # Explicit async sleep
    return False
```

---

### Fix #7: Use `heapq.nlargest()` for Process Sorting
**Time:** ~5 minutes | **Impact:** O(n) vs O(n log n)

**File:** `actions/process_manager.py`

```python
import heapq

# BEFORE:
sorted(all_procs, key=lambda p: abs(p.get("cpu", 0)), reverse=True)[:n]

# AFTER:
heapq.nlargest(n, all_procs, key=lambda p: abs(p.get("cpu", 0)))
```

---

### Fix #8: Lazy Plugin Loading
**Time:** ~20 minutes | **Impact:** Faster startup, less memory

**File:** `core/jarvis.py` or plugin loader

```python
# BEFORE (load all at startup):
from actions import weather, github, vision, desktop, media, calendar

# AFTER (load on first use):
_plugins = {}
def get_plugin(name):
    if name not in _plugins:
        if name == "weather":
            from actions import weather
            _plugins[name] = weather
        elif name == "github":
            from actions import github
            _plugins[name] = github
        # ...
    return _plugins[name]
```

---

### Fix #9: Configurable Polling Intervals
**Time:** ~10 minutes | **Impact:** Tunable without code changes

**File:** `config/config.toml` or new `config/polling.py`

```python
# config/polling.py
SERVER_POLL_INTERVAL = 0.05      # 50ms
UI_REFRESH_INTERVAL = 0.016      # 16ms (60fps)
STREAM_FLUSH_INTERVAL = 0.025    # 25ms
PLUGIN_SCAN_INTERVAL = 1.0       # 1s
MEMORY_FLUSH_INTERVAL = 5.0      # 5s
```

---

## Implementation Checklist

- [ ] Fix #1: `_piper()` asyncio.to_thread (5min)
- [ ] Fix #2: Persistent HTTP client (20min)
- [ ] Fix #3: Async log queue (15min)
- [ ] Fix #4: Skip markdown during streaming (5min)
- [ ] Fix #5: Batch frontend DOM updates (20min)
- [ ] Fix #6: Replace blocking retries (15min)
- [ ] Fix #7: heapq.nlargest for processes (5min)
- [ ] Fix #8: Lazy plugin loading (20min)
- [ ] Fix #9: Configurable polling intervals (10min)

**Total estimated time:** ~115 minutes for all 9 fixes
**Expected combined impact:** 40-60% reduction in typical response latency
