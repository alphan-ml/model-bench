"""Provider protocol and shared types for every adapter (bedrock,
anthropic_direct, openai_compatible, fake).

Per SPEC-model-bench.md section 5, plus SPEC-cost-meter-and-angi-reuse.md
section 4 ("Changes to the base specs"): CallResult gains session_id,
use_case, step so a later task (W-M1/W-M2) can write a usage_events row per
call without touching this dataclass again. Nothing in this task (W-A2)
reads or writes those three fields — they default to None and are carried
through unused, which is the addendum's stated intent.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass
class CallResult:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    adapter: str  # "bedrock" | "anthropic_direct" | "openai_compatible" | "fake"
    http_status: int
    retries: int
    error: str | None
    # Cost-meter addendum fields (unused until W-M1/W-M2 — see module docstring).
    session_id: str | None = None
    use_case: str | None = None
    step: str | None = None


class Provider(Protocol):
    def call(
        self, model_id: str, prompt: str, max_tokens: int, temperature: float
    ) -> CallResult: ...


class RetryableError(Exception):
    """Raise this from inside an adapter's single-attempt function to signal
    a retryable failure (throttling or a 5xx). Any other exception raised
    from the attempt function is treated as fatal: call_with_retries stops
    immediately, no retry.
    """

    def __init__(self, message: str, http_status: int = 0):
        super().__init__(message)
        self.http_status = http_status


def call_with_retries(
    attempt: Callable[[], object], max_attempts: int = 5
) -> tuple[object | None, int, str | None, int]:
    """Calls attempt() (a zero-arg callable) up to max_attempts times total.

    Retries only on RetryableError, with exponential backoff + jitter between
    attempts (never after the last one). Per SPEC-model-bench.md section 5:
    up to 5 attempts, exponential backoff with jitter, on throttling and 5xx
    only.

    Returns (result_or_None, retries, error_or_None, http_status).
    `retries` is the number of retries actually used — 0 means the first
    attempt succeeded. `result_or_None` is None only if every attempt failed,
    or if attempt() raised a non-retryable exception (in which case no retry
    is attempted at all).
    """
    last_error: str | None = None
    last_http_status = 0
    for attempt_num in range(max_attempts):
        try:
            result = attempt()
            return result, attempt_num, None, 0
        except RetryableError as exc:
            last_error = str(exc)
            last_http_status = exc.http_status
            if attempt_num < max_attempts - 1:
                sleep_s = (2**attempt_num) * 0.1 + random.uniform(0, 0.1)
                time.sleep(sleep_s)
        except Exception as exc:  # non-retryable: fail immediately, no retry
            return None, attempt_num, str(exc), 0
    return None, max_attempts - 1, last_error, last_http_status
