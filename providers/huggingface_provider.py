"""HuggingFace Inference API Provider — free tier with many models.

Free tier: rate-limited but no credit card required.
Base URL: https://router.huggingface.co/v1
"""

from providers.openai_compat import OpenAICompatibleProvider


class HuggingFaceProvider(OpenAICompatibleProvider):
    def __init__(self, config: dict, api_key: str):
        super().__init__(
            "huggingface", config, api_key,
            default_model="Qwen/Qwen2.5-72B-Instruct",
            base_url="https://router.huggingface.co/v1",
        )
