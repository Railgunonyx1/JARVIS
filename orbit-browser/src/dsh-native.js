/**
 * JARVIS Orbit — Native DSH Integration
 * 
 * Connects directly to the JARVIS bridge server (127.0.0.1:8170)
 * without needing the browser extension. Full access to:
 * 
 * - Chat (SSE streaming)
 * - Agent tasks (autonomous browsing)
 * - Tool execution
 * - Status monitoring
 * - Memory operations
 * 
 * Endpoints:
 * GET  /status     -> {"ok": bool, "kernel": "online"|"offline"}
 * POST /v1/chat    -> SSE stream of {"type":"start|delta|done|error"}
 * POST /v1/agent   -> SSE stream of agent task execution
 */

class DSHNative {
  constructor(config = {}) {
    this.config = {
      baseUrl: config.baseUrl || 'http://127.0.0.1:8170',
      wsUrl: config.wsUrl || 'ws://127.0.0.1:8171',
      authToken: config.authToken || null,
      timeout: config.timeout || 30000,
      retryAttempts: config.retryAttempts || 3,
      retryDelay: config.retryDelay || 1000,
      ...config,
    };
    // A-01: the launcher generates a per-launch token and exports it to the
    // main process; the renderer reads it once via the preload boundary and
    // every request (all via getHeaders()) carries it.
    if (!this.config.authToken && typeof window !== 'undefined' && window.orbit && typeof window.orbit.getBridgeToken === 'function') {
      try { this.config.authToken = window.orbit.getBridgeToken() || null; } catch (_) {}
    }
    
    this.status = {
      connected: false,
      kernel: 'offline',
      lastCheck: null,
      error: null,
    };
    
    this.sessions = new Map();
    this.activeStreams = new Map();
    this.messageQueue = [];
    this.maxQueueSize = 100;
    
    this.listeners = {
      status: [],
      message: [],
      agent: [],
      error: [],
      model: [],
    };
    
    this.init();
  }

  init() {
    // Status updates: PRIMARY channel is the WS push (bridge watchdog pushes
    // online/offline transitions; main forwards them via onStatus — see
    // jarvis.js wireDshNative). This poll is only a 30s SAFETY NET for the
    // case where the bridge process itself is dead (no pushes can arrive).
    // Was a fixed 5s poll (~12 fetches/min forever) — spec rule: "Renderer
    // does not poll JARVIS. Events only."
    this.startStatusPolling(30000);
    
    // Setup reconnection
    this.setupReconnection();
    
    console.log('[DSH] Native integration initialized');
  }

  // ── Status Management ───────────────────────────────────────────
  
  startStatusPolling(intervalMs = 30000) {
    // Single self-scheduling loop (was: setInterval + a separate reconnect
    // timer that double-fired). When the bridge is DOWN the delay grows
    // exponentially to a 30s cap instead of hammering a dead port every
    // ~1s forever (measured 2026-09-17: 16 failed connects in 20s while
    // services were down — connection-attempt storm, console noise, and
    // renderer network churn). Healthy state: 30s safety-net cadence —
    // live status arrives via WS push, not this loop.
    this._pollBaseMs = intervalMs;
    this._pollDelayMs = intervalMs;
    this._polling = true;
    this._checking = false;
    this._scheduleNextCheck(0); // immediate first check
  }

  _scheduleNextCheck(delayMs) {
    if (!this._polling) return;
    if (this._pollTimer) clearTimeout(this._pollTimer);
    this._pollTimer = setTimeout(async () => {
      if (this._checking) { this._scheduleNextCheck(500); return; }
      this._checking = true;
      try {
        const st = await this.checkStatus();
        this._pollDelayMs = st.connected
          ? this._pollBaseMs
          : Math.min((this._pollDelayMs || this._pollBaseMs) * 2, 30000);
      } catch (e) {
        this._pollDelayMs = Math.min((this._pollDelayMs || this._pollBaseMs) * 2, 30000);
      } finally {
        this._checking = false;
      }
      this._scheduleNextCheck(this._pollDelayMs);
    }, delayMs);
  }

  stopStatusPolling() {
    this._polling = false;
    if (this._pollTimer) {
      clearTimeout(this._pollTimer);
      this._pollTimer = null;
    }
    if (this.statusInterval) {
      clearInterval(this.statusInterval);
      this.statusInterval = null;
    }
  }

  async checkStatus() {
    try {
      const response = await fetch(`${this.config.baseUrl}/status`, {
        method: 'GET',
        headers: this.getHeaders(),
        signal: AbortSignal.timeout(5000),
      });
      
      const data = await response.json();
      
      this.status = {
        connected: response.ok,
        kernel: data.kernel || 'offline',
        lastCheck: Date.now(),
        error: null,
        ...data,
      };
      
      this.emit('status', this.status);
      
      return this.status;
    } catch (error) {
      this.status = {
        connected: false,
        kernel: 'offline',
        lastCheck: Date.now(),
        error: error.message,
      };
      
      this.emit('status', this.status);
      
      return this.status;
    }
  }

  // ── Chat API ────────────────────────────────────────────────────
  
  async chat(message, options = {}) {
    const {
      sessionId = this.stableSessionId(),
      page = null,
      stream = true,
      model = this.selectedModel || null,
    } = options;
    
    const payload = {
      text: message,
      session_id: sessionId,
      page,
    };
    // Conversation continuity: when the caller supplies prior messages
    // (options.messages), send them so the model sees the thread. The
    // bridge merges messages + text server-side.
    if (Array.isArray(options.messages) && options.messages.length) {
      payload.messages = this.conversationFrom(options.messages, message);
    }
    // Per-chat model selection: "provider/model" id from /v1/models. The
    // bridge resolves which provider owns it; unset -> router default chain.
    if (model) payload.model = model;
    
    if (stream) {
      return this.streamChat(payload, sessionId);
    } else {
      return this.sendChat(payload);
    }
  }

  // ── Model Selection ───────────────────────────────────────────

  get selectedModel() {
    try {
      return localStorage.getItem('orbit-model') || null;
    } catch (_) {
      return null;
    }
  }

  set selectedModel(id) {
    try {
      if (id) localStorage.setItem('orbit-model', id);
      else localStorage.removeItem('orbit-model');
    } catch (_) { /* storage unavailable */ }
    this.emit('model', id);
  }

  /** Fetch selectable models from the bridge (config + live Ollama tags). */
  async listModels() {
    try {
      const response = await fetch(`${this.config.baseUrl}/v1/models`, {
        method: 'GET',
        headers: this.getHeaders(),
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      return Array.isArray(data.models) ? data.models : [];
    } catch (error) {
      console.error('[DSH] listModels error:', error);
      return [];
    }
  }

  async sendChat(payload) {
    try {
      const response = await fetch(`${this.config.baseUrl}/v1/chat`, {
        method: 'POST',
        headers: {
          ...this.getHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let result = '';
      let buffer = '';
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        // SSE lines can straddle network chunks — buffer the partial tail.
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'done') {
                result = event.text || result;
              } else if (event.type === 'error') {
                throw new Error(event.message || 'Chat error');
              }
            } catch (e) {
              // Skip invalid JSON
            }
          }
        }
      }
      
      return { success: true, text: result, sessionId: payload.session_id };
    } catch (error) {
      console.error('[DSH] Chat error:', error);
      return { success: false, error: error.message };
    }
  }

  async streamChat(payload, sessionId) {
    const streamId = `stream-${Date.now()}`;
    
    try {
      const response = await fetch(`${this.config.baseUrl}/v1/chat`, {
        method: 'POST',
        headers: {
          ...this.getHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      
      this.activeStreams.set(streamId, {
        reader,
        sessionId,
        startTime: Date.now(),
      });
      
      let fullText = '';
      let buffer = '';
      
      // Process stream
      const processStream = async () => {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            // SSE lines can straddle network chunks — buffer the partial tail.
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const event = JSON.parse(line.slice(6));
                  
                  switch (event.type) {
                    case 'start':
                      this.emit('message', {
                        type: 'start',
                        sessionId,
                        streamId,
                      });
                      break;
                      
                    case 'delta':
                      if (event.text) {
                        fullText += event.text;
                        this.emit('message', {
                          type: 'delta',
                          text: event.text,
                          fullText,
                          sessionId,
                          streamId,
                        });
                      }
                      break;
                      
                    case 'done':
                      this.emit('message', {
                        type: 'done',
                        text: event.text || fullText,
                        sessionId,
                        streamId,
                      });
                      break;

                    case 'meta':
                      // Router telemetry: which provider/model actually served
                      // the reply (event.model = "provider/model" id).
                      this.emit('message', {
                        type: 'meta',
                        model: event.model || null,
                        provider: event.provider || null,
                        sessionId,
                        streamId,
                      });
                      break;
                      
                    case 'error':
                      this.emit('error', {
                        type: 'chat_error',
                        message: event.message,
                        sessionId,
                        streamId,
                      });
                      break;
                  }
                } catch (e) {
                  // Skip invalid JSON
                }
              }
            }
          }
        } finally {
          this.activeStreams.delete(streamId);
        }
      };
      
      processStream();
      
      return { streamId, sessionId };
    } catch (error) {
      console.error('[DSH] Stream error:', error);
      this.activeStreams.delete(streamId);
      return { success: false, error: error.message };
    }
  }

  // ── Agent API ───────────────────────────────────────────────────
  
  async runAgent(task, options = {}) {
    const {
      sessionId = this.generateSessionId(),
      page = null,
      stream = true,
    } = options;
    
    const payload = {
      task,
      session_id: sessionId,
      page,
    };
    
    if (stream) {
      return this.streamAgent(payload, sessionId);
    } else {
      return this.sendAgent(payload);
    }
  }

  async sendAgent(payload) {
    try {
      const response = await fetch(`${this.config.baseUrl}/v1/agent`, {
        method: 'POST',
        headers: {
          ...this.getHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `HTTP ${response.status}`);
      }
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let result = '';
      let steps = [];
      let buffer = '';
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        // SSE lines can straddle network chunks — buffer the partial tail.
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));
              
              if (event.type === 'done') {
                result = event.text || result;
              } else if (event.type === 'step') {
                steps.push(event);
              } else if (event.type === 'error') {
                throw new Error(event.message || 'Agent error');
              }
            } catch (e) {
              // Skip invalid JSON
            }
          }
        }
      }
      
      return { success: true, text: result, steps, sessionId: payload.session_id };
    } catch (error) {
      console.error('[DSH] Agent error:', error);
      return { success: false, error: error.message };
    }
  }

  async streamAgent(payload, sessionId) {
    const streamId = `agent-${Date.now()}`;
    
    try {
      const response = await fetch(`${this.config.baseUrl}/v1/agent`, {
        method: 'POST',
        headers: {
          ...this.getHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `HTTP ${response.status}`);
      }
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      
      this.activeStreams.set(streamId, {
        reader,
        sessionId,
        type: 'agent',
        startTime: Date.now(),
      });
      
      let fullText = '';
      let steps = [];
      let buffer = '';
      
      const processStream = async () => {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            // SSE lines can straddle network chunks — buffer the partial tail.
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const event = JSON.parse(line.slice(6));
                  
                  switch (event.type) {
                    case 'start':
                      this.emit('agent', {
                        type: 'start',
                        sessionId,
                        streamId,
                        task: payload.task,
                      });
                      break;
                      
                    case 'delta':
                      if (event.text) {
                        fullText += event.text;
                        this.emit('agent', {
                          type: 'delta',
                          text: event.text,
                          fullText,
                          sessionId,
                          streamId,
                        });
                      }
                      break;
                      
                    case 'step':
                      steps.push(event);
                      this.emit('agent', {
                        type: 'step',
                        step: event,
                        steps,
                        sessionId,
                        streamId,
                      });
                      break;
                      
                    case 'done':
                      this.emit('agent', {
                        type: 'done',
                        text: event.text || fullText,
                        steps,
                        sessionId,
                        streamId,
                      });
                      break;
                      
                    case 'error':
                      this.emit('error', {
                        type: 'agent_error',
                        message: event.message,
                        sessionId,
                        streamId,
                      });
                      break;
                  }
                } catch (e) {
                  // Skip invalid JSON
                }
              }
            }
          }
        } finally {
          this.activeStreams.delete(streamId);
        }
      };
      
      processStream();
      
      return { streamId, sessionId };
    } catch (error) {
      console.error('[DSH] Agent stream error:', error);
      this.activeStreams.delete(streamId);
      return { success: false, error: error.message };
    }
  }

  // ── Tool Execution ──────────────────────────────────────────────
  
  async executeTool(toolName, toolArgs = {}, options = {}) {
    const { sessionId = this.generateSessionId() } = options;
    
    const command = {
      tool: toolName,
      arguments: toolArgs,
      id: `tool-${Date.now()}`,
    };
    
    try {
      // Use agent endpoint for tool execution
      const result = await this.runAgent(
        `Execute tool: ${toolName} with arguments: ${JSON.stringify(toolArgs)}`,
        { sessionId }
      );
      
      return result;
    } catch (error) {
      console.error('[DSH] Tool execution error:', error);
      return { success: false, error: error.message };
    }
  }

  // ── Browser Commands ────────────────────────────────────────────
  
  async navigate(url) {
    return this.executeTool('orbit.navigate', { url });
  }

  async read(tabId = null) {
    return this.executeTool('orbit.read', { tab_id: tabId });
  }

  async click(selector) {
    return this.executeTool('orbit.click', { selector });
  }

  async type(selector, text) {
    return this.executeTool('orbit.type', { selector, text });
  }

  async screenshot() {
    return this.executeTool('orbit.screenshot', {});
  }

  // ── Memory Operations ───────────────────────────────────────────
  
  async storeMemory(content, metadata = {}) {
    return this.executeTool('memory.store', { content, ...metadata });
  }

  async recallMemory(query) {
    return this.executeTool('memory.recall', { query });
  }

  // ── Session Management ──────────────────────────────────────────
  
  getSession(sessionId) {
    return this.sessions.get(sessionId);
  }

  createSession(options = {}) {
    const sessionId = options.id || this.generateSessionId();
    const session = {
      id: sessionId,
      created: Date.now(),
      messages: [],
      ...options,
    };
    
    this.sessions.set(sessionId, session);
    return session;
  }

  deleteSession(sessionId) {
    return this.sessions.delete(sessionId);
  }

  // ── Stream Management ───────────────────────────────────────────
  
  cancelStream(streamId) {
    const stream = this.activeStreams.get(streamId);
    if (stream) {
      stream.reader.cancel();
      this.activeStreams.delete(streamId);
      return true;
    }
    return false;
  }

  cancelAllStreams() {
    for (const [id, stream] of this.activeStreams) {
      stream.reader.cancel();
    }
    this.activeStreams.clear();
  }

  getActiveStreams() {
    return Array.from(this.activeStreams.entries()).map(([id, stream]) => ({
      id,
      sessionId: stream.sessionId,
      type: stream.type || 'chat',
      duration: Date.now() - stream.startTime,
    }));
  }

  // ── Event System ────────────────────────────────────────────────
  
  on(event, callback) {
    if (this.listeners[event]) {
      this.listeners[event].push(callback);
    }
    return () => this.off(event, callback);
  }

  off(event, callback) {
    if (this.listeners[event]) {
      const index = this.listeners[event].indexOf(callback);
      if (index !== -1) {
        this.listeners[event].splice(index, 1);
      }
    }
  }

  emit(event, data) {
    if (this.listeners[event]) {
      for (const callback of this.listeners[event]) {
        try {
          callback(data);
        } catch (error) {
          console.error(`[DSH] Event listener error (${event}):`, error);
        }
      }
    }
  }

  // ── Reconnection ────────────────────────────────────────────────
  
  setupReconnection() {
    // Superseded: reconnection is owned by the single status-poll loop
    // (_scheduleNextCheck backs off exponentially while disconnected and
    // snaps back to the base cadence on first success). The old listener
    // scheduled a SECOND overlapping check per failure, producing a ~1s
    // retry storm against a dead bridge.
  }

  // ── Helpers ─────────────────────────────────────────────────────
  
  getHeaders() {
    const headers = {};
    
    if (this.config.authToken) {
      headers['Authorization'] = `Bearer ${this.config.authToken}`;
    }
    
    return headers;
  }

  generateSessionId() {
    return `session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }

  /**
   * One stable session per browser session (regenerated on relaunch).
   * The old chat() default minted a NEW random id per message, so the
   * bridge never correlated turns — the model was permanently amnesiac.
   * Anything needing an isolated conversation still passes sessionId
   * explicitly (agents, one-shot tools), which is unchanged.
   */
  stableSessionId() {
    if (!this._stableSession) {
      this._stableSession = this.generateSessionId();
    }
    return this._stableSession;
  }

  /** Start a fresh conversation: the next chat() call gets a new session id
   * (the old thread's context is gone from the model's perspective). */
  rotateSession() {
    this._stableSession = this.generateSessionId();
    return this._stableSession;
  }

  /**
   * Per-tab sessions: each browser tab keeps its own conversation thread so
   * tabs don't bleed context into each other. Falls back to the stable
   * global session when no tabId is given (one-shot tools, agent tasks).
   */
  sessionForTab(tabId) {
    if (!tabId) return this.stableSessionId();
    if (!this._tabSessions) this._tabSessions = new Map();
    if (!this._tabSessions.has(tabId)) {
      this._tabSessions.set(tabId, this.generateSessionId());
      // Bound the map: 200 tabs is beyond any real session.
      if (this._tabSessions.size > 200) {
        const first = this._tabSessions.keys().next().value;
        this._tabSessions.delete(first);
      }
    }
    return this._tabSessions.get(tabId);
  }

  /** Forget one tab's thread (tab closed / /new in that tab). */
  forgetTabSession(tabId) {
    if (this._tabSessions) this._tabSessions.delete(tabId);
  }

  /** Full OpenAI-shaped message list for a chat call. Callers that have a
   * Chat module pass Chat.historyFor(); the just-sent text must NOT be
   * duplicated in messages (it goes as `text`), so drop a trailing user
   * entry equal to it. */
  conversationFrom(history, currentText) {
    const msgs = (history || []).filter(m => m && m.role && m.content);
    while (msgs.length && msgs[msgs.length - 1].role === "user" &&
           msgs[msgs.length - 1].content === currentText) {
      msgs.pop();
    }
    return msgs;
  }

  // ── Status ──────────────────────────────────────────────────────
  
  getStatus() {
    return {
      ...this.status,
      activeSessions: this.sessions.size,
      activeStreams: this.activeStreams.size,
      queuedMessages: this.messageQueue.length,
    };
  }

  // ── Cleanup ─────────────────────────────────────────────────────
  
  destroy() {
    this.stopStatusPolling();
    this.cancelAllStreams();
    this.sessions.clear();
    this.messageQueue = [];
    this.listeners = { status: [], message: [], agent: [], error: [], model: [] };
  }
}

// Export
window.DSHNative = DSHNative;
window.dshNative = new DSHNative();
