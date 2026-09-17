"""Small-fixture tests for errors.py (decision-pack Task 3: confusion pairs
and the intents where every given model fails)."""

from __future__ import annotations

import pytest

from modelbench import errors


def _row(id_, true, pred, correct):
    return {"id": id_, "intent_fine": true, "intent_pred": pred, "correct_fine": correct}


def test_top_confused_pairs_counts_wrong_rows_only_most_frequent_first():
    rows = [
        _row(1, "card_arrival", "card_delivery_estimate", False),
        _row(2, "card_arrival", "card_delivery_estimate", False),
        _row(3, "card_arrival", "card_arrival", True),  # correct, excluded
        _row(4, "exchange_rate", "exchange_via_app", False),
        _row(5, "card_arrival", "top_up_failed", False),
    ]
    result = errors.top_confused_pairs(rows, top_n=10)
    assert result[0] == {"true": "card_arrival", "predicted": "card_delivery_estimate", "count": 2}
    assert {"true": "exchange_rate", "predicted": "exchange_via_app", "count": 1} in result
    assert {"true": "card_arrival", "predicted": "top_up_failed", "count": 1} in result
    assert len(result) == 3  # the correct row never contributes a pair


def test_top_confused_pairs_respects_top_n():
    rows = [_row(i, "x", f"pred_{i}", False) for i in range(15)]
    result = errors.top_confused_pairs(rows, top_n=5)
    assert len(result) == 5


def test_top_confused_pairs_handles_none_prediction():
    rows = [_row(1, "card_arrival", None, False), _row(2, "card_arrival", None, False)]
    result = errors.top_confused_pairs(rows)
    assert result == [{"true": "card_arrival", "predicted": None, "count": 2}]


def test_hardest_intents_all_wrong_requires_every_model_wrong_on_the_same_id():
    rows_by_model = {
        "nova": [
            _row(1, "card_arrival", "x", False),
            _row(2, "card_arrival", "card_arrival", True),
            _row(3, "exchange_rate", "x", False),
        ],
        "llama": [
            _row(1, "card_arrival", "y", False),
            _row(2, "card_arrival", "card_arrival", True),
            _row(3, "exchange_rate", "exchange_rate", True),  # llama gets id 3 right
        ],
    }
    result = errors.hardest_intents_all_wrong(rows_by_model)
    by_name = {r["intent"]: r for r in result}

    # id 1: both wrong -> card_arrival gets 1 all-wrong row (out of 2 rows for that intent)
    assert by_name["card_arrival"]["n_rows"] == 2
    assert by_name["card_arrival"]["n_all_wrong"] == 1
    assert by_name["card_arrival"]["rate"] == 0.5

    # id 3: nova wrong, llama right -> not "all wrong"
    assert by_name["exchange_rate"]["n_rows"] == 1
    assert by_name["exchange_rate"]["n_all_wrong"] == 0
    assert by_name["exchange_rate"]["rate"] == 0.0


def test_hardest_intents_all_wrong_sorted_worst_first():
    rows_by_model = {
        "a": [
            _row(1, "intent_low", "x", False),
            _row(2, "intent_high", "x", False),
            _row(3, "intent_high", "x", False),
        ],
        "b": [
            _row(1, "intent_low", "x", False),
            _row(2, "intent_high", "x", False),
            _row(3, "intent_high", "x", False),
        ],
    }
    result = errors.hardest_intents_all_wrong(rows_by_model)
    assert result[0]["intent"] == "intent_high"
    assert result[0]["n_all_wrong"] == 2
    assert result[1]["intent"] == "intent_low"
    assert result[1]["n_all_wrong"] == 1


def test_hardest_intents_all_wrong_only_uses_ids_common_to_every_model():
    rows_by_model = {
        "a": [_row(1, "card_arrival", "x", False), _row(2, "card_arrival", "x", False)],
        "b": [_row(1, "card_arrival", "y", False)],  # id 2 missing from b
    }
    result = errors.hardest_intents_all_wrong(rows_by_model)
    assert result == [{"intent": "card_arrival", "n_rows": 1, "n_all_wrong": 1, "rate": 1.0}]


def test_hardest_intents_all_wrong_empty_input_raises():
    with pytest.raises(ValueError):
        errors.hardest_intents_all_wrong({})
