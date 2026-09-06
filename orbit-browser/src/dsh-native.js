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
    };
    
    this.init();
  }

  init() {
    // Start status polling
    this.startStatusPolling();
    
    // Setup reconnection
    this.setupReconnection();
    
    console.log('[DSH] Native integration initialized');
  }

  // ── Status Management ───────────────────────────────────────────
  
  startStatusPolling(intervalMs = 5000) {
    this.statusInterval = setInterval(() => {
      this.checkStatus();
    }, intervalMs);
    
    // Initial check
    this.checkStatus();
  }

  stopStatusPolling() {
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
      sessionId = this.generateSessionId(),
      page = null,
      stream = true,
    } = options;
    
    const payload = {
      text: message,
      session_id: sessionId,
      page,
    };
    
    if (stream) {
      return this.streamChat(payload, sessionId);
    } else {
      return this.sendChat(payload);
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
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        
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
      
      // Process stream
      const processStream = async () => {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            
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
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        
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
      
      const processStream = async () => {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            
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
    let reconnectTimer = null;
    
    this.on('status', (status) => {
      if (!status.connected && !reconnectTimer) {
        reconnectTimer = setTimeout(() => {
          console.log('[DSH] Attempting reconnection...');
          this.checkStatus();
          reconnectTimer = null;
        }, this.config.retryDelay);
      } else if (status.connected && reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    });
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
    this.listeners = { status: [], message: [], agent: [], error: [] };
  }
}

// Export
window.DSHNative = DSHNative;
window.dshNative = new DSHNative();
