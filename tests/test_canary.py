"""Tests for modelbench.canary (Live Eval canary).

No test calls the real live endpoint -- run_hosted_models/call_endpoint
take an injectable `call`/`http_post` the same way the provider adapters
take an injectable client, per this repo's "tests mock the network" rule.

One test (test_canary_rows_are_all_in_the_holdout_split) is the spec's own
required proof: every id committed in canary/rows.json exists in
data/golden.jsonl with matching text/labels, i.e. the canary set is really
drawn from the held-out split and was not hand-typed.
"""

from __future__ import annotations

import json

import pytest

from modelbench import canary

GOLDEN_FIXTURE = [
    {
        "id": i,
        "text": f"row {i}",
        "intent_fine": f"intent_{i % 5}",
        "intent_coarse": f"coarse_{i % 2}",
    }
    for i in range(50)
]


def test_select_canary_row_ids_is_deterministic():
    first = canary.select_canary_row_ids(GOLDEN_FIXTURE, n=10, seed=26)
    second = canary.select_canary_row_ids(GOLDEN_FIXTURE, n=10, seed=26)
    assert first == second
    assert len(first) == 10
    assert len(set(first)) == 10
    assert set(first).issubset({row["id"] for row in GOLDEN_FIXTURE})
    assert first == sorted(first)


def test_select_canary_row_ids_changes_with_seed():
    a = canary.select_canary_row_ids(GOLDEN_FIXTURE, n=10, seed=26)
    b = canary.select_canary_row_ids(GOLDEN_FIXTURE, n=10, seed=1)
    assert a != b


def test_build_canary_rows_carries_real_golden_fields():
    rows = canary.build_canary_rows(GOLDEN_FIXTURE, n=10, seed=26)
    assert len(rows) == 10
    ids = [row["id"] for row in rows]
    assert ids == sorted(ids)
    by_id = {row["id"]: row for row in GOLDEN_FIXTURE}
    for row in rows:
        assert row == by_id[row["id"]]


def test_canary_rows_are_all_in_the_holdout_split():
    """The spec's required proof: canary/rows.json is drawn from
    data/golden.jsonl (the committed Banking77 TEST/holdout split), not
    hand-typed or drawn from anywhere else."""
    golden_by_id = {row["id"]: row for row in canary.load_jsonl(canary.GOLDEN_PATH)}
    canary_rows = canary.load_canary_rows()

    assert len(canary_rows) == canary.N_CANARY_ROWS
    for row in canary_rows:
        assert row["id"] in golden_by_id, f"canary row id {row['id']} is not in the holdout split"
        golden_row = golden_by_id[row["id"]]
        assert row["text"] == golden_row["text"]
        assert row["intent_fine"] == golden_row["intent_fine"]
        assert row["intent_coarse"] == golden_row["intent_coarse"]


def test_canary_rows_file_matches_seed_26_regeneration():
    """canary/rows.json is exactly what build_canary_rows(seed=26)
    produces from the real golden split -- proves the committed file
    wasn't hand-edited after generation."""
    golden_rows = canary.load_jsonl(canary.GOLDEN_PATH)
    regenerated = canary.build_canary_rows(golden_rows, n=canary.N_CANARY_ROWS, seed=canary.SEED)
    assert regenerated == canary.load_canary_rows()


def test_call_endpoint_returns_answers_on_success():
    def fake_post(url, payload, timeout):
        assert payload == {"text": "hello"}
        return {"answers": [{"key": "nova", "intent": "card_arrival", "error": None}]}

    result = canary.call_endpoint("hello", http_post=fake_post)
    assert result["error"] is None
    assert result["answers"] == [{"key": "nova", "intent": "card_arrival", "error": None}]
    assert result["latency_ms"] >= 0


def test_call_endpoint_never_raises_on_network_failure():
    def fake_post(url, payload, timeout):
        raise OSError("Name or service not known")

    result = canary.call_endpoint("hello", http_post=fake_post)
    assert result["answers"] == []
    assert "Name or service not known" in result["error"]


CANARY_ROWS = [
    {"id": 1, "text": "a", "intent_fine": "x", "intent_coarse": "c"},
    {"id": 2, "text": "b", "intent_fine": "y", "intent_coarse": "c"},
]


def test_run_hosted_models_scores_correct_and_wrong_and_sums_real_cost():
    responses = {
        "a": {
            "answers": [
                {"key": "nova", "intent": "x", "cost_usd": 0.01, "error": None},
                {"key": "llama", "intent": "wrong", "cost_usd": 0.02, "error": None},
                {"key": "mistral", "intent": "x", "cost_usd": 0.03, "error": None},
            ],
            "latency_ms": 100.0, "error": None,
        },
        "b": {
            "answers": [
                {"key": "nova", "intent": "y", "cost_usd": 0.01, "error": None},
                {"key": "llama", "intent": "y", "cost_usd": 0.02, "error": None},
                {"key": "mistral", "intent": "wrong", "cost_usd": 0.03, "error": None},
            ],
            "latency_ms": 200.0, "error": None,
        },
    }

    result = canary.run_hosted_models(CANARY_ROWS, call=lambda text: responses[text])

    assert result["scores"]["nova"] == {"n_correct": 2, "n_errors": 0}
    assert result["scores"]["llama"] == {"n_correct": 1, "n_errors": 0}
    assert result["scores"]["mistral"] == {"n_correct": 1, "n_errors": 0}
    assert result["cost_usd_total"] == pytest.approx(0.01 + 0.02 + 0.03 + 0.01 + 0.02 + 0.03)
    assert result["latencies_ms"] == [100.0, 200.0]
    assert result["request_errors"] == 0
    assert result["n_rows"] == 2


def test_run_hosted_models_per_model_error_counts_as_wrong_not_dropped():
    responses = {
        "a": {
            "answers": [
                {
                    "key": "nova", "intent": None, "cost_usd": 0.0,
                    "error": "Model not yet configured.",
                },
                {"key": "llama", "intent": "wrong", "cost_usd": 0.02, "error": None},
                {"key": "mistral", "intent": "x", "cost_usd": 0.03, "error": None},
            ],
            "latency_ms": 100.0, "error": None,
        },
        "b": {
            "answers": [
                {"key": "nova", "intent": "y", "cost_usd": 0.01, "error": None},
                {"key": "llama", "intent": "y", "cost_usd": 0.02, "error": None},
                {"key": "mistral", "intent": "wrong", "cost_usd": 0.03, "error": None},
            ],
            "latency_ms": 200.0, "error": None,
        },
    }

    result = canary.run_hosted_models(CANARY_ROWS, call=lambda text: responses[text])

    assert result["scores"]["nova"] == {"n_correct": 1, "n_errors": 1}
    # No fallback number was substituted for the error row -- it is not counted correct.
    assert result["cost_usd_total"] == pytest.approx(0.02 + 0.03 + 0.01 + 0.02 + 0.03)


def test_run_hosted_models_whole_request_failure_counts_as_error_for_every_hosted_model():
    def call(text):
        return {"answers": [], "latency_ms": 500.0, "error": "TimeoutError: timed out"}

    result = canary.run_hosted_models(CANARY_ROWS, call=call)

    assert result["request_errors"] == 2
    for key in canary.HOSTED_MODEL_KEYS:
        assert result["scores"][key] == {"n_correct": 0, "n_errors": 2}
    assert result["cost_usd_total"] == 0.0


def _hosted(n_correct_nova, n_errors_nova, n_rows=10, cost=0.05):
    return {
        "scores": {
            "nova": {"n_correct": n_correct_nova, "n_errors": n_errors_nova},
            "llama": {"n_correct": 7, "n_errors": 0},
            "mistral": {"n_correct": 8, "n_errors": 0},
        },
        "cost_usd_total": cost,
        "latencies_ms": [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0],
        "request_errors": 0,
        "n_rows": n_rows,
    }


_CLASSIFIER_OK = {"status": "ok", "error": None, "accuracy_fine": 0.9}


def test_build_record_matches_within_tolerance():
    hosted = _hosted(n_correct_nova=7, n_errors_nova=0)  # observed 0.7 vs recorded 0.705
    record = canary.build_record(
        CANARY_ROWS, hosted, _CLASSIFIER_OK, recorded=0.705, release="abc123", duration_s=12.3
    )

    assert record["observed"] == 0.7
    assert record["recorded"] == 0.705
    assert record["match"] is True
    assert record["errors"] == 0
    assert record["n"] == 10
    assert record["metric"] == "accuracy_fine_nova"
    assert record["system"] == "model-bench"
    assert record["kind"] == "canary"
    assert 1 <= len(record["lines"]) <= 8


def test_build_record_no_match_when_outside_tolerance():
    hosted = _hosted(n_correct_nova=0, n_errors_nova=0)  # observed 0.0, way outside tolerance
    record = canary.build_record(
        CANARY_ROWS, hosted, _CLASSIFIER_OK, recorded=0.705, release="abc123", duration_s=1.0
    )
    assert record["observed"] == 0.0
    assert record["match"] is False


def test_build_record_no_match_when_headline_model_has_any_error_even_if_in_tolerance():
    # 7/10 correct + a headline-model error is still "recorded as an error and match=false" --
    # no fallback number stands in for the missing/erroring row.
    hosted = _hosted(n_correct_nova=7, n_errors_nova=1)
    record = canary.build_record(
        CANARY_ROWS, hosted, _CLASSIFIER_OK, recorded=0.705, release="abc123", duration_s=1.0
    )
    assert record["match"] is False
    assert record["errors"] == 1


def test_build_record_extra_has_per_model_accuracy_and_real_cost():
    hosted = _hosted(n_correct_nova=7, n_errors_nova=0, cost=0.123456)
    record = canary.build_record(
        CANARY_ROWS, hosted, _CLASSIFIER_OK, recorded=0.705, release="abc123", duration_s=1.0
    )
    assert record["extra"]["accuracy_fine_nova"] == 0.7
    assert record["extra"]["accuracy_fine_llama"] == 0.7
    assert record["extra"]["accuracy_fine_mistral"] == 0.8
    assert record["extra"]["accuracy_fine_classifier"] == 0.9
    assert record["extra"]["cost_usd"] == pytest.approx(0.123456)


def test_build_record_handles_blocked_classifier_without_crashing():
    hosted = _hosted(n_correct_nova=7, n_errors_nova=0)
    blocked = {
        "status": "blocked", "error": "Name or service not known", "accuracy_fine": None,
    }
    record = canary.build_record(
        CANARY_ROWS, hosted, blocked, recorded=0.705, release="abc123", duration_s=1.0
    )
    assert record["extra"]["accuracy_fine_classifier"] is None
    assert "Name or service not known" in record["extra"]["classifier_error"]
    assert any("blocked" in line for line in record["lines"])


def test_load_recorded_metric_reads_nova_accuracy_fine(tmp_path):
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps({
        "models": [
            {"key": "nova", "accuracy_fine": 0.7051948051948052},
            {"key": "llama", "accuracy_fine": 0.72},
        ]
    }))
    assert canary.load_recorded_metric(results_path, model_key="nova") == 0.705


def test_run_classifier_passes_through_blocked_status(monkeypatch):
    def fake_run_baseline(rows, coarse_map, **kwargs):
        return {"status": "blocked", "error": "boom"}

    monkeypatch.setattr(canary.baseline, "run_baseline", fake_run_baseline)
    result = canary.run_classifier(CANARY_ROWS)
    assert result == {"status": "blocked", "error": "boom", "accuracy_fine": None}
