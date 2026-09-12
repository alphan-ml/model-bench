"""A fake Provider for local smoke tests only.

Never a real adapter choice for a run: it is not one of the documented
MODELBENCH_ADAPTER values in .env.example and has no entry in
data/prices.json. It exists so `modelbench smoke` (and this repo's own
tests) can exercise the full pipeline — prompt building, calling, parsing,
correctness scoring, resumable file writing — with no network and no
secrets. See runner.py's use of a dedicated `.smoke_outputs/` directory,
which this provider's output is always written to, never to outputs/.
"""

from __future__ import annotations

import json
import random
import time

from modelbench.providers.base import CallResult


class FakeProvider:
    """Reads the allowed-intent list back out of the prompt (build_prompt
    lists them one per line as "- label") and returns a valid-shaped JSON
    response naming a random one of them, with a small simulated latency.
    Always succeeds — it exists to test pipeline plumbing, not accuracy.
    """

    def call(self, model_id: str, prompt: str, max_tokens: int, temperature: float) -> CallResult:
        start = time.perf_counter()
        labels = [line[2:] for line in prompt.splitlines() if line.startswith("- ")]
        intent = random.choice(labels) if labels else "unknown"
        confidence = random.randint(50, 99)
        text = json.dumps({"intent": intent, "confidence": confidence})
        latency_ms = (time.perf_counter() - start) * 1000 + random.uniform(5, 20)
        return CallResult(
            text=text,
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
            latency_ms=latency_ms,
            adapter="fake",
            http_status=200,
            retries=0,
            error=None,
        )
