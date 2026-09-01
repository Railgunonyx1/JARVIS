/**
 * JARVIS Ollama Adapter for DeepSeek Harness
 * 
 * Registers Ollama as an LLM provider in DSH's runtime.
 * Supports the three-tier cascade: 1B → 1.5B → 3B
 * 
 * @module @jarvis/dsh-ollama-adapter
 */

import type { Context } from '@deepseek-ai/cordis';

// ── Types ──────────────────────────────────────────────────────────────────

interface OllamaConfig {
  host: string;
  cascade: {
    router: string;    // gemma3:1b
    worker: string;    // qwen2.5:1.5b
    heavy: string;     // qwen2.5:3b
  };
  maxLoadedModels: number;
  numParallel: number;
  flashAttention: boolean;
}

interface GenerateOptions {
  model: string;
  messages: Array<{ role: string; content: string }>;
  tools?: Array<{ type: string; function: { name: string; description: string; parameters: unknown } }>;
  stream?: boolean;
  temperature?: number;
  maxTokens?: number;
}

interface StreamChunk {
  type: 'delta' | 'finish';
  delta?: { content?: string; toolCalls?: unknown[] };
  finish?: { reason: string; usage?: { promptTokens: number; completionTokens: number } };
}

// ── Ollama Client ──────────────────────────────────────────────────────────

class OllamaClient {
  private host: string;

  constructor(host: string) {
    this.host = host;
  }

  async isRunning(): Promise<boolean> {
    try {
      const response = await fetch(`${this.host}/api/tags`);
      return response.ok;
    } catch {
      return false;
    }
  }

  async listModels(): Promise<string[]> {
    try {
      const response = await fetch(`${this.host}/api/tags`);
      const data = await response.json();
      return data.models?.map((m: { name: string }) => m.name) || [];
    } catch {
      return [];
    }
  }

  async generate(options: GenerateOptions): Promise<AsyncIterable<StreamChunk>> {
    const response = await fetch(`${this.host}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: options.model,
        messages: options.messages,
        tools: options.tools,
        stream: options.stream ?? true,
        options: {
          temperature: options.temperature,
          num_predict: options.maxTokens,
        },
      }),
    });

    if (!response.ok) {
      throw new Error(`Ollama error: ${response.status} ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    return this.parseSSEStream(reader);
  }

  private async *parseSSEStream(reader: ReadableStreamDefaultReader<Uint8Array>): AsyncIterable<StreamChunk> {
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            
            if (data.message?.content) {
              yield {
                type: 'delta',
                delta: { content: data.message.content },
              };
            }

            if (data.message?.tool_calls) {
              yield {
                type: 'delta',
                delta: { toolCalls: data.message.tool_calls },
              };
            }

            if (data.done) {
              yield {
                type: 'finish',
                finish: {
                  reason: 'stop',
                  usage: {
                    promptTokens: data.prompt_eval_count || 0,
                    completionTokens: data.eval_count || 0,
                  },
                },
              };
            }
          } catch {
            // Skip invalid JSON
          }
        }
      }
    }
  }
}

// ── Cascade Router ─────────────────────────────────────────────────────────

class CascadeRouter {
  private config: OllamaConfig['cascade'];
  private client: OllamaClient;

  constructor(config: OllamaConfig['cascade'], client: OllamaClient) {
    this.config = config;
    this.client = client;
  }

  async selectModel(prompt: string, hasTools: boolean): Promise<string> {
    // Simple heuristic routing
    const isComplex = prompt.length > 200 || 
                     prompt.includes('debug') || 
                     prompt.includes('refactor') ||
                     prompt.includes('analyze') ||
                     prompt.includes('plan');

    if (isComplex && hasTools) {
      return this.config.heavy;
    }

    if (hasTools || prompt.length > 50) {
      return this.config.worker;
    }

    return this.config.router;
  }

  async preloadCascade(): Promise<void> {
    // Load router model first (fast)
    console.log(`[JARVIS] Preloading router: ${this.config.router}`);
    // Ollama loads models on first request, so we make a dummy request
    await this.client.generate({
      model: this.config.router,
      messages: [{ role: 'user', content: '' }],
      stream: false,
    });
    console.log(`[JARVIS] Router ready: ${this.config.router}`);
  }
}

// ── DSH Adapter ────────────────────────────────────────────────────────────

export class OllamaAdapter {
  private client: OllamaClient;
  private router: CascadeRouter;
  private config: OllamaConfig;

  constructor(config: OllamaConfig) {
    this.config = config;
    this.client = new OllamaClient(config.host);
    this.router = new CascadeRouter(config.cascade, this.client);
  }

  async initialize(): Promise<void> {
    const isRunning = await this.client.isRunning();
    if (!isRunning) {
      console.warn('[JARVIS] Ollama not running. Starting...');
      // Try to start Ollama
      try {
        const { execSync } = await import('child_process');
        execSync('ollama serve &', { stdio: 'ignore' });
        await new Promise(resolve => setTimeout(resolve, 2000));
      } catch (error) {
        console.error('[JARVIS] Failed to start Ollama:', error);
      }
    }

    await this.router.preloadCascade();
  }

  async stream(options: GenerateOptions): AsyncIterable<StreamChunk> {
    const model = await this.router.selectModel(
      options.messages[options.messages.length - 1]?.content || '',
      (options.tools?.length || 0) > 0
    );

    console.log(`[JARVIS] Using model: ${model}`);

    return this.client.generate({
      ...options,
      model,
    });
  }

  async listModels(): Promise<string[]> {
    return this.client.listModels();
  }

  getClient(): OllamaClient {
    return this.client;
  }

  getRouter(): CascadeRouter {
    return this.router;
  }
}

// ── Cordis Plugin ──────────────────────────────────────────────────────────

export const ollamaPlugin = {
  name: '@jarvis/dsh-ollama',
  config: {
    host: 'http://127.0.0.1:11434',
    cascade: {
      router: 'gemma3:1b',
      worker: 'qwen2.5:1.5b',
      heavy: 'qwen2.5:3b',
    },
    maxLoadedModels: 2,
    numParallel: 2,
    flashAttention: true,
  },
  async apply(ctx: Context, config: OllamaConfig) {
    const adapter = new OllamaAdapter(config);
    await adapter.initialize();

    // Register with DSH LLM runtime
    ctx.llm.registerAdapter(['ollama'], {
      stream: (options: GenerateOptions) => adapter.stream(options),
      listModels: () => adapter.listModels(),
    });

    console.log('[JARVIS] Ollama adapter registered with DSH');
  },
};

export default ollamaPlugin;
