"""Generic OpenAI-compatible free-tier providers (freellm-apis directory).

One module, many providers: each free LLM API from the awesome-freellm-apis
directory that speaks the plain OpenAI chat-completions protocol gets a tiny
subclass here instead of its own file. Rate limits live in
``config/models.toml`` ([<name>] sections); API keys come from the standard
``<NAME>_API_KEY`` env/.env chain (see core/api_keys.py).

Providers and default models follow freellm.net's daily-refreshed data
(2026-09 snapshot):
    llm7          — https://api.llm7.io/v1            (no card, 10 RPM)
    github_models — https://models.github.ai/inference (no card)
    cloudflare_ai — Workers AI REST                    (no card)
    cohere        — https://api.cohere.com/compatibility/v2 (no card, 20 RPM)
    sambanova     — https://api.sambanova.ai/v1        (20 RPM / 20 RPD)
    zai           — https://api.z.ai/api/paas/v4       (GLM flash models)
    agnes         — https://apihub.agnes-ai.com/v1     (30 RPM)
    kilo_code     — https://api.kilo.ai/api/gateway    (200 req/hr)
    scaleway      — https://api.scaleway.ai/v1         (registration)
"""

from providers.openai_compat import OpenAICompatibleProvider


class LLM7Provider(OpenAICompatibleProvider):
    """llm7.io — free tier, no credit card, anonymous access supported.

    Verified 2026-09-20: the endpoint accepts the literal token "unused"
    for a subset of models (GLM-5.3-Flash, codestral-latest — the big-name
    entries now 401 anonymously). The dead default "gpt-oss-20b" is gone
    from the live menu; default follows config/models.toml instead.
    """

    ANON_TOKEN = "unused"

    def __init__(self, config: dict, api_key: str | None = None,
                 extra_keys: list[str] | None = None,
                 base_url: str | None = None,
                 default_model: str | None = None):
        super().__init__(
            "llm7", config, api_key or self.ANON_TOKEN,
            extra_keys=extra_keys,
            base_url=base_url or config.get("base_url", "https://api.llm7.io/v1"),
            default_model=default_model or config.get("model", "GLM-5.3-Flash"),
        )


class GitHubModelsProvider(OpenAICompatibleProvider):
    """GitHub Models — free tier with a GitHub PAT, no credit card."""

    def __init__(self, config: dict, api_key: str):
        super().__init__(
            "github_models", config, api_key,
            base_url=config.get("base_url", "https://models.github.ai/inference"),
            default_model="openai/gpt-4.1-mini",
        )


class CloudflareAIProvider(OpenAICompatibleProvider):
    """Cloudflare Workers AI — REST inference, 10K neurons/day free."""

    def __init__(self, config: dict, api_key: str):
        super().__init__(
            "cloudflare_ai", config, api_key,
            base_url=config.get(
                "base_url",
                "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run",
            ),
            default_model="@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        )


class CohereProvider(OpenAICompatibleProvider):
    """Cohere — OpenAI-compatibility endpoint, 20 RPM free, no card."""

    def __init__(self, config: dict, api_key: str):
        super().__init__(
            "cohere", config, api_key,
            base_url=config.get(
                "base_url", "https://api.cohere.com/compatibility/v2"
            ),
            default_model="command-a-111b",
        )


class SambaNovaProvider(OpenAICompatibleProvider):
    """SambaNova — 20 RPM / 20 RPD free tier."""

    def __init__(self, config: dict, api_key: str):
        super().__init__(
            "sambanova", config, api_key,
            base_url=config.get("base_url", "https://api.sambanova.ai/v1"),
            default_model="deepseek-v3-1",
        )


class ZAIProvider(OpenAICompatibleProvider):
    """Z AI (Zhipu) — GLM flash models, 1 concurrent request free."""

    def __init__(self, config: dict, api_key: str):
        super().__init__(
            "zai", config, api_key,
            base_url=config.get("base_url", "https://api.z.ai/api/paas/v4"),
            default_model="glm-4.7-flash",
        )


class AgnesProvider(OpenAICompatibleProvider):
    """Agnes AI — 30 RPM free tier."""

    def __init__(self, config: dict, api_key: str):
        super().__init__(
            "agnes", config, api_key,
            base_url=config.get("base_url", "https://apihub.agnes-ai.com/v1"),
            default_model="agnes-2.0-flash",
        )


class KiloCodeProvider(OpenAICompatibleProvider):
    """Kilo Code gateway — 200 req/hr, proxies :free OpenRouter models."""

    def __init__(self, config: dict, api_key: str):
        super().__init__(
            "kilo_code", config, api_key,
            base_url=config.get("base_url", "https://api.kilo.ai/api/gateway"),
            default_model="nvidia/nemotron-3-ultra-550b-a55b:free",
        )


class ScalewayProvider(OpenAICompatibleProvider):
    """Scaleway Generative APIs — registration only, no card."""

    def __init__(self, config: dict, api_key: str):
        super().__init__(
            "scaleway", config, api_key,
            base_url=config.get("base_url", "https://api.scaleway.ai/v1"),
            default_model="qwen3-235b-a22b-instruct",
        )


__all__ = [
    "LLM7Provider",
    "GitHubModelsProvider",
    "CloudflareAIProvider",
    "CohereProvider",
    "SambaNovaProvider",
    "ZAIProvider",
    "AgnesProvider",
    "KiloCodeProvider",
    "ScalewayProvider",
]
