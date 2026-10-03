"""Sakana AI (Fugu family) provider.

Sakana Fugu is a multi-agent orchestration system delivered behind a single
OpenAI-compatible API (https://api.sakana.ai/v1). Fugu Ultra v2 (2026-09-11)
targets peak multi-step capability; Fugu Max targets the cost-performance
Pareto frontier. Keys: console.sakana.ai (SAKANA_API_KEY).
"""

from __future__ import annotations

from providers.openai_compat import OpenAICompatibleProvider


class SakanaProvider(OpenAICompatibleProvider):
    def __init__(self, config: dict, api_key: str, extra_keys: list[str] | None = None):
        super().__init__(
            "sakana", config, api_key, extra_keys=extra_keys,
            base_url=config.get("base_url", "https://api.sakana.ai/v1"),
            default_model=config.get("model", "fugu-ultra-v2"),
        )
