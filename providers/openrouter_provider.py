"""OpenRouter Provider — gateway to free and paid models via OpenRouter API."""

import logging

from providers.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger("jarvis.providers.openrouter")


class OpenRouterProvider(OpenAICompatibleProvider):
    def __init__(self, config: dict, api_key: str, extra_keys: list[str] | None = None):
        super().__init__(
            "openrouter", config, api_key, extra_keys=extra_keys,
            base_url=config.get("base_url", "https://openrouter.ai/api/v1"),
            default_model="nvidia/nemotron-3-ultra-550b-a55b:free",
        )
        self._extra_headers = {
            "HTTP-Referer": "https://jarvis-mkx.local",
            "X-Title": "JARVIS MK-X",
        }

    async def complete(self, messages, system_prompt=None, max_tokens=None,
                       temperature=None, tools=None):
        """Override to inject extra_headers into the OpenAI call."""
        from providers.types import openai_tools_param, parse_openai_tool_calls
        import time as _time

        full_messages = self._build_messages(messages, system_prompt)
        tool_param = openai_tools_param(tools)
        attempts = 0

        while attempts < len(self._keys):
            client = self._get_client()
            start = _time.time()
            try:
                kwargs = {"extra_headers": self._extra_headers}
                if tool_param:
                    kwargs["tools"] = tool_param
                response = await client.chat.completions.create(
                    model=self.config.get("model", self.default_model),
                    messages=full_messages,
                    max_tokens=max_tokens or self.config.get("max_tokens", 4096),
                    temperature=temperature or self.config.get("temperature", 0.7),
                    **kwargs,
                )
                latency = (_time.time() - start) * 1000
                choice = response.choices[0]
                usage = response.usage
                result = self._make_response(choice, response, usage, latency)
                self.record_success(latency)
                return result
            except Exception as e:
                error_str = str(e)
                if self._check_rate_limit(error_str) and self._rotate_key():
                    self.record_rate_limit()
                    attempts += 1
                    continue
                self.record_failure(error_str)
                raise
        from providers.types import ProviderError
        raise ProviderError(self.name, f"all {len(self._keys)} keys exhausted")

    async def complete_stream(self, messages, system_prompt=None, max_tokens=None,
                              temperature=None, tools=None):
        """Override to inject extra_headers into streaming calls."""
        from providers.types import openai_tools_param
        import time as _time

        full_messages = self._build_messages(messages, system_prompt)
        tool_param = openai_tools_param(tools)
        attempts = 0

        while attempts < len(self._keys):
            client = self._get_client()
            start = _time.time()
            try:
                kwargs = {"extra_headers": self._extra_headers}
                if tool_param:
                    kwargs["tools"] = tool_param
                stream = await client.chat.completions.create(
                    model=self.config.get("model", self.default_model),
                    messages=full_messages,
                    max_tokens=max_tokens or self.config.get("max_tokens", 4096),
                    temperature=temperature or self.config.get("temperature", 0.7),
                    stream=True,
                    **kwargs,
                )
                self._init_stream_tool_calls()
                async for chunk in stream:
                    if chunk.choices:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            yield delta.content
                        self._merge_tool_call_delta(delta.tool_calls)
                latency = (_time.time() - start) * 1000
                self.record_success(latency)
                return
            except Exception as e:
                error_str = str(e)
                if self._check_rate_limit(error_str) and self._rotate_key():
                    self.record_rate_limit()
                    attempts += 1
                    continue
                self.record_failure(error_str)
                raise
        from providers.types import ProviderError
        raise ProviderError(self.name, f"all {len(self._keys)} keys exhausted (stream)")
