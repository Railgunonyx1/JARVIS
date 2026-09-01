import { describe, it, expect, vi, beforeEach } from 'vitest';
import { JarvisPlugin } from '../index.js';

describe('JarvisPlugin', () => {
  let plugin: JarvisPlugin;

  beforeEach(() => {
    plugin = new JarvisPlugin({
      jarvisRoot: '/tmp/test-jarvis',
    });
  });

  describe('initialization', () => {
    it('should create plugin with default config', () => {
      expect(plugin).toBeDefined();
      expect(plugin.getGateway()).toBeDefined();
      expect(plugin.getMemory()).toBeDefined();
      expect(plugin.getTools()).toBeDefined();
      expect(plugin.getVerification()).toBeDefined();
    });

    it('should create plugin with custom config', () => {
      const customPlugin = new JarvisPlugin({
        name: 'Custom JARVIS',
        models: {
          primary: 'ollama',
          cascade: {
            router: 'custom:1b',
            worker: 'custom:3b',
            heavy: 'custom:7b',
          },
        },
      });

      expect(customPlugin).toBeDefined();
    });
  });

  describe('model gateway', () => {
    it('should check Ollama status', async () => {
      const gateway = plugin.getGateway();
      // Mock fetch
      global.fetch = vi.fn().mockResolvedValue({ ok: true });
      
      const isRunning = await gateway.isOllamaRunning();
      expect(isRunning).toBe(true);
    });

    it('should handle Ollama not running', async () => {
      const gateway = plugin.getGateway();
      global.fetch = vi.fn().mockRejectedValue(new Error('Connection refused'));
      
      const isRunning = await gateway.isOllamaRunning();
      expect(isRunning).toBe(false);
    });
  });

  describe('memory bridge', () => {
    it('should recall memory', async () => {
      const memory = plugin.getMemory();
      // Mock execSync
      vi.mock('child_process', () => ({
        execSync: vi.fn().mockReturnValue('Aayan'),
      }));

      const result = await memory.recall('what is my name');
      expect(result).toBe('Aayan');
    });

    it('should handle memory recall failure', async () => {
      const memory = plugin.getMemory();
      vi.mock('child_process', () => ({
        execSync: vi.fn().mockImplementation(() => {
          throw new Error('Memory not found');
        }),
      }));

      const result = await memory.recall('unknown');
      expect(result).toBe('');
    });
  });

  describe('tool bridge', () => {
    it('should execute tool', async () => {
      const tools = plugin.getTools();
      vi.mock('child_process', () => ({
        spawn: vi.fn().mockReturnValue({
          stdout: { on: vi.fn().mockImplementation((_, cb) => cb('result')) },
          stderr: { on: vi.fn() },
          on: vi.fn().mockImplementation((event, cb) => {
            if (event === 'close') cb(0);
          }),
        }),
      }));

      const result = await tools.executeTool('filesystem.read', { path: '/test' });
      expect(result).toBe('result');
    });
  });

  describe('verification bridge', () => {
    it('should run tests', async () => {
      const verification = plugin.getVerification();
      vi.mock('child_process', () => ({
        execSync: vi.fn().mockReturnValue('10 passed'),
      }));

      const result = await verification.runTests();
      expect(result).toBe('10 passed');
    });

    it('should run lint', async () => {
      const verification = plugin.getVerification();
      vi.mock('child_process', () => ({
        execSync: vi.fn().mockReturnValue('All checks passed'),
      }));

      const result = await verification.runLint();
      expect(result).toBe('All checks passed');
    });
  });
});
