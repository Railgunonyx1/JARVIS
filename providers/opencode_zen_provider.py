"""OpenCode Zen Provider — Free models via OpenAI-compatible endpoint."""

import hashlib
import logging
import uuid

from providers.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger("jarvis.providers.opencode_zen")


class OpenCodeZenProvider(OpenAICompatibleProvider):
    def __init__(self, config: dict, api_key: str):
        super().__init__(
            "opencode_zen", config, api_key,
            base_url=config.get("base_url", "https://opencode.ai/zen/v1"),
            default_model="nemotron-3-ultra-free",
        )
        # Zen's free tier rejects requests without a stable session header
        # (MissingSessionID: "free tier can only be used in OpenCode"). Send
        # one derived from the key hash so routing is stable across restarts
        # without ever transmitting the key itself.
        digest = hashlib.sha256((api_key or "").encode()).hexdigest()
        self._zen_session = f"jarvis-{digest[:24]}-{uuid.uuid4().hex[:8]}"

    def _extra_headers(self) -> dict:
        headers = super()._extra_headers()
        headers["x-opencode-session"] = self._zen_session
        headers["X-Session-ID"] = self._zen_session
        return headers
