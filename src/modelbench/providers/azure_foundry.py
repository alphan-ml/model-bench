"""Azure AI Foundry adapter -- the second provider (per the build
instruction's section 6.2, "Model Bench -- Azure AI Foundry as the second
provider"): "Add src/modelbench/providers/azure_foundry.py implementing the
same Provider interface as bedrock.py (Foundry chat-completions endpoint,
key from env AZURE_FOUNDRY_KEY, deployment from AZURE_FOUNDRY_DEPLOYMENT;
same retry contract; token usage from the response)."

Azure AI Foundry model deployments expose an OpenAI-compatible REST API:

    POST {endpoint}/openai/deployments/{deployment}/chat/completions?api-version=...
    header: api-key: <key>
    body:   {"messages": [...], "max_tokens": ..., "temperature": ...}
    resp:   {"choices": [{"message": {"content": ...}}], "usage": {...}}

This is the same request/response shape as openai_compatible.py -- just a
different URL and an `api-key` header instead of `Authorization: Bearer` --
implemented as its own file rather than by parameterizing/subclassing
OpenAICompatibleProvider, matching the repo's existing pattern of one
self-contained file per fallback/secondary adapter (anthropic_direct.py and
openai_compatible.py already duplicate this same request/retry shape rather
than share a base class -- see D10 in CONTEXT.md). Stdlib `urllib` only,
same dependency-free rule as those two (no new SDK dependency for a second
provider whose main cost driver, per the build instruction, is one small
chat-completions deployment).

STATUS as of this file's creation: no Azure AI Foundry project, endpoint, or
key exists yet on this Mac (Gate 1, section 4, is not done -- confirmed by
`az account show` failing with no Azure CLI even installed). This adapter
has been exercised ONLY against a mocked HTTP response in
tests/test_providers_mock.py. It has never made, and as of this file's
creation cannot make, a real network call to any Azure endpoint.

`_DEFAULT_API_VERSION` below is a plausible Azure OpenAI-style REST
`api-version` query value, written from general knowledge of the Azure
OpenAI/AI Foundry REST API shape -- it is NOT confirmed against the actual
Azure AI Foundry docs page for whatever deployment Leon provisions at Gate
1, and must not be treated as a verified fact. Confirm (or override via the
AZURE_FOUNDRY_API_VERSION env var) once a real Foundry project/deployment
exists.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from modelbench.providers.base import CallResult, RetryableError, call_with_retries

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# UNVERIFIED default -- see module docstring. Override with
# AZURE_FOUNDRY_API_VERSION once a real Foundry deployment's docs page
# confirms the right value for that deployment.
_DEFAULT_API_VERSION = "2024-06-01"


class AzureFoundryProvider:
    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        deployment: str | None = None,
        api_version: str | None = None,
    ):
        self._endpoint = (endpoint or os.environ.get("AZURE_FOUNDRY_ENDPOINT") or "").rstrip("/")
        self._api_key = api_key or os.environ.get("AZURE_FOUNDRY_KEY")
        self._deployment = deployment or os.environ.get("AZURE_FOUNDRY_DEPLOYMENT")
        self._api_version = (
            api_version or os.environ.get("AZURE_FOUNDRY_API_VERSION") or _DEFAULT_API_VERSION
        )

    def call(self, model_id: str, prompt: str, max_tokens: int, temperature: float) -> CallResult:
        # model_id is part of the shared Provider interface (bedrock.py's
        # model_id selects which Bedrock model to invoke) but Foundry routes
        # by *deployment*, not model id -- AZURE_FOUNDRY_DEPLOYMENT is what
        # actually gets called. Accepted and ignored, rather than dropped
        # from the signature, so runner.py never needs an adapter-specific
        # call shape.
        del model_id

        if not self._endpoint or not self._api_key or not self._deployment:
            return CallResult(
                text="",
                input_tokens=0,
                output_tokens=0,
                latency_ms=0.0,
                adapter="azure_foundry",
                http_status=0,
                retries=0,
                error=(
                    "AZURE_FOUNDRY_ENDPOINT / AZURE_FOUNDRY_KEY / "
                    "AZURE_FOUNDRY_DEPLOYMENT not set"
                ),
            )

        body = json.dumps(
            {
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")

        url = (
            f"{self._endpoint}/openai/deployments/{self._deployment}/chat/completions"
            f"?api-version={self._api_version}"
        )

        def attempt():
            start = time.perf_counter()
            req = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers={
                    "content-type": "application/json",
                    "api-key": self._api_key,
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    payload = json.loads(resp.read())
                    status = resp.status
            except urllib.error.HTTPError as exc:
                status = exc.code
                if status in _RETRYABLE_STATUS:
                    raise RetryableError(
                        f"HTTP {status}: {exc.reason}", http_status=status
                    ) from exc
                raise RuntimeError(f"HTTP {status}: {exc.reason}") from exc
            elapsed_ms = (time.perf_counter() - start) * 1000
            return payload, status, elapsed_ms

        outcome, retries, error, http_status = call_with_retries(attempt)

        if outcome is None:
            return CallResult(
                text="",
                input_tokens=0,
                output_tokens=0,
                latency_ms=0.0,
                adapter="azure_foundry",
                http_status=http_status,
                retries=retries,
                error=error,
            )

        payload, status, elapsed_ms = outcome
        choice = payload.get("choices", [{}])[0]
        text = choice.get("message", {}).get("content", "")
        usage = payload.get("usage", {})

        return CallResult(
            text=text,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_ms=elapsed_ms,
            adapter="azure_foundry",
            http_status=status,
            retries=retries,
            error=None,
        )
