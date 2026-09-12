"""Provider factory. Per SPEC-model-bench.md section 2: get_provider(name) ->
Provider. Adapter modules are imported lazily inside each branch so importing
this package never requires every adapter's dependencies to be installed.
"""

from __future__ import annotations

from modelbench.providers.base import CallResult, Provider

_KNOWN_ADAPTERS = ("bedrock", "anthropic_direct", "openai_compatible", "fake")


def get_provider(name: str) -> Provider:
    if name == "bedrock":
        from modelbench.providers.bedrock import BedrockProvider

        return BedrockProvider()
    if name == "anthropic_direct":
        from modelbench.providers.anthropic_direct import AnthropicDirectProvider

        return AnthropicDirectProvider()
    if name == "openai_compatible":
        from modelbench.providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider()
    if name == "fake":
        # Local smoke tests only. Not a valid choice for a real run: it is
        # not documented in .env.example's MODELBENCH_ADAPTER values and has
        # no entry in data/prices.json.
        from modelbench.providers.fake import FakeProvider

        return FakeProvider()
    raise ValueError(
        f"unknown adapter {name!r}; expected one of: {', '.join(_KNOWN_ADAPTERS)} "
        "('fake' is for local smoke tests only)"
    )


__all__ = ["CallResult", "Provider", "get_provider"]
