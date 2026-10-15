"""Provider capability registry — declarative source of truth + fallback report.

`ProviderRouter` already walks a config-driven fallback chain, but nothing
recorded *what each provider can actually do*. That made the chain blind: a
request that needs tool calling could be routed at a provider that cannot
serve tools, and `cli/status` could not answer "which providers are capable of
X?".

This module is the single declarative source of truth. Two tiers:

* ``capabilities`` (enforced) — only capabilities the provider INTEGRATION
  actually exercises in code (streaming, tool calls, streamed tool-call
  capture, key rotation, local execution). The router is allowed to filter
  the fallback chain on these, so they must stay truthful.
* ``advisory`` — model/family-level traits (vision, JSON mode, reasoning,
  long context). Display-only; the router never filters on them because they
  depend on the specific model, not the provider integration.

The table is DECLARED (reviewed against the provider classes), not probed at
runtime. The router merges it with live health/availability when reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "ProviderCapability",
    "ProviderCapabilities",
    "PROVIDER_CAPABILITIES",
    "capabilities_for",
    "providers_with",
    "capability_matrix",
    "provider_capability_report",
]


class ProviderCapability(StrEnum):
    """Enforced, integration-level capabilities the router may filter on."""
    STREAMING = "streaming"
    TOOL_CALLS = "tool_calls"
    STREAM_TOOL_CALLS = "stream_tool_calls"
    KEY_ROTATION = "key_rotation"
    LOCAL = "local"


# Short codes for compact CLI rendering.
_SHORT = {
    ProviderCapability.STREAMING: "str",
    ProviderCapability.TOOL_CALLS: "tool",
    ProviderCapability.STREAM_TOOL_CALLS: "stool",
    ProviderCapability.KEY_ROTATION: "rotate",
    ProviderCapability.LOCAL: "local",
}


@dataclass(frozen=True)
class ProviderCapabilities:
    """Declared capabilities for one provider integration."""
    provider: str
    capabilities: frozenset[ProviderCapability]
    advisory: frozenset[str] = frozenset()
    requires_key: bool = True
    context_window: int | None = None
    notes: str = ""

    def has(self, *caps: ProviderCapability) -> bool:
        return all(c in self.capabilities for c in caps)

    def short(self) -> str:
        order = list(ProviderCapability)
        return ",".join(_SHORT[c] for c in order if c in self.capabilities)

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "capabilities": sorted(c.value for c in self.capabilities),
            "advisory": sorted(self.advisory),
            "requires_key": self.requires_key,
            "context_window": self.context_window,
            "notes": self.notes,
        }


# ── Integration-level capability sets (derived from provider code) ─────────

# OpenAICompatibleProvider subclasses: streamed tool-call capture + key rotation.
_OAI = frozenset({
    ProviderCapability.STREAMING,
    ProviderCapability.TOOL_CALLS,
    ProviderCapability.STREAM_TOOL_CALLS,
    ProviderCapability.KEY_ROTATION,
})
# GeminiProvider implements LLMProvider directly: no streamed tool-call capture
# (see the router's non-streaming fallback for that path).
_GEMINI = frozenset({
    ProviderCapability.STREAMING,
    ProviderCapability.TOOL_CALLS,
})
_GEMMA_LOCAL = frozenset({
    ProviderCapability.STREAMING,
    ProviderCapability.TOOL_CALLS,
    ProviderCapability.STREAM_TOOL_CALLS,
    ProviderCapability.LOCAL,
})
# Local routing gateway: OpenAI-compatible transport but keyless.
_GATEWAY = frozenset({
    ProviderCapability.STREAMING,
    ProviderCapability.TOOL_CALLS,
    ProviderCapability.STREAM_TOOL_CALLS,
})


def _oai(provider: str, *, advisory=(), requires_key=True, notes="", context_window=None):
    return ProviderCapabilities(
        provider=provider,
        capabilities=_OAI,
        advisory=frozenset(advisory),
        requires_key=requires_key,
        context_window=context_window,
        notes=notes,
    )


PROVIDER_CAPABILITIES: dict[str, ProviderCapabilities] = {
    # ── local ──────────────────────────────────────────────────────────
    "ollama": ProviderCapabilities(
        provider="ollama",
        capabilities=_GEMMA_LOCAL,
        advisory=frozenset({"reasoning", "vision"}),
        requires_key=False,
        notes="local daemon; model-dependent advisory traits",
    ),
    "omni_route": ProviderCapabilities(
        provider="omni_route",
        capabilities=_GATEWAY,
        advisory=frozenset({"reasoning"}),
        requires_key=False,
        notes="keyless local routing gateway",
    ),
    # ── first-party cloud ─────────────────────────────────────────────
    "gemini": ProviderCapabilities(
        provider="gemini",
        capabilities=_GEMINI,
        advisory=frozenset({"vision", "json_mode", "reasoning", "long_context"}),
        context_window=1_000_000,
        notes="no streamed tool-call capture; router falls back to non-streaming",
    ),
    "deepseek": _oai(
        "deepseek",
        advisory=("reasoning", "json_mode"),
        context_window=128_000,
    ),
    # ── aggregators / multi-model ─────────────────────────────────────
    "groq": _oai("groq", advisory=("json_mode",)),
    "openrouter": _oai(
        "openrouter",
        advisory=("vision", "json_mode", "reasoning", "long_context"),
        context_window=1_000_000,
        notes="model-dependent; routes across upstreams",
    ),
    "opencode_zen": _oai("opencode_zen", advisory=("vision", "json_mode", "reasoning")),
    "mistral": _oai("mistral", advisory=("json_mode", "vision")),
    "nvidia_nim": _oai("nvidia_nim", advisory=("json_mode",)),
    "cerebras": _oai("cerebras", advisory=("json_mode",)),
    "sakana": _oai("sakana", advisory=("reasoning",)),
    "huggingface": _oai(
        "huggingface",
        advisory=("json_mode", "vision"),
        notes="inference endpoints / router",
    ),
    # ── free-tier providers ───────────────────────────────────────────
    "llm7": _oai("llm7", advisory=("json_mode",), requires_key=False,
                 notes="anonymous token 'unused' serves a subset of its menu"),
    "github_models": _oai("github_models", advisory=("json_mode", "vision")),
    "cloudflare_ai": _oai("cloudflare_ai", advisory=("json_mode",)),
    "cohere": _oai("cohere", advisory=("json_mode",)),
    "sambanova": _oai("sambanova", advisory=("json_mode",)),
    "zai": _oai("zai", advisory=("json_mode", "reasoning")),
    "agnes": _oai("agnes", advisory=("json_mode",)),
    "kilo_code": _oai("kilo_code", advisory=("json_mode",)),
    "scaleway": _oai("scaleway", advisory=("json_mode",)),
}

# Conservative fallback for an unknown integration: assume the safe minimum
# (the transport every provider inherits) and require a key.
_UNKNOWN = ProviderCapabilities(
    provider="unknown",
    capabilities=frozenset({ProviderCapability.STREAMING, ProviderCapability.TOOL_CALLS}),
    requires_key=True,
    notes="unregistered provider — conservative assumptions",
)


def capabilities_for(provider: str) -> ProviderCapabilities:
    """Declared capabilities for ``provider`` (conservative default if unknown)."""
    return PROVIDER_CAPABILITIES.get(provider, _UNKNOWN)


def providers_with(*caps: ProviderCapability) -> list[str]:
    """Providers whose ENFORCED capabilities include all of ``caps``."""
    return [
        name for name, pc in PROVIDER_CAPABILITIES.items()
        if pc.has(*caps)
    ]


def capability_matrix() -> dict[str, dict]:
    """Full declared matrix (every registered provider) as plain dicts."""
    return {name: pc.to_dict() for name, pc in PROVIDER_CAPABILITIES.items()}


def provider_capability_report(
    *,
    status: dict | None = None,
    fallback_chain: list[str] | None = None,
    local_models: list[str] | None = None,
) -> dict:
    """Merge the declared capability table with live router state.

    ``status`` is ``ProviderRouter.status`` (per-configured-provider runtime
    health). Providers in the declared table but not configured are still
    listed, marked ``configured=False``, so the report doubles as a catalog.
    """
    status = status or {}
    names = list(dict.fromkeys([*PROVIDER_CAPABILITIES, *status]))
    providers: dict[str, dict] = {}
    for name in names:
        pc = capabilities_for(name)
        entry = pc.to_dict()
        runtime = status.get(name)
        entry["configured"] = runtime is not None
        entry["available"] = bool(runtime.get("available")) if runtime else None
        entry["model"] = runtime.get("model") if runtime else None
        entry["health"] = runtime.get("health") if runtime else None
        providers[name] = entry
    return {
        "providers": providers,
        "fallback_chain": list(fallback_chain or []),
        "local_models": list(local_models or []),
    }

