"""Hand-computed tests for every metrics.py function, per
SPEC-model-bench.md section 6.2's requirement: "a 10-row toy set with
hand-computed expected values for every function, including the edge cases
(all correct, all wrong, no confidence values)."

Expected values below are computed independently in this file with plain
arithmetic (not by calling the functions under test), so they are a genuine
check, not a restatement of the implementation.

Toy set (10 rows, two true fine intents / two true coarse groups):
  rows 1-5: intent_fine="card_arrival", intent_coarse="card"
    correct_fine:   T, T, F, F, T   (3/5)
    correct_coarse: T, T, T, F, T   (4/5)
    confidence:     90,80,60,40,None
    tokens in/out:  100/10, 100/10, 100/10, 120/15, 100/10
    latency_ms:     200, 210, 190, 300, 220         (no errors)
  rows 6-10: intent_fine="exchange_rate", intent_coarse="currency_crypto"
    correct_fine:   T, T, T, F, F   (3/5)
    correct_coarse: T, T, T, F, F   (3/5)
    confidence:     95,85,75,20,None
    tokens in/out:  90/8, 90/8, 90/8, 95/9, 0/0
    latency_ms:     150, 160, 140, 500, 0           (row 10 is an error row)
"""

from __future__ import annotations

import pytest

from modelbench import metrics


def _row(
    intent_fine,
    intent_coarse,
    correct_fine,
    correct_coarse,
    confidence,
    input_tokens,
    output_tokens,
    latency_ms,
    error=None,
):
    return {
        "intent_fine": intent_fine,
        "intent_coarse": intent_coarse,
        "correct_fine": correct_fine,
        "correct_coarse": correct_coarse,
        "confidence": confidence,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": latency_ms,
        "error": error,
    }


TOY_ROWS = [
    _row("card_arrival", "card", True, True, 90, 100, 10, 200),
    _row("card_arrival", "card", True, True, 80, 100, 10, 210),
    _row("card_arrival", "card", False, True, 60, 100, 10, 190),
    _row("card_arrival", "card", False, False, 40, 120, 15, 300),
    _row("card_arrival", "card", True, True, None, 100, 10, 220),
    _row("exchange_rate", "currency_crypto", True, True, 95, 90, 8, 150),
    _row("exchange_rate", "currency_crypto", True, True, 85, 90, 8, 160),
    _row("exchange_rate", "currency_crypto", True, True, 75, 90, 8, 140),
    _row("exchange_rate", "currency_crypto", False, False, 20, 95, 9, 500),
    _row("exchange_rate", "currency_crypto", False, False, None, 0, 0, 0, error="timeout"),
]


def test_accuracy_fine():
    # (3 + 3) / 10
    assert metrics.accuracy_fine(TOY_ROWS) == 0.6


def test_accuracy_coarse():
    # (4 + 3) / 10
    assert metrics.accuracy_coarse(TOY_ROWS) == 0.7


def test_accuracy_all_correct_edge_case():
    all_correct = [_row("x", "g", True, True, 90, 10, 1, 100) for _ in range(4)]
    assert metrics.accuracy_fine(all_correct) == 1.0
    assert metrics.accuracy_coarse(all_correct) == 1.0


def test_accuracy_all_wrong_edge_case():
    all_wrong = [_row("x", "g", False, False, 10, 10, 1, 100) for _ in range(4)]
    assert metrics.accuracy_fine(all_wrong) == 0.0
    assert metrics.accuracy_coarse(all_wrong) == 0.0


def test_accuracy_empty_rows():
    assert metrics.accuracy_fine([]) == 0.0
    assert metrics.accuracy_coarse([]) == 0.0


def test_cost_per_1k():
    price = {"input_per_1m": 3.0, "output_per_1m": 15.0}
    mean_in = (100 + 100 + 100 + 120 + 100 + 90 + 90 + 90 + 95 + 0) / 10
    mean_out = (10 + 10 + 10 + 15 + 10 + 8 + 8 + 8 + 9 + 0) / 10
    expected = (mean_in * 3.0 + mean_out * 15.0) / 1e6 * 1000
    assert metrics.cost_per_1k(TOY_ROWS, price) == expected
    assert expected == 0.3975  # pinned so a future refactor can't silently drift


def test_latency_p50_p95_excludes_error_rows():
    # Row 10 (error="timeout") is excluded regardless of its latency_ms=0.
    values = sorted([200, 210, 190, 300, 220, 150, 160, 140, 500])
    assert values == [140, 150, 160, 190, 200, 210, 220, 300, 500]
    p50, p95 = metrics.latency_p50_p95(TOY_ROWS)
    assert p50 == pytest.approx(200)  # rank 0.5*8=4.0 -> values[4]
    assert p95 == pytest.approx(420)  # rank 0.95*8=7.6 -> 300 + (500-300)*0.6


def test_brier():
    scored = [r for r in TOY_ROWS if r["confidence"] is not None]
    assert len(scored) == 8
    expected = sum(
        (r["confidence"] / 100 - (1.0 if r["correct_fine"] else 0.0)) ** 2 for r in scored
    ) / len(scored)
    assert metrics.brier(TOY_ROWS) == expected


def test_brier_no_confidence_values_edge_case():
    rows = [_row("x", "g", True, True, None, 10, 1, 100) for _ in range(3)]
    assert metrics.brier(rows) == 0.0


def test_reliability_bins():
    bins = metrics.reliability_bins(TOY_ROWS)
    assert len(bins) == 10
    by_label = {b["bin"]: b for b in bins}

    assert by_label["90-100"]["n"] == 2  # confidences 90, 95
    assert by_label["90-100"]["mean_confidence"] == 92.5
    assert by_label["90-100"]["observed_accuracy"] == 1.0

    assert by_label["80-90"]["n"] == 2  # confidences 80, 85
    assert by_label["80-90"]["observed_accuracy"] == 1.0

    assert by_label["70-80"]["n"] == 1  # confidence 75
    assert by_label["70-80"]["observed_accuracy"] == 1.0

    assert by_label["60-70"]["n"] == 1  # confidence 60, wrong
    assert by_label["60-70"]["observed_accuracy"] == 0.0

    assert by_label["40-50"]["n"] == 1  # confidence 40, wrong
    assert by_label["20-30"]["n"] == 1  # confidence 20, wrong

    # Untouched bins report n=0, not an error.
    assert by_label["0-10"]["n"] == 0
    assert by_label["0-10"]["mean_confidence"] == 0.0


def test_reliability_bins_confidence_100_falls_in_last_bin():
    rows = [_row("x", "g", True, True, 100, 10, 1, 100)]
    bins = metrics.reliability_bins(rows)
    assert bins[9]["n"] == 1
    assert bins[9]["bin"] == "90-100"


def test_per_intent_fine():
    result = metrics.per_intent(TOY_ROWS, "fine")
    by_name = {r["name"]: r for r in result}
    assert by_name["card_arrival"] == {"name": "card_arrival", "n": 5, "accuracy": 0.6}
    assert by_name["exchange_rate"] == {"name": "exchange_rate", "n": 5, "accuracy": 0.6}
    assert len(result) == 2


def test_per_intent_coarse_sorted_worst_first():
    result = metrics.per_intent(TOY_ROWS, "coarse")
    # currency_crypto (0.6) is worse than card (0.8), so it comes first.
    assert result[0]["name"] == "currency_crypto"
    assert result[0]["accuracy"] == 0.6
    assert result[1]["name"] == "card"
    assert result[1]["accuracy"] == 0.8


def test_per_intent_invalid_level_raises():
    with pytest.raises(ValueError):
        metrics.per_intent(TOY_ROWS, "medium")
