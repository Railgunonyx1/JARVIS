/**
 * JARVIS MK-X — DeepSeek Harness Plugin
 * 
 * Bridges JARVIS's Python capabilities into DSH's Cordis plugin system.
 * Provides model gateway, memory bridge, tool execution, and verification.
 * 
 * @module @jarvis/dsh-plugin
 */

import { execSync, spawn } from 'child_process';
import { join, resolve } from 'path';
import { existsSync, readFileSync } from 'fs';

// ── Configuration ──────────────────────────────────────────────────────────

interface JarvisConfig {
  name: string;
  jarvisRoot: string;
  models: {
    primary: string;
    cascade: {
      router: string;
      worker: string;
      heavy: string;
    };
  };
  memory: {
    enabled: boolean;
    backend: string;
  };
  verification: {
    enabled: boolean;
    tests: boolean;
    lint: boolean;
  };
}

const DEFAULT_CONFIG: JarvisConfig = {
  name: 'JARVIS MK-X',
  jarvisRoot: resolve(__dirname, '../../'),
  models: {
    primary: 'ollama',
    cascade: {
      router: 'gemma3:1b',
      worker: 'qwen2.5:1.5b',
      heavy: 'qwen2.5:3b',
    },
  },
  memory: {
    enabled: true,
    backend: 'sqlite',
  },
  verification: {
    enabled: true,
    tests: true,
    lint: true,
  },
};

// ── Model Gateway ──────────────────────────────────────────────────────────

class ModelGateway {
  private config: JarvisConfig['models'];
  private ollamaHost: string;

  constructor(config: JarvisConfig['models']) {
    this.config = config;
    this.ollamaHost = process.env.OLLAMA_HOST || 'http://127.0.0.1:11434';
  }

  async isOllamaRunning(): Promise<boolean> {
    try {
      const response = await fetch(`${this.ollamaHost}/api/tags`);
      return response.ok;
    } catch {
      return false;
    }
  }

  async loadModel(model: string): Promise<void> {
    console.log(`[JARVIS] Loading model: ${model}`);
    try {
      await fetch(`${this.ollamaHost}/api/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model, prompt: '', stream: false }),
      });
      console.log(`[JARVIS] Model ${model} loaded`);
    } catch (error) {
      console.error(`[JARVIS] Failed to load model ${model}:`, error);
    }
  }

  async preloadCascade(): Promise<void> {
    console.log('[JARVIS] Preloading model cascade...');
    // Load 1B first (fast), defer 3B
    await this.loadModel(this.config.cascade.router);
    console.log(`[JARVIS] Router model ${this.config.cascade.router} ready`);
  }

  async ensureWorkerModel(): Promise<void> {
    // Lazy-load worker model on first real task
    await this.loadModel(this.config.cascade.worker);
    console.log(`[JARVIS] Worker model ${this.config.cascade.worker} ready`);
  }
}

// ── Memory Bridge ──────────────────────────────────────────────────────────

class MemoryBridge {
  private config: JarvisConfig['memory'];
  private jarvisRoot: string;

  constructor(config: JarvisConfig['memory'], jarvisRoot: string) {
    this.config = config;
    this.jarvisRoot = jarvisRoot;
  }

  async recall(query: string): Promise<string> {
    if (!this.config.enabled) return '';
    
    try {
      // Call JARVIS Python memory system
      const result = execSync(
        `python -c "from memory.controller import MemoryController; mc = MemoryController(); print(mc.retrieve('${query.replace(/'/g, "\\'")}'))"`,
        { cwd: this.jarvisRoot, encoding: 'utf-8', timeout: 5000 }
      );
      return result.trim();
    } catch (error) {
      console.error('[JARVIS] Memory recall failed:', error);
      return '';
    }
  }

  async remember(key: string, value: string): Promise<void> {
    if (!this.config.enabled) return;
    
    try {
      execSync(
        `python -c "from memory.controller import MemoryController; mc = MemoryController(); mc.store('${key}', '${value.replace(/'/g, "\\'")}')  "`,
        { cwd: this.jarvisRoot, encoding: 'utf-8', timeout: 5000 }
      );
    } catch (error) {
      console.error('[JARVIS] Memory store failed:', error);
    }
  }
}

// ── Tool Bridge ────────────────────────────────────────────────────────────

class ToolBridge {
  private jarvisRoot: string;

  constructor(jarvisRoot: string) {
    this.jarvisRoot = jarvisRoot;
  }

  async executeTool(toolName: string, args: Record<string, unknown>): Promise<string> {
    try {
      // Spawn JARVIS Python tool execution
      const child = spawn('python', [
        '-c',
        `from core.agent.tools import ToolRegistry; tr = ToolRegistry(); print(tr.execute('${toolName}', ${JSON.stringify(args)}))`
      ], {
        cwd: this.jarvisRoot,
        stdio: ['pipe', 'pipe', 'pipe'],
        timeout: 30000,
      });

      return await new Promise((resolve, reject) => {
        let stdout = '';
        let stderr = '';
        
        child.stdout.on('data', (data) => { stdout += data; });
        child.stderr.on('data', (data) => { stderr += data; });
        
        child.on('close', (code) => {
          if (code === 0) {
            resolve(stdout.trim());
          } else {
            reject(new Error(stderr || `Tool ${toolName} failed with code ${code}`));
          }
        });
        
        child.on('error', reject);
      });
    } catch (error) {
      throw new Error(`Tool ${toolName} execution failed: ${error}`);
    }
  }
}

// ── Verification Bridge ────────────────────────────────────────────────────

class VerificationBridge {
  private jarvisRoot: string;
  private config: JarvisConfig['verification'];

  constructor(config: JarvisConfig['verification'], jarvisRoot: string) {
    this.config = config;
    this.jarvisRoot = jarvisRoot;
  }

  async runTests(): Promise<string> {
    if (!this.config.tests) return 'Tests disabled';
    
    try {
      const result = execSync('python -m pytest tests/ -x -q', {
        cwd: this.jarvisRoot,
        encoding: 'utf-8',
        timeout: 60000,
      });
      return result.trim();
    } catch (error) {
      throw new Error(`Tests failed: ${error}`);
    }
  }

  async runLint(): Promise<string> {
    if (!this.config.lint) return 'Lint disabled';
    
    try {
      const result = execSync('python -m ruff check .', {
        cwd: this.jarvisRoot,
        encoding: 'utf-8',
        timeout: 30000,
      });
      return result.trim();
    } catch (error) {
      throw new Error(`Lint failed: ${error}`);
    }
  }

  async verify(): Promise<{ passed: boolean; results: string[] }> {
    const results: string[] = [];
    let passed = true;

    try {
      results.push('Tests: ' + await this.runTests());
    } catch (error) {
      results.push('Tests FAILED: ' + (error as Error).message);
      passed = false;
    }

    try {
      results.push('Lint: ' + await this.runLint());
    } catch (error) {
      results.push('Lint FAILED: ' + (error as Error).message);
      passed = false;
    }

    return { passed, results };
  }
}

// ── JARVIS Plugin ──────────────────────────────────────────────────────────

export class JarvisPlugin {
  private config: JarvisConfig;
  private modelGateway: ModelGateway;
  private memoryBridge: MemoryBridge;
  private toolBridge: ToolBridge;
  private verificationBridge: VerificationBridge;

  constructor(config: Partial<JarvisConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.modelGateway = new ModelGateway(this.config.models);
    this.memoryBridge = new MemoryBridge(this.config.memory, this.config.jarvisRoot);
    this.toolBridge = new ToolBridge(this.config.jarvisRoot);
    this.verificationBridge = new VerificationBridge(this.config.verification, this.config.jarvisRoot);
  }

  async initialize(): Promise<void> {
    console.log(`[JARVIS] Initializing ${this.config.name}...`);
    
    // Check Ollama status
    const ollamaRunning = await this.modelGateway.isOllamaRunning();
    if (!ollamaRunning) {
      console.warn('[JARVIS] Ollama not running. Starting...');
      // Try to start Ollama
      try {
        execSync('ollama serve &', { stdio: 'ignore' });
        await new Promise(resolve => setTimeout(resolve, 2000));
      } catch (error) {
        console.error('[JARVIS] Failed to start Ollama:', error);
      }
    }

    // Preload model cascade
    await this.modelGateway.preloadCascade();
    
    console.log(`[JARVIS] ${this.config.name} initialized`);
  }

  async handleMessage(message: string): Promise<string> {
    // Check memory first
    const memoryContext = await this.memoryBridge.recall(message);
    
    // Route to appropriate model based on complexity
    const model = this.selectModel(message);
    
    // Execute via JARVIS Python agent
    try {
      const result = await this.toolBridge.executeTool('agent.chat', {
        message,
        model,
        memory: memoryContext,
      });
      return result;
    } catch (error) {
      return `Error: ${error}`;
    }
  }

  private selectModel(message: string): string {
    // Simple routing logic
    const isComplex = message.length > 100 || 
                     message.includes('debug') || 
                     message.includes('refactor') ||
                     message.includes('analyze');
    
    if (isComplex) {
      return this.config.models.cascade.heavy;
    }
    return this.config.models.cascade.worker;
  }

  getGateway(): ModelGateway {
    return this.modelGateway;
  }

  getMemory(): MemoryBridge {
    return this.memoryBridge;
  }

  getTools(): ToolBridge {
    return this.toolBridge;
  }

  getVerification(): VerificationBridge {
    return this.verificationBridge;
  }
}

// ── Export ─────────────────────────────────────────────────────────────────

export default JarvisPlugin;
export { ModelGateway, MemoryBridge, ToolBridge, VerificationBridge };
export type { JarvisConfig };
