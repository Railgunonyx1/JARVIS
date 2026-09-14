"""Groq LLM Provider — ultra-fast inference via GroqCloud.

Uses the ``groq`` SDK (not openai) but shares the same chat completions
interface.  Overrides ``_get_client`` to create an ``AsyncGroq`` instance.
"""

import importlib.util
import logging

from providers.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger("jarvis.providers.groq")


class GroqProvider(OpenAICompatibleProvider):
    # Reasoning models (qwen3.6-27b) spend seconds emitting <think> tokens
    # before the first visible one. "none" disables reasoning entirely —
    # measured TTFT drops from ~3.4s to sub-second. Only applied to models
    # that support the parameter (Groq 400s otherwise), keyed by model id.
    _REASONING_MODELS = ("qwen3", "gpt-oss", "minimax")

    def __init__(self, config: dict, api_key: str, extra_keys: list[str] | None = None):
        super().__init__(
            "groq", config, api_key, extra_keys=extra_keys,
            default_model="llama-3.1-8b-instant",
        )
        self._sdk_package = "groq"
        self._check_package()

    def _extra_request_params(self) -> dict:
        """Disable reasoning tokens on reasoning-capable models (TTFT)."""
        model = str(self.config.get("model", self.default_model)).lower()
        if any(tag in model for tag in self._REASONING_MODELS):
            return {"reasoning_effort": "none", "reasoning_format": "hidden"}
        return {}

    def _check_package(self) -> bool:
        try:
            self._package_ok = importlib.util.find_spec("groq") is not None
            if not self._package_ok:
                self._package_error = "groq package not installed"
            return self._package_ok
        except Exception:
            self._package_ok = False
            self._package_error = "groq package not importable"
            return False

    def _get_client(self):
        if self._client is None or self._client_key_index != self._key_index:
            import groq
            self._client = groq.AsyncGroq(
                api_key=self.api_key,
                max_retries=0,
                timeout=self._timeout_seconds,
            )
            self._client_key_index = self._key_index
            logger.info("Groq: using key index %d", self._key_index)
        return self._client
