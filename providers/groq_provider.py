"""Groq LLM Provider — ultra-fast inference via GroqCloud.

Uses the ``groq`` SDK (not openai) but shares the same chat completions
interface.  Overrides ``_get_client`` to create an ``AsyncGroq`` instance.
"""

import importlib.util
import logging

from providers.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger("jarvis.providers.groq")


class GroqProvider(OpenAICompatibleProvider):
    def __init__(self, config: dict, api_key: str, extra_keys: list[str] | None = None):
        super().__init__(
            "groq", config, api_key, extra_keys=extra_keys,
            default_model="llama-3.1-8b-instant",
        )
        self._sdk_package = "groq"
        self._check_package()

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
            )
            self._client_key_index = self._key_index
            logger.info("Groq: using key index %d", self._key_index)
        return self._client
