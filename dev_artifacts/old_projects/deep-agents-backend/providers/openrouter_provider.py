"""OpenRouter Provider — gateway to free and paid models via OpenRouter API."""

import logging

from providers.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger("jarvis.providers.openrouter")


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self, config: dict, api_key: str, extra_keys: list[str] | None = None):
        super().__init__(
            "openrouter", config, api_key, extra_keys=extra_keys,
            base_url=config.get("base_url", "https://openrouter.ai/api/v1"),
            default_model="nvidia/nemotron-3-ultra-550b-a55b:free",
        )

    def _extra_headers(self) -> dict:
        return {
            "HTTP-Referer": "https://jarvis-mkx.local",
            "X-Title": "JARVIS MK-X",
        }
