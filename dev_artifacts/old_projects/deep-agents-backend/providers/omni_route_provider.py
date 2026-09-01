"""OmniRoute Provider — free local AI gateway via OpenAI-compatible endpoint."""

import logging

from providers.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger("jarvis.providers.omni_route")


class OmniRouteProvider(OpenAICompatibleProvider):
    def __init__(self, config: dict, api_key: str = "omni-route"):
        super().__init__(
            "omni_route", config, api_key or "omni-route",
            base_url=config.get("base_url", "http://localhost:20128/v1"),
            default_model="auto",
        )
