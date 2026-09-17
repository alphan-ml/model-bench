"""Small-fixture tests for baseline.py (decision-pack Task 1: TF-IDF +
logistic regression classifier baseline). No real network call in any
test here -- download_train_jsonl is exercised against a tiny local CSV
fixture (cache path) and against a monkeypatched urlopen that raises, to
prove TrainDownloadError carries the original message. Training/eval use
a small synthetic train/test set, not the real 10,003-row split.
"""

from __future__ import annotations

import json

import pytest

from modelbench import baseline

TRAIN_ROWS = [
    {"id": 0, "text": "my card has not arrived yet", "intent_fine": "card_arrival"},
    {"id": 1, "text": "where is my card, it is late", "intent_fine": "card_arrival"},
    {"id": 2, "text": "card still not here after two weeks", "intent_fine": "card_arrival"},
    {"id": 3, "text": "what is today's exchange rate for euros", "intent_fine": "exchange_rate"},
    {"id": 4, "text": "can you tell me the current exchange rate", "intent_fine": "exchange_rate"},
    {"id": 5, "text": "exchange rate for usd to gbp please", "intent_fine": "exchange_rate"},
]

TEST_ROWS = [
    {
        "id": 100,
        "text": "my card hasn't arrived",
        "intent_fine": "card_arrival",
        "intent_coarse": "card",
    },
    {
        "id": 101,
        "text": "what's the exchange rate today",
        "intent_fine": "exchange_rate",
        "intent_coarse": "currency_crypto",
    },
]

COARSE_MAP = {"card_arrival": "card", "exchange_rate": "currency_crypto"}


def test_rows_from_train_csv_text_parses_id_text_intent():
    csv_text = "text,category\r\nhello there,greeting\r\nwhat is my balance,balance\r\n"
    rows = baseline._rows_from_train_csv_text(csv_text)
    assert rows == [
        {"id": 0, "text": "hello there", "intent_fine": "greeting"},
        {"id": 1, "text": "what is my balance", "intent_fine": "balance"},
    ]


def test_download_train_jsonl_uses_cache_without_network(tmp_path, monkeypatch):
    dest = tmp_path / "train.jsonl"
    with open(dest, "w") as f:
        for row in TRAIN_ROWS:
            f.write(json.dumps(row) + "\n")

    def _boom(*args, **kwargs):
        raise AssertionError("must not touch the network when the cache exists")

    monkeypatch.setattr(baseline.urllib.request, "urlopen", _boom)

    summary = baseline.download_train_jsonl(dest_path=dest, use_cache=True)
    assert summary["from_cache"] is True
    assert summary["n_rows"] == len(TRAIN_ROWS)
    assert summary["dest_path"] == "train.jsonl" or summary["dest_path"].endswith("train.jsonl")


def test_download_train_jsonl_wraps_failure_in_train_download_error(tmp_path, monkeypatch):
    dest = tmp_path / "does_not_exist" / "train.jsonl"

    def _boom(*args, **kwargs):
        raise OSError("Name or service not known")

    monkeypatch.setattr(baseline.urllib.request, "urlopen", _boom)

    with pytest.raises(baseline.TrainDownloadError) as excinfo:
        baseline.download_train_jsonl(dest_path=dest, use_cache=True)
    assert "Name or service not known" in str(excinfo.value)


def test_train_and_evaluate_classifier_on_tiny_fixture():
    pipe = baseline.train_classifier(TRAIN_ROWS)
    result = baseline.evaluate_classifier(pipe, TEST_ROWS, COARSE_MAP)

    assert result["n_test_rows"] == 2
    # This tiny, cleanly-separated fixture should be trivially learnable.
    assert result["accuracy_fine"] == 1.0
    assert result["accuracy_coarse"] == 1.0
    assert {r["id"] for r in result["rows"]} == {100, 101}
    for row in result["rows"]:
        assert row["correct_fine"] is True
        assert row["correct_coarse"] is True


def test_run_baseline_end_to_end_ok(tmp_path, monkeypatch):
    dest = tmp_path / "train.jsonl"
    with open(dest, "w") as f:
        for row in TRAIN_ROWS:
            f.write(json.dumps(row) + "\n")

    def _boom(*args, **kwargs):
        raise AssertionError("must not touch the network when the cache exists")

    monkeypatch.setattr(baseline.urllib.request, "urlopen", _boom)

    result = baseline.run_baseline(TEST_ROWS, COARSE_MAP, dest_path=dest)
    assert result["status"] == "ok"
    assert result["error"] is None
    assert result["n_train_rows"] == len(TRAIN_ROWS)
    assert result["n_test_rows"] == 2
    assert result["cost_per_1k_usd"] == 0.0
    assert "zero" in result["cost_assumption"].lower()
    assert len(result["rows"]) == 2


def test_run_baseline_reports_blocked_status_with_exact_error(tmp_path, monkeypatch):
    dest = tmp_path / "train.jsonl"  # does not exist -> forces a download attempt

    def _boom(*args, **kwargs):
        raise OSError("[Errno -2] Name or service not known")

    monkeypatch.setattr(baseline.urllib.request, "urlopen", _boom)

    result = baseline.run_baseline(TEST_ROWS, COARSE_MAP, dest_path=dest)
    assert result["status"] == "blocked"
    assert "Name or service not known" in result["error"]
    assert "rows" not in result
