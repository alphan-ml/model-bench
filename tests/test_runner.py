"""Tests for the runner: resumability/idempotence (a hard non-negotiable per
SPEC-model-bench.md section 1: "Runs are resumable and idempotent") and the
output row schema, using the real committed golden/labels/coarse-map data
(sliced small with --limit) and a FakeProvider — no network, no secrets.

These always write to a pytest tmp_path, never to outputs/ or
.smoke_outputs/, so they can never touch or corrupt real run data.
"""

from __future__ import annotations

import json

from modelbench import runner
from modelbench.providers.base import CallResult
from modelbench.providers.fake import FakeProvider


def test_run_writes_expected_row_schema(tmp_path):
    out_path = tmp_path / "smoke.jsonl"
    summary = runner.run(
        "smoke-fake",
        model_id="fake-model-v1",
        provider=FakeProvider(),
        limit=5,
        resume=False,
        out_path=out_path,
    )
    assert summary.n_processed == 5
    assert summary.n_errors == 0
    assert summary.error_rate == 0.0

    lines = out_path.read_text().strip().splitlines()
    assert len(lines) == 5
    expected_fields = {
        "id",
        "model_key",
        "model_id",
        "adapter",
        "intent_pred",
        "confidence",
        "invalid",
        "correct_fine",
        "correct_coarse",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "retries",
        "error",
        "ts",
    }
    for line in lines:
        row = json.loads(line)
        assert set(row.keys()) == expected_fields
        assert row["model_key"] == "smoke-fake"
        assert row["model_id"] == "fake-model-v1"
        assert row["adapter"] == "fake"
        assert row["error"] is None


def test_run_is_resumable_and_idempotent(tmp_path):
    out_path = tmp_path / "resume.jsonl"

    first = runner.run(
        "smoke-fake",
        model_id="fake-model-v1",
        provider=FakeProvider(),
        limit=5,
        resume=True,
        out_path=out_path,
    )
    assert first.n_processed == 5
    assert first.n_skipped_existing == 0

    second = runner.run(
        "smoke-fake",
        model_id="fake-model-v1",
        provider=FakeProvider(),
        limit=5,
        resume=True,
        out_path=out_path,
    )
    # Every id from the first run is already present, so nothing new runs.
    assert second.n_processed == 0
    assert second.n_skipped_existing == 5

    lines = out_path.read_text().strip().splitlines()
    assert len(lines) == 5  # not duplicated


def test_run_partial_resume_only_processes_missing_ids(tmp_path):
    out_path = tmp_path / "partial.jsonl"

    first = runner.run(
        "smoke-fake",
        model_id="fake-model-v1",
        provider=FakeProvider(),
        limit=3,
        resume=True,
        out_path=out_path,
    )
    assert first.n_processed == 3

    # Re-run against a larger slice of the same golden rows: ids 0-2 already
    # exist, so only ids 3-4 should be newly processed.
    second = runner.run(
        "smoke-fake",
        model_id="fake-model-v1",
        provider=FakeProvider(),
        limit=5,
        resume=True,
        out_path=out_path,
    )
    assert second.n_processed == 2
    assert second.n_skipped_existing == 3

    lines = out_path.read_text().strip().splitlines()
    ids = sorted(json.loads(line)["id"] for line in lines)
    assert ids == [0, 1, 2, 3, 4]


def test_run_error_rate_is_reported(tmp_path):
    class AlwaysErrorsProvider:
        def call(self, model_id, prompt, max_tokens, temperature):
            return CallResult(
                text="",
                input_tokens=0,
                output_tokens=0,
                latency_ms=0.0,
                adapter="fake",
                http_status=0,
                retries=0,
                error="simulated failure",
            )

    out_path = tmp_path / "errors.jsonl"
    summary = runner.run(
        "smoke-fake",
        model_id="fake-model-v1",
        provider=AlwaysErrorsProvider(),
        limit=5,
        resume=False,
        out_path=out_path,
    )
    assert summary.n_errors == 5
    assert summary.error_rate == 1.0


def test_run_survives_a_provider_that_raises_instead_of_returning_a_call_result(tmp_path):
    """A provider bug (or an adapter setup failure it forgot to catch — this
    is exactly the shape of a bug this test caught: BedrockProvider used to
    raise RuntimeError("AWS_REGION is not set") straight out of .call()
    instead of returning a CallResult) must never crash the whole run or
    lose the rest of the batch. One bad row becomes one error row.
    """

    class RaisingProvider:
        def call(self, model_id, prompt, max_tokens, temperature):
            raise RuntimeError("boom: adapter misconfigured")

    out_path = tmp_path / "raising.jsonl"
    summary = runner.run(
        "smoke-fake",
        model_id="fake-model-v1",
        provider=RaisingProvider(),
        limit=5,
        resume=False,
        out_path=out_path,
    )
    assert summary.n_processed == 5  # every row still gets written
    assert summary.n_errors == 5

    lines = out_path.read_text().strip().splitlines()
    assert len(lines) == 5
    for line in lines:
        row = json.loads(line)
        assert row["invalid"] is True
        assert row["correct_fine"] is False
        assert "boom: adapter misconfigured" in row["error"]
