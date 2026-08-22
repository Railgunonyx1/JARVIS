"""Shared utilities for 1B model operations.

Handles model auto-pull, HTTP communication, and timeout management.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request

logger = logging.getLogger("jarvis.memory.llm")

# Default model for memory enhancements
MODEL_NAME = os.environ.get("JARVIS_MEMORY_MODEL", "qwen2.5:1.5b")

# Timeouts (must be fast — these are on the hot path)
REFORMULATE_TIMEOUT = 3.0
RERANK_TIMEOUT = 2.0
CONDENSE_TIMEOUT = 3.0

# Track whether we've verified the model exists
_model_verified = False


def ensure_model(model: str = MODEL_NAME) -> bool:
    """Ensure the model is available in Ollama. Auto-pull if missing.

    Returns True if the model is ready, False if unavailable.
    """
    global _model_verified
    if _model_verified:
        return True

    try:
        # Check if model exists
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        models = [m.get("name", "") for m in data.get("models", [])]

        # Check exact match or prefix match (e.g., "qwen2.5:1.5b" matches "qwen2.5:1.5b-instruct")
        if any(model in m or m in model for m in models):
            _model_verified = True
            return True

        # Model not found — auto-pull
        logger.info("Auto-pulling %s for memory enhancements...", model)
        pull_req = urllib.request.Request(
            "http://127.0.0.1:11434/api/pull",
            data=json.dumps({"name": model}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(pull_req, timeout=120) as resp:
            # Stream the pull progress
            for line in resp:
                try:
                    status = json.loads(line)
                    if "status" in status:
                        logger.debug("Pull: %s", status["status"])
                except json.JSONDecodeError:
                    pass

        _model_verified = True
        logger.info("Successfully pulled %s", model)
        return True

    except Exception as e:
        logger.warning("Failed to ensure model %s: %s", model, e)
        return False


def query_ollama(
    model: str,
    prompt: str,
    system: str = "",
    timeout: float = 5.0,
    max_tokens: int = 128,
) -> str | None:
    """Query Ollama directly via HTTP — avoids importing the ollama SDK.

    Returns the response text, or None on failure.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": 0.1},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
        return result.get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.debug("1B query failed: %s", e)
        return None
