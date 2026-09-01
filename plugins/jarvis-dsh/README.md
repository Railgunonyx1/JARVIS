# JARVIS MK-X — DeepSeek Harness Integration

This plugin bridges JARVIS's Python capabilities into DeepSeek Harness's Cordis plugin system.

## Architecture

```
DSH Runtime (Node.js/Cordis)
    │
    ├── JARVIS Personality Plugin
    │       └── System prompt, identity, communication style
    │
    ├── JARVIS Ollama Adapter
    │       └── Three-tier cascade: 1B → 1.5B → 3B
    │
    ├── JARVIS Memory Plugin
    │       └── SQLite + JSON memory system
    │
    └── JARVIS MCP Server
            └── Tools: filesystem, shell, search, memory, verification
```

## Quick Start

### Option 1: DSH Mode (Recommended)

```bash
# Install DSH
npm install -g @deepseek-ai/dsh

# Run setup
cd plugins/jarvis-dsh
./setup.sh

# Launch JARVIS via DSH
dsh --profile jarvis
# or
launch-jarvis-dsh.bat  # Windows
./launch-jarvis-dsh.sh  # Linux/Mac
```

### Option 2: Standalone Mode

```bash
# Launch JARVIS without DSH
JARVIS.bat  # Windows
python -m cli.main  # Linux/Mac
```

## Components

### 1. Ollama Adapter (`ollama-adapter.ts`)

Registers Ollama as an LLM provider with three-tier cascade:

| Tier | Model | Use Case |
|------|-------|----------|
| Router | gemma3:1b | Quick responses, simple queries |
| Worker | qwen2.5:1.5b | Tool-using tasks |
| Heavy | qwen2.5:3b | Complex reasoning |

### 2. Memory Plugin (`memory-plugin.ts`)

Integrates JARVIS's memory system with DSH sessions:

- **Recall**: Search memories by query
- **Remember**: Store new memories
- **Identity**: User name, role, project context
- **Cache**: In-memory cache for fast access

### 3. Personality Plugin (`personality-plugin.ts`)

Configures JARVIS's identity and communication style:

- **Identity**: JARVIS MK-X, created by Aayan
- **Traits**: Precise, helpful, proactive, concise
- **Expertise**: Software engineering, AI/ML, DevOps
- **Style**: Structured responses with code blocks

### 4. MCP Server (`jarvis-mcp-server.py`)

Exposes JARVIS tools via MCP protocol:

- `filesystem.read` / `filesystem.write` / `filesystem.search`
- `shell.execute`
- `memory.recall` / `memory.remember`
- `web.search`
- `verification.run_tests` / `verification.run_lint`

## Configuration

### DSH Profile (`jarvis.profile.yml`)

```yaml
# Identity
- id: jarvis-personality
  name: '@jarvis/dsh-personality'

# LLM Provider
- id: jarvis-ollama
  name: '@jarvis/dsh-ollama'

# Memory
- id: jarvis-memory
  name: '@jarvis/dsh-memory'

# Tools (via MCP)
- id: jarvis-tools-mcp
  name: '@deepseek-ai/dsh-mcp-client'
```

### JARVIS Config (`config/jarvis.yml`)

```yaml
jarvis:
  name: JARVIS MK-X
  
models:
  primary: ollama
  cascade:
    router: gemma3:1b
    worker: qwen2.5:1.5b
    heavy: qwen2.5:3b

memory:
  enabled: true
  identity:
    userName: Aayan
    userRole: Software developer
    project: JARVIS MK-X

verification:
  enabled: true
  tests: true
  lint: true
```

## Development

### Building

```bash
cd plugins/jarvis-dsh
npm install
npm run build
```

### Testing

```bash
npm test
```

### Watch Mode

```bash
npm run dev
```

## Migration Status

| Component | Status | Notes |
|-----------|--------|-------|
| Ollama Adapter | ✅ Complete | Three-tier cascade working |
| Memory Plugin | ✅ Complete | SQLite + JSON integration |
| Personality Plugin | ✅ Complete | System prompt configured |
| MCP Server | ✅ Complete | All tools exposed |
| DSH Profile | ✅ Complete | Configuration ready |
| DSH Runtime | 🔄 Pending | Waiting for Windows support |
| End-to-End Test | 📋 Planned | After DSH runtime available |

## Troubleshooting

### Ollama Not Running

```bash
# Start Ollama
ollama serve

# Check status
curl http://127.0.0.1:11434/api/tags
```

### DSH Not Found

```bash
# Install DSH
npm install -g @deepseek-ai/dsh

# Verify
dsh --version
```

### Memory Not Working

```bash
# Check JARVIS memory
python -c "from memory.controller import MemoryController; mc = MemoryController(); print(mc.retrieve('Aayan'))"
```

## Resources

- [DSH Repository](https://github.com/deepseek-ai/deepseek-harness)
- [DSH Documentation](https://github.com/deepseek-ai/deepseek-harness/blob/master/AGENTS.md)
- [Cordis Tutorial](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cordis-tutorial/index.md)
- [JARVIS Repository](https://github.com/Railgunonyx1/JARVIS1)
- [MCP Protocol](https://modelcontextprotocol.io/)
