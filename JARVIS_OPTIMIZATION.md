# JARVIS MK-X — Ollama Optimization Guide

Hardware: MX130 2GB VRAM | 7GB RAM | Intel 8-core | Windows 11

## 1. Ollama Environment Variables (set in JARVIS.bat)

```batch
:: ── GPU Memory Optimization ──
:: Force Ollama to use CUDA (if available) with aggressive VRAM usage
set OLLAMA_GPU_LAYERS=999          :: Offload all layers to GPU if possible
set CUDA_VISIBLE_DEVICES=0         :: Use first GPU

:: ── CPU Optimization ──
:: Match physical core count (not hyperthreads)
set OLLAMA_NUM_PARALLEL=2          :: Max concurrent requests (keep low for 7GB RAM)
set OLLAMA_MAX_LOADED_MODELS=1     :: Only keep 1 model in memory at a time
set OLLAMA_FLASH_ATTENTION=1       :: Enable flash attention (faster, less memory)

:: ── Context Window ──
:: Smaller context = faster inference, less memory
:: Default is 2048; set based on model needs
set OLLAMA_CONTEXT_LENGTH=2048     :: Reduce from default for speed

:: ── Server Tuning ──
set OLLAMA_HOST=127.0.0.1:11434    :: Explicit bind (avoid DNS lookup)
set OLLAMA_KEEP_ALIVE=5m           :: Unload idle models after 5 min (saves RAM)
set OLLAMA_MAX_QUEUE=2             :: Limit queued requests

:: ── Cache ──
set OLLAMA_CACHE_DIR=C:\ollama_cache  :: Use fast SSD for cache if available
```

## 2. Model Selection Strategy

| Use Case | Model | Size | When |
|----------|-------|------|------|
| Quick reply, identity, status | qwen2.5:0.5b | 398MB | INSTANT/CONVERSATIONAL |
| Normal coding, memory queries | qwen2.5:1.5b | 986MB | SIMPLE tasks |
| Complex coding, multi-step | qwen2.5:3b | 1.9GB | COMPLEX tasks |
| Heavy reasoning (if needed) | qwen3:4b | 2.5GB | EMERGENCY only |

**Key insight:** With 7GB RAM and 2GB VRAM:
- qwen2.5:0.5b = fully in VRAM (fastest)
- qwen2.5:1.5b = partially in VRAM (fast)
- qwen2.5:3b = mostly CPU (slower but fits)
- qwen3:4b = CPU only (slowest)

## 3. Ollama API Tuning

When calling Ollama, use these parameters:

```python
# Fast responses (identity, status, simple questions)
{
    "model": "qwen2.5:1.5b",
    "options": {
        "num_ctx": 1024,        # Minimal context for speed
        "temperature": 0.3,     # Lower = faster, more focused
        "num_predict": 256,     # Limit response length
        "top_k": 20,           # Reduced search space
        "top_p": 0.8,          # Narrower sampling
        "repeat_penalty": 1.0   # No repetition penalty for speed
    }
}

# Normal coding tasks
{
    "model": "qwen2.5:3b",
    "options": {
        "num_ctx": 4096,        # Enough for tool calls
        "temperature": 0.4,
        "num_predict": 1024,
        "top_k": 30,
        "top_p": 0.9
    }
}
```

## 4. JARVIS.bat Startup Optimizations

```batch
@echo off
title JARVIS MK-X

:: ── Pre-allocate memory ──
set PYTHONDONTWRITEBYTECODE=1
set PYTHONUNBUFFERED=1

:: ── Start Ollama with optimized settings ──
start /B "" "C:\Users\aayan\AppData\Local\Programs\Ollama\ollama.exe" serve
timeout /t 2 /nobreak >nul

:: ── Pre-pull models (run once) ──
:: "C:\Users\aayan\AppData\Local\Programs\Ollama\ollama.exe" pull qwen2.5:0.5b
:: "C:\Users\aayan\AppData\Local\Programs\Ollama\ollama.exe" pull qwen2.5:1.5b
:: "C:\Users\aayan\AppData\Local\Programs\Ollama\ollama.exe" pull qwen2.5:3b

:: ── Warm up model (keeps it in memory) ──
start /B "" curl -s http://localhost:11434/api/chat -d "{\"model\":\"qwen2.5:1.5b\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"options\":{\"num_predict\":1}}"

:: ── Launch JARVIS ──
python -m cli %*
```

## 5. Model Preloading (Biggest Latency Win)

First request to Ollama is slow (model loading). Solutions:

### Option A: Keep model loaded
```bash
# In Ollama config (Modelfile):
PARAMETER keep_alive 30m
```

### Option B: Background warm-up in JARVIS.bat
```batch
:: Warm up all cascade models on startup
start /B "" curl -s http://localhost:11434/api/generate -d "{\"model\":\"qwen2.5:1.5b\",\"prompt\":\"hi\",\"options\":{\"num_predict\":1}}"
start /B "" curl -s http://localhost:11434/api/generate -d "{\"model\":\"qwen2.5:3b\",\"prompt\":\"hi\",\"options\":{\"num_predict\":1}}"
```

### Option C: Use Modelfiles with optimized settings
Create `Modelfile.qwen-fast`:
```
FROM qwen2.5:1.5b
PARAMETER num_ctx 1024
PARAMETER num_predict 256
PARAMETER temperature 0.3
PARAMETER top_k 20
PARAMETER top_p 0.8
PARAMETER repeat_penalty 1.0
PARAMETER num_thread 6
```

Then: `ollama create qwen-fast -f Modelfile.qwen-fast`

## 6. CPU Thread Optimization

Intel 8-core = 8 physical cores, 16 threads with hyperthreading.

```bash
# Optimal thread count for inference (not training)
# Rule: use physical cores, not hyperthreads
set OLLAMA_NUM_THREAD=8

# Or in API call:
{"options": {"num_thread": 8}}
```

For your cascade:
- 1.5B model: `num_thread=6` (faster, less context)
- 3B model: `num_thread=8` (needs all cores)

## 7. Context Window Optimization

Smaller context = faster inference. Strategy:

| Task Type | Context Size | Why |
|-----------|-------------|-----|
| INSTANT reply | 512 | Just the question |
| SIMPLE question | 1024 | Question + brief memory |
| Normal coding | 4096 | Enough for tool calls |
| Complex multi-step | 8192 | Full conversation |

In JARVIS, this maps to the `context_level` in the intent classifier.

## 8. Quantization Impact

| Quant | Size (1.5B) | Speed | Quality |
|-------|-------------|-------|---------|
| Q8_0 | 1.6GB | Slow | Best |
| Q6_K | 1.3GB | Medium | Great |
| Q4_K_M | 986MB | Fast | Good |
| Q2_K | 600MB | Fastest | Reduced |

Ollama uses Q4_K_M by default — this is already optimal for your hardware.

## 9. Response Streaming

Enable streaming for perceived speed improvement:

```python
# Stream response tokens as they arrive
response = ollama.chat(
    model='qwen2.5:1.5b',
    messages=messages,
    stream=True,  # Key: stream tokens
    options={'num_ctx': 1024}
)
```

JARVIS already does this via `on_chunk` callbacks. Make sure it's enabled.

## 10. Memory Management

With 7GB RAM total:
- OS uses ~2GB
- Python/JARVIS uses ~500MB
- Available for Ollama: ~4.5GB

Optimal allocation:
- 1 model loaded at a time (`OLLAMA_MAX_LOADED_MODELS=1`)
- 5-minute idle unload (`OLLAMA_KEEP_ALIVE=5m`)
- Monitor with: `GET /api/ps` endpoint

## Quick Wins (Do These First)

1. **Set `OLLAMA_FLASH_ATTENTION=1`** — 20-30% speed boost
2. **Set `OLLAMA_NUM_THREAD=8`** — matches your CPU
3. **Set `OLLAMA_CONTEXT_LENGTH=2048`** — reduce from default 32K
4. **Set `OLLAMA_MAX_LOADED_MODELS=1`** — prevent memory pressure
5. **Pre-load models in JARVIS.bat** — eliminate cold start latency
6. **Use streaming** — perceived speed improvement
7. **Reduce context per task** — INSTANT=512, SIMPLE=1024, COMPLEX=4096
