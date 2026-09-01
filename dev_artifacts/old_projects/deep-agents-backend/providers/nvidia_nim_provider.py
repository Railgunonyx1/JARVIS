"""NVIDIA NIM Provider — hosted models via OpenAI-compatible endpoint."""

import logging

from providers.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger("jarvis.providers.nvidia_nim")


class NVIDIAProvider(OpenAICompatibleProvider):
    def __init__(self, config: dict, api_key: str):
        super().__init__(
            "nvidia_nim", config, api_key,
            base_url=config.get("base_url", "https://integrate.api.nvidia.com/v1"),
            default_model="nvidia/llama-3.3-70b-instruct",
        )
