"""Mistral Provider — OpenAI-compatible endpoint with multi-key rotation."""

import logging

from providers.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger("jarvis.providers.mistral")


class MistralProvider(OpenAICompatibleProvider):
    def __init__(self, config: dict, api_key: str, extra_keys: list[str] | None = None):
        super().__init__(
            "mistral", config, api_key, extra_keys=extra_keys,
            base_url=config.get("base_url", "https://api.mistral.ai/v1"),
            default_model="mistral-small-latest",
        )
