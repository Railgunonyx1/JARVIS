"""OpenCode Zen Provider — Free models via OpenAI-compatible endpoint."""

import logging

from providers.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger("jarvis.providers.opencode_zen")


class OpenCodeZenProvider(OpenAICompatibleProvider):
    def __init__(self, config: dict, api_key: str):
        super().__init__(
            "opencode_zen", config, api_key,
            base_url=config.get("base_url", "https://opencode.ai/zen/v1"),
            default_model="nemotron-3-ultra-free",
        )
