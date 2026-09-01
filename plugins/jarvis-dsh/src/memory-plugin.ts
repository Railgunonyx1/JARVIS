/**
 * JARVIS Memory Plugin for DeepSeek Harness
 * 
 * Integrates JARVIS's memory system with DSH's session architecture.
 * Provides semantic search, identity memory, and context injection.
 * 
 * @module @jarvis/dsh-memory
 */

import { execSync } from 'child_process';
import { join } from 'path';

// ── Configuration ──────────────────────────────────────────────────────────

interface MemoryConfig {
  enabled: boolean;
  jarvisRoot: string;
  identity: {
    userName: string;
    userRole: string;
    project: string;
  };
  cacheSize: number;
}

// ── Memory Store ───────────────────────────────────────────────────────────

class MemoryStore {
  private config: MemoryConfig;
  private cache: Map<string, string> = new Map();

  constructor(config: MemoryConfig) {
    this.config = config;
  }

  async recall(query: string): Promise<string[]> {
    if (!this.config.enabled) return [];

    // Check cache first
    const cacheKey = query.toLowerCase().trim();
    if (this.cache.has(cacheKey)) {
      return [this.cache.get(cacheKey)!];
    }

    try {
      // Call JARVIS Python memory system
      const result = execSync(
        `python -c "from memory.controller import MemoryController; mc = MemoryController(); results = mc.retrieve('${query.replace(/'/g, '\\\\\\'')}'); print('\\n'.join([r.content for r in results]))"`,
        { 
          cwd: this.config.jarvisRoot, 
          encoding: 'utf-8', 
          timeout: 5000,
          env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        }
      );

      const memories = result.trim().split('\n').filter(Boolean);
      
      // Cache results
      if (memories.length > 0 && this.cache.size < this.config.cacheSize) {
        this.cache.set(cacheKey, memories[0]);
      }

      return memories;
    } catch (error) {
      console.error('[JARVIS Memory] Recall failed:', error);
      return [];
    }
  }

  async remember(key: string, value: string): Promise<void> {
    if (!this.config.enabled) return;

    try {
      // Store memory: pass dict as item, key as second arg
      // This creates MemoryItem(content=value, type='general') and sets id=key
      execSync(
        `python -c "from memory.controller import MemoryController; mc = MemoryController(); mc.store({'content': '${value.replace(/'/g, '\\\\\\'')}','type': 'general'}, '${key.replace(/'/g, '\\\\\\'')}')"`,
        { 
          cwd: this.config.jarvisRoot, 
          encoding: 'utf-8', 
          timeout: 5000,
          env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        }
      );

      // Update cache
      this.cache.set(key, value);
    } catch (error) {
      console.error('[JARVIS Memory] Remember failed:', error);
    }
  }

  async forget(key: string): Promise<void> {
    if (!this.config.enabled) return;

    try {
      // Delete memory by key
      execSync(
        `python -c "from memory.controller import MemoryController; mc = MemoryController(); mc.delete('${key.replace(/'/g, '\\\\\\'')}')"`,
        { 
          cwd: this.config.jarvisRoot, 
          encoding: 'utf-8', 
          timeout: 5000,
          env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
        }
      );

      // Remove from cache if present
      this.cache.delete(key);
    } catch (error) {
      console.error('[JARVIS Memory] Forget failed:', error);
    }
  }

  async update(key: string, value: string): Promise<void> {
    if (!this.config.enabled) return;

    try {
      // Update existing memory by deleting old and storing new
      // First try to delete the old entry
      try {
        execSync(
          `python -c "from memory.controller import MemoryController; mc = MemoryController(); mc.delete('${key.replace(/'/g, '\\\\\\'')}')"`,
          { 
            cwd: this.config.jarvisRoot, 
            encoding: 'utf-8', 
            timeout: 5000,
            env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
          }
        );
      } catch (e) {
        // If delete fails (key doesn't exist), that's OK - we'll just store new
        console.log('[JARVIS Memory] Update: key did not exist, storing new entry');
      }
      
      // Store the new value
      await this.remember(key, value);
    } catch (error) {
      console.error('[JARVIS Memory] Update failed:', error);
    }
  }

  getIdentityContext(): string {
    return `
User Information:
- Name: ${this.config.identity.userName}
- Role: ${this.config.identity.userRole}
- Project: ${this.config.identity.project}
    `.trim();
  }
}

// ── DSH Plugin ─────────────────────────────────────────────────────────────

export const memoryPlugin = {
  name: '@jarvis/dsh-memory',
  // Human-readable name for reference
  displayName: 'JARVIS Memory Module',
  description: 'Persistent memory across JARVIS sessions with recall/remember/forget/update capabilities',
  config: {
    enabled: true,
    jarvisRoot: process.cwd(),
    identity: {
      userName: 'Aayan',
      userRole: 'Software developer',
      project: 'JARVIS MK-X',
    },
    cacheSize: 1000,
  },
  async apply(ctx: any, config: MemoryConfig) {
    const store = new MemoryStore(config);

    // Inject identity context into system prompt
    ctx.on('system-prompt/assemble', (prompt: string) => {
      const identityContext = store.getIdentityContext();
      
      // Also recall and inject general memories (top 3) into context
      // This happens on every conversation start/turn
      try {
        const memories = store.recall('');
        const memoryText = memories.slice(0, 3)
          .map(m => `- ${m}`)
          .join('\n');
        const combinedContext = `${identityContext}\n\n${memoryText || '(no memories)'}`;
        return `${prompt}\n\n${combinedContext}`;
      } catch (error) {
        console.error('[JARVIS Memory] Recall failed during context injection:', error);
        return `${prompt}\n\n${identityContext}`;
      }
    });

    // Add memory tools to the tool registry
    ctx.tools.register({
      name: 'memory.recall',
      description: 'Recall memories related to a query. Memories are injected into context automatically.',
      inputSchema: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'Query to search memories' },
          limit: { type: 'number', description: 'Max memories to return (default: 5)' },
        },
        required: ['query'],
      },
      output: { type: 'string' },
      async execute(args: { query: string; limit?: number }) {
        const memories = await store.recall(args.query);
        const limit = args.limit || 5;
        return memories.slice(0, limit).join('\n');
      },
    });

    ctx.tools.register({
      name: 'memory.remember',
      description: 'Store a new memory. Will be automatically injected into future contexts.',
      inputSchema: {
        type: 'object',
        properties: {
          key: { type: 'string', description: 'Memory key/category (e.g., "project-config", "user-preference")' },
          value: { type: 'string', description: 'Memory content to store' },
        },
        required: ['key', 'value'],
      },
      output: { type: 'string' },
      async execute(args: { key: string; value: string }) {
        await store.remember(args.key, args.value);
        return `Stored memory: ${args.key} = ${args.value.substring(0, 50)}${args.value.length > 50 ? '...' : ''}`;
      },
    });

    ctx.tools.register({
      name: 'memory.forget',
      description: 'Remove a memory by key. The memory will no longer appear in context.',
      inputSchema: {
        type: 'object',
        properties: {
          key: { type: 'string', description: 'Memory key to remove' },
        },
        required: ['key'],
      },
      output: { type: 'string' },
      async execute(args: { key: string }) {
        await store.forget(args.key);
        return `Removed memory: ${args.key}`;
      },
    });

    ctx.tools.register({
      name: 'memory.update',
      description: 'Update/override an existing memory by key. The memory content will be replaced and injected into future contexts.',
      inputSchema: {
        type: 'object',
        properties: {
          key: { type: 'string', description: 'Memory key to update' },
          value: { type: 'string', description: 'New memory content' },
        },
        required: ['key', 'value'],
      },
      output: { type: 'string' },
      async execute(args: { key: string; value: string }) {
        await store.update(args.key, args.value);
        return `Updated memory: ${args.key} = ${args.value.substring(0, 50)}${args.value.length > 50 ? '...' : ''}`;
      },
    });

    // Add memory commands to the command registry
    // These allow DSH to invoke memory operations directly
    if (ctx.commands) {
      ctx.commands.register({
        name: 'memory',
        description: 'JARVIS Memory Module - manage persistent memories',
        subcommands: [
          {
            name: 'recall',
            description: 'Search memories by query',
            inputSchema: {
              type: 'object',
              properties: {
                query: { type: 'string', description: 'Search query' },
                limit: { type: 'number', description: 'Max results (default: 5)' },
              },
              required: ['query'],
            },
            async execute(args: { query: string; limit?: number }) {
              const memories = await store.recall(args.query);
              const limit = args.limit || 5;
              return memories.slice(0, limit).join('\n');
            },
          },
          {
            name: 'remember',
            description: 'Store a new memory (auto-injects into context)',
            inputSchema: {
              type: 'object',
              properties: {
                key: { type: 'string', description: 'Memory key/category' },
                value: { type: 'string', description: 'Memory content' },
              },
              required: ['key', 'value'],
            },
            async execute(args: { key: string; value: string }) {
              await store.remember(args.key, args.value);
              return `Stored memory: ${args.key} = ${args.value.substring(0, 50)}${args.value.length > 50 ? '...' : ''}`;
            },
          },
          {
            name: 'forget',
            description: 'Remove a memory by key',
            inputSchema: {
              type: 'object',
              properties: {
                key: { type: 'string', description: 'Memory key to remove' },
              },
              required: ['key'],
            },
            async execute(args: { key: string }) {
              await store.forget(args.key);
              return `Removed memory: ${args.key}`;
            },
          },
          {
            name: 'update',
            description: 'Update/override an existing memory',
            inputSchema: {
              type: 'object',
              properties: {
                key: { type: 'string', description: 'Memory key to update' },
                value: { type: 'string', description: 'New memory content' },
              },
              required: ['key', 'value'],
            },
            async execute(args: { key: string; value: string }) {
              await store.update(args.key, args.value);
              return `Updated memory: ${args.key} = ${args.value.substring(0, 50)}${args.value.length > 50 ? '...' : ''}`;
            },
          },
        ],
      });
    }

    console.log('[JARVIS Memory] Plugin registered - displayName:', memoryPlugin.displayName);
  },
};

export default memoryPlugin;