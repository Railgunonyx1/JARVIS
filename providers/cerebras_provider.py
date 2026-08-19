"""Cerebras LLM Provider — ultra-fast inference via Cerebras Inference.

Free tier: 1000 requests/day, no credit card required.
Base URL: https://api.cerebras.ai/v1
"""

from providers.openai_compat import OpenAICompatibleProvider


class CerebrasProvider(OpenAICompatibleProvider):
    def __init__(self, config: dict, api_key: str):
        super().__init__(
            "cerebras", config, api_key,
            default_model="llama-3.3-70b",
            base_url="https://api.cerebras.ai/v1",
        )
