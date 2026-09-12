"""Tests for the provider layer. Per SPEC-model-bench.md section 5: "Tests
mock the network; no test calls a real API." Every network boundary here
(boto3's bedrock-runtime client, urllib.request.urlopen) is replaced with a
fake, never a real call.
"""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import patch

import pytest

from modelbench.providers import get_provider
from modelbench.providers.anthropic_direct import AnthropicDirectProvider
from modelbench.providers.base import RetryableError, call_with_retries
from modelbench.providers.bedrock import BedrockProvider
from modelbench.providers.fake import FakeProvider
from modelbench.providers.openai_compatible import OpenAICompatibleProvider

# --- call_with_retries ----------------------------------------------------


def test_retry_succeeds_first_try():
    calls = []

    def attempt():
        calls.append(1)
        return "ok"

    result, retries, error, http_status = call_with_retries(attempt)
    assert result == "ok"
    assert retries == 0
    assert error is None
    assert len(calls) == 1


def test_retry_succeeds_after_two_failures():
    calls = []

    def attempt():
        calls.append(1)
        if len(calls) < 3:
            raise RetryableError("throttled", http_status=429)
        return "ok"

    with patch("modelbench.providers.base.time.sleep"):
        result, retries, error, http_status = call_with_retries(attempt)
    assert result == "ok"
    assert retries == 2
    assert len(calls) == 3


def test_retry_exhausts_all_attempts():
    def attempt():
        raise RetryableError("still throttled", http_status=429)

    with patch("modelbench.providers.base.time.sleep"):
        result, retries, error, http_status = call_with_retries(attempt, max_attempts=5)
    assert result is None
    assert retries == 4
    assert "still throttled" in error
    assert http_status == 429


def test_retry_non_retryable_fails_immediately():
    calls = []

    def attempt():
        calls.append(1)
        raise ValueError("bad request")

    result, retries, error, http_status = call_with_retries(attempt)
    assert result is None
    assert retries == 0
    assert "bad request" in error
    assert len(calls) == 1  # no retry attempted


# --- BedrockProvider --------------------------------------------------------


class _FakeBotocoreError(Exception):
    def __init__(self, code, http_status):
        super().__init__(code)
        self.response = {
            "Error": {"Code": code},
            "ResponseMetadata": {"HTTPStatusCode": http_status},
        }


class _FakeBedrockClientSuccess:
    def converse(self, **kwargs):
        return {
            "output": {
                "message": {"content": [{"text": '{"intent": "card_arrival", "confidence": 90}'}]}
            },
            "usage": {"inputTokens": 120, "outputTokens": 8},
            "ResponseMetadata": {"HTTPStatusCode": 200},
        }


class _FakeBedrockClientThrottleThenSuccess:
    def __init__(self):
        self.calls = 0

    def converse(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise _FakeBotocoreError("ThrottlingException", 429)
        return {
            "output": {
                "message": {"content": [{"text": '{"intent": "card_arrival", "confidence": 50}'}]}
            },
            "usage": {"inputTokens": 100, "outputTokens": 5},
            "ResponseMetadata": {"HTTPStatusCode": 200},
        }


class _FakeBedrockClientValidationError:
    def converse(self, **kwargs):
        raise _FakeBotocoreError("ValidationException", 400)


def test_bedrock_success_parses_usage_and_text():
    provider = BedrockProvider(region="us-east-1")
    provider._client = _FakeBedrockClientSuccess()
    result = provider.call("some-model-id", "prompt text", max_tokens=60, temperature=0)
    assert result.error is None
    assert result.input_tokens == 120
    assert result.output_tokens == 8
    assert result.adapter == "bedrock"
    assert result.retries == 0
    assert "card_arrival" in result.text


def test_bedrock_retries_on_throttling_then_succeeds():
    provider = BedrockProvider(region="us-east-1")
    provider._client = _FakeBedrockClientThrottleThenSuccess()
    with patch("modelbench.providers.base.time.sleep"):
        result = provider.call("some-model-id", "prompt text", max_tokens=60, temperature=0)
    assert result.error is None
    assert result.retries == 1


def test_bedrock_non_retryable_error_fails_immediately():
    provider = BedrockProvider(region="us-east-1")
    provider._client = _FakeBedrockClientValidationError()
    result = provider.call("some-model-id", "prompt text", max_tokens=60, temperature=0)
    assert result.error is not None
    assert result.retries == 0
    assert result.text == ""


# --- AnthropicDirectProvider -------------------------------------------------


class _FakeHTTPResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def test_anthropic_direct_missing_api_key_errors_without_network():
    with patch.dict("os.environ", {}, clear=True):
        provider = AnthropicDirectProvider()
        result = provider.call("claude-x", "hi", max_tokens=60, temperature=0)
    assert result.error is not None
    assert result.retries == 0


def test_anthropic_direct_success():
    payload = {
        "content": [{"text": '{"intent": "card_arrival", "confidence": 70}'}],
        "usage": {"input_tokens": 50, "output_tokens": 6},
    }
    provider = AnthropicDirectProvider(api_key="fake-key")
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
        result = provider.call("claude-x", "hi", max_tokens=60, temperature=0)
    assert result.error is None
    assert result.input_tokens == 50
    assert result.output_tokens == 6
    assert "card_arrival" in result.text


def test_anthropic_direct_retries_on_503_then_succeeds():
    payload = {"content": [{"text": "{}"}], "usage": {"input_tokens": 1, "output_tokens": 1}}
    calls = {"n": 0}

    def fake_urlopen(req, timeout=60):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 503, "Service Unavailable", {}, None)
        return _FakeHTTPResponse(payload)

    provider = AnthropicDirectProvider(api_key="fake-key")
    with patch("urllib.request.urlopen", side_effect=fake_urlopen), patch(
        "modelbench.providers.base.time.sleep"
    ):
        result = provider.call("claude-x", "hi", max_tokens=60, temperature=0)
    assert result.error is None
    assert result.retries == 1


def test_anthropic_direct_non_retryable_400_fails_immediately():
    def fake_urlopen(req, timeout=60):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, None)

    provider = AnthropicDirectProvider(api_key="fake-key")
    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = provider.call("claude-x", "hi", max_tokens=60, temperature=0)
    assert result.error is not None
    assert result.retries == 0


# --- OpenAICompatibleProvider ------------------------------------------------


def test_openai_compatible_missing_config_errors_without_network():
    with patch.dict("os.environ", {}, clear=True):
        provider = OpenAICompatibleProvider()
        result = provider.call("some-model", "hi", max_tokens=60, temperature=0)
    assert result.error is not None
    assert result.retries == 0


def test_openai_compatible_success():
    payload = {
        "choices": [{"message": {"content": '{"intent": "card_arrival", "confidence": 65}'}}],
        "usage": {"prompt_tokens": 40, "completion_tokens": 7},
    }
    provider = OpenAICompatibleProvider(base_url="https://example.com/v1", api_key="fake-key")
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse(payload)):
        result = provider.call("some-model", "hi", max_tokens=60, temperature=0)
    assert result.error is None
    assert result.input_tokens == 40
    assert result.output_tokens == 7


# --- FakeProvider ------------------------------------------------------------


def test_fake_provider_returns_a_valid_label_from_the_prompt():
    from modelbench.prompt import build_prompt

    labels = ["card_arrival", "exchange_rate", "top_up_failed"]
    prompt = build_prompt("Where is my card?", labels)
    provider = FakeProvider()
    result = provider.call("fake-model", prompt, max_tokens=60, temperature=0)
    parsed = json.loads(result.text)
    assert parsed["intent"] in labels
    assert 0 <= parsed["confidence"] <= 100
    assert result.error is None
    assert result.adapter == "fake"


# --- get_provider factory -----------------------------------------------------


def test_get_provider_known_names():
    assert isinstance(get_provider("fake"), FakeProvider)


def test_get_provider_unknown_name_raises():
    with pytest.raises(ValueError):
        get_provider("not-a-real-adapter")
