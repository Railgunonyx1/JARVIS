"""DeepSeek LLM Provider — affordable coding-focused inference.

DeepSeek offers very cheap API access with excellent coding ability.
Base URL: https://api.deepseek.com/v1
"""

from providers.openai_compat import OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    def __init__(self, config: dict, api_key: str):
        super().__init__(
            "deepseek", config, api_key,
            default_model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
        )
