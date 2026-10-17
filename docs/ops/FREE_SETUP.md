# JARVIS MK-X — Free Setup Guide

Run JARVIS 100% free. No credit card required for any provider.

## Quick Setup

```bash
python scripts/setup_free.py
```

This walks you through getting free API keys and writes them to `config/.env`.

## Free Providers (sorted by quality)

| Provider | Free Tier | Best For | Sign Up |
|----------|-----------|----------|---------|
| **Groq** | 14,400 req/day | Fastest inference | [console.groq.com](https://console.groq.com/keys) |
| **Google Gemini** | 1,500 req/day | Best reasoning | [aistudio.google.com](https://aistudio.google.com/apikey) |
| **Cerebras** | 1,000 req/day | Ultra-fast | [cloud.cerebras.ai](https://cloud.cerebras.ai/) |
| **DeepSeek** | Cheap ($0.14/M tokens) | Best coding | [platform.deepseek.com](https://platform.deepseek.com/api_keys) |
| **OpenRouter** | Free models | Model variety | [openrouter.ai](https://openrouter.ai/keys) |
| **Mistral** | 500 req/day | Balanced | [console.mistral.ai](https://console.mistral.ai/api-keys/) |
| **HuggingFace** | Rate-limited | Many models | [huggingface.co](https://huggingface.co/settings/tokens) |
| **Ollama** | Unlimited | Local/offline | [ollama.com](https://ollama.com/download) |

## Recommended Combos

### Best Free Setup (recommended)
**Groq + Gemini + Ollama**
- Groq: fast responses for simple tasks
- Gemini: smart reasoning for complex tasks  
- Ollama: offline fallback (unlimited)

### Maximum Free Volume
**Groq + Gemini + Cerebras + OpenRouter + Ollama**
- ~20,000+ free requests/day combined

### Fully Local (no API keys needed)
**Ollama only**
```bash
# Install Ollama
winget install Ollama.Ollama  # Windows
# or: brew install ollama     # macOS

# Pull a coding model
ollama pull qwen2.5-coder:14b

# Run JARVIS (uses local Ollama automatically)
python -m cli
```

## Manual Setup

If you prefer manual setup, add keys to `config/.env`:

```env
GROQ_API_KEY=gsk_your_key_here
GEMINI_API_KEY=AIza_your_key_here
CEREBRAS_API_KEY=csk_your_key_here
OPENROUTER_API_KEY=sk-or_your_key_here
```

## How It Works

JARVIS's `ProviderRouter` tries providers in this order:
1. Gemini → 2. Groq → 3. Cerebras → 4. DeepSeek → 5. OpenRouter → ...

When one hits a rate limit or fails, it automatically falls back to the next.
With 3+ providers configured, you'll never run out of free quota for normal use.
