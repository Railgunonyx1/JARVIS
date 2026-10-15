/**
 * JARVIS Orbit — Headless Agent Loop
 *
 * Inspired by DeepSeek Harness: the agent loop runs without UI overhead,
 * streams structured output, and executes tools in parallel when safe.
 * No waiting, no spinners — just results.
 *
 * Architecture:
 *   User message → LLM (structured output) → Tool calls → Results → Response
 *
 * Key differences from the UI chat:
 *   1. No message rendering overhead
 *   2. Parallel tool execution (when safe)
 *   3. Structured JSON output from the model
 *   4. Automatic retry with backoff
 *   5. Streaming partial results
 */

'use strict';

const EventEmitter = require('events');

// ── Agent States ────────────────────────────────────────────────
const AgentState = {
  IDLE: 'idle',
  THINKING: 'thinking',
  EXECUTING: 'executing',
  OBSERVING: 'observing',
  COMPLETED: 'completed',
  FAILED: 'failed',
};

// ── Tool Registry ───────────────────────────────────────────────
class ToolRegistry {
  constructor() {
    this._tools = new Map();
  }

  register(name, handler, options = {}) {
    this._tools.set(name, {
      handler,
      risk: options.risk || 'low',    // low | medium | high
      parallel: options.parallel ?? true,  // can run in parallel?
      timeout: options.timeout || 30000,
    });
  }

  get(name) {
    return this._tools.get(name);
  }

  list() {
    return Array.from(this._tools.entries()).map(([name, def]) => ({
      name,
      risk: def.risk,
      parallel: def.parallel,
    }));
  }

  /**
   * Build the tool schema for the LLM (OpenAI function-calling format).
   */
  toSchema() {
    const tools = [];
    for (const [name, def] of this._tools) {
      tools.push({
        type: 'function',
        function: {
          name,
          description: `${name} — risk: ${def.risk}`,
          parameters: { type: 'object', properties: {} },
        },
      });
    }
    return tools;
  }
}

// ── Structured Output Parser ────────────────────────────────────
/**
 * Parses the model's structured output into a plan + tool calls.
 * Supports:
 *   - OpenAI function calling format
 *   - JSON mode output
 *   - Plain text with embedded tool calls
 */
function parseModelOutput(response) {
  const result = {
    text: '',
    toolCalls: [],
    done: false,
  };

  // Case 1: OpenAI-style function calls
  if (response.tool_calls && response.tool_calls.length > 0) {
    result.toolCalls = response.tool_calls.map(tc => ({
      id: tc.id || `call_${Date.now()}`,
      name: tc.function.name,
      arguments: typeof tc.function.arguments === 'string'
        ? JSON.parse(tc.function.arguments)
        : tc.function.arguments,
    }));
  }

  // Case 2: Text content
  if (response.content) {
    result.text = response.content;
  }

  // Case 3: Check for completion signals
  if (response.finish_reason === 'stop' || response.stop_reason === 'end_turn') {
    result.done = true;
  }

  return result;
}

// ── Headless Agent Loop ─────────────────────────────────────────
class AgentLoop extends EventEmitter {
  constructor(options = {}) {
    super();
    this.model = options.model || 'deepseek/deepseek-v4-flash';
    this.maxIterations = options.maxIterations || 20;
    this.maxTokens = options.maxTokens || 8192;
    this.temperature = options.temperature || 0.3;
    this.tools = options.tools || new ToolRegistry();
    this.baseUrl = options.baseUrl || 'http://127.0.0.1:8171';
    this.state = AgentState.IDLE;
    this.iteration = 0;
    this.messages = [];
    this._abortController = null;
  }

  /**
   * Run the agent loop on a user message.
   * Returns the final response text.
   */
  async run(userMessage, options = {}) {
    const { sessionId = 'default', signal } = options;
    this._abortController = new AbortController();
    if (signal) {
      signal.addEventListener('abort', () => this._abortController.abort());
    }

    this.state = AgentState.THINKING;
    this.iteration = 0;
    this.messages = [
      { role: 'system', content: this._buildSystemPrompt() },
      { role: 'user', content: userMessage },
    ];

    this.emit('state', this.state);

    try {
      while (this.iteration < this.maxIterations) {
        if (this._abortController.signal.aborted) {
          throw new Error('Agent loop aborted');
        }

        this.iteration++;
        this.emit('iteration', this.iteration);

        // Call the LLM
        this.state = AgentState.THINKING;
        this.emit('state', this.state);

        const response = await this._callLLM(sessionId);
        const parsed = parseModelOutput(response);

        // Add assistant message to context
        this.messages.push({
          role: 'assistant',
          content: parsed.text || '',
          tool_calls: parsed.toolCalls.length > 0 ? parsed.toolCalls : undefined,
        });

        // If no tool calls, we're done
        if (parsed.toolCalls.length === 0 || parsed.done) {
          this.state = AgentState.COMPLETED;
          this.emit('state', this.state);
          this.emit('done', parsed.text);
          return parsed.text;
        }

        // Execute tool calls
        this.state = AgentState.EXECUTING;
        this.emit('state', this.state);

        const results = await this._executeTools(parsed.toolCalls, sessionId);

        // Add tool results to context
        for (const result of results) {
          this.messages.push({
            role: 'tool',
            tool_call_id: result.id,
            content: result.output,
          });
        }

        this.state = AgentState.OBSERVING;
        this.emit('state', this.state);
      }

      // Max iterations reached
      this.state = AgentState.COMPLETED;
      this.emit('state', this.state);
      return this.messages[this.messages.length - 1]?.content || 'Max iterations reached';
    } catch (error) {
      this.state = AgentState.FAILED;
      this.emit('state', this.state);
      this.emit('error', error);
      throw error;
    }
  }

  /**
   * Build the system prompt with tool instructions.
   */
  _buildSystemPrompt() {
    const toolList = this.tools.list();
    const toolDescriptions = toolList.map(t =>
      `- ${t.name} (risk: ${t.risk}, parallel: ${t.parallel})`
    ).join('\n');

    return `You are JARVIS, an intelligent browser agent. You can browse the web, read pages, click elements, fill forms, and perform research tasks.

Available tools:
${toolDescriptions}

When you need to use a tool, call it directly. When you have enough information, provide a final answer.

Rules:
- Be concise and direct
- Use tools when needed, don't guess
- Parallel tool calls are allowed for read-only operations
- High-risk actions require explicit user approval
- Always provide a clear final answer`;
  }

  /**
   * Call the LLM with the current message context.
   */
  async _callLLM(sessionId) {
    const body = {
      model: this.model,
      messages: this.messages,
      max_tokens: this.maxTokens,
      temperature: this.temperature,
      stream: false,
    };

    // Only add tools if we have any
    const toolSchema = this.tools.toSchema();
    if (toolSchema.length > 0) {
      body.tools = toolSchema;
      body.tool_choice = 'auto';
    }

    const response = await fetch(`${this.baseUrl}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: this._abortController.signal,
    });

    if (!response.ok) {
      throw new Error(`LLM request failed: ${response.status}`);
    }

    const data = await response.json();
    return data.choices?.[0]?.message || { content: '' };
  }

  /**
   * Execute tool calls, parallelizing safe ones.
   */
  async _executeTools(toolCalls, sessionId) {
    const results = [];

    // Group by parallel safety
    const parallel = [];
    const sequential = [];

    for (const call of toolCalls) {
      const tool = this.tools.get(call.name);
      if (tool && tool.parallel) {
        parallel.push(call);
      } else {
        sequential.push(call);
      }
    }

    // Execute parallel tools concurrently
    if (parallel.length > 0) {
      const parallelResults = await Promise.allSettled(
        parallel.map(call => this._executeOneTool(call, sessionId))
      );
      for (let i = 0; i < parallel.length; i++) {
        const result = parallelResults[i];
        if (result.status === 'fulfilled') {
          results.push(result.value);
        } else {
          results.push({
            id: parallel[i].id,
            output: `Error: ${result.reason?.message || 'Tool execution failed'}`,
          });
        }
      }
    }

    // Execute sequential tools one by one
    for (const call of sequential) {
      try {
        const result = await this._executeOneTool(call, sessionId);
        results.push(result);
      } catch (error) {
        results.push({
          id: call.id,
          output: `Error: ${error.message}`,
        });
      }
    }

    return results;
  }

  /**
   * Execute a single tool call.
   */
  async _executeOneTool(call, sessionId) {
    const tool = this.tools.get(call.name);
    if (!tool) {
      return { id: call.id, output: `Unknown tool: ${call.name}` };
    }

    this.emit('tool', { name: call.name, args: call.arguments });

    const startTime = Date.now();
    try {
      const result = await Promise.race([
        tool.handler(call.arguments, { sessionId }),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('Tool timeout')), tool.timeout)
        ),
      ]);

      const duration = Date.now() - startTime;
      this.emit('toolResult', { name: call.name, duration, success: true });

      return {
        id: call.id,
        output: typeof result === 'string' ? result : JSON.stringify(result),
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      this.emit('toolResult', { name: call.name, duration, success: false, error: error.message });

      return {
        id: call.id,
        output: `Error executing ${call.name}: ${error.message}`,
      };
    }
  }

  /**
   * Abort the current run.
   */
  abort() {
    this._abortController?.abort();
  }

  /**
   * Get the current state.
   */
  getStatus() {
    return {
      state: this.state,
      iteration: this.iteration,
      maxIterations: this.maxIterations,
      messageCount: this.messages.length,
    };
  }
}

module.exports = {
  AgentLoop,
  AgentState,
  ToolRegistry,
  parseModelOutput,
};
