"""Tests for report.check_results_schema — the function CI's hard gate calls
against the real, committed results.json once one exists (W-A4). Per
SPEC-model-bench.md section 6.3: "fails if any model has n_rows !=
n_rows_expected or n_errors / n_rows > 0.02."

No real results.json exists yet (W-A2 has no Bedrock access and no run) —
these tests exercise the checking logic itself against in-memory fixtures,
so they stay meaningful and green regardless of run state.
"""

from __future__ import annotations

from modelbench.report import check_results_schema


def _model(key, n_rows, n_errors):
    return {"key": key, "n_rows": n_rows, "n_errors": n_errors}


def test_passing_results_has_no_violations():
    results = {
        "n_rows_expected": 3080,
        "models": [
            _model("claude-haiku", 3080, 0),
            _model("claude-sonnet", 3080, 10),  # 10/3080 = 0.32%, well under 2%
        ],
    }
    assert check_results_schema(results) == []


def test_wrong_row_count_is_a_violation():
    results = {
        "n_rows_expected": 3080,
        "models": [_model("claude-haiku", 3000, 0)],
    }
    violations = check_results_schema(results)
    assert len(violations) == 1
    assert "claude-haiku" in violations[0]
    assert "3000" in violations[0]


def test_error_rate_over_2_percent_is_a_violation():
    results = {
        "n_rows_expected": 3080,
        "models": [_model("claude-haiku", 3080, 100)],  # 100/3080 = 3.25%
    }
    violations = check_results_schema(results)
    assert len(violations) == 1
    assert "claude-haiku" in violations[0]


def test_error_rate_exactly_2_percent_is_not_a_violation():
    results = {
        "n_rows_expected": 100,
        "models": [_model("claude-haiku", 100, 2)],  # exactly 2%
    }
    assert check_results_schema(results) == []


def test_multiple_models_each_checked_independently():
    results = {
        "n_rows_expected": 3080,
        "models": [
            _model("good-model", 3080, 0),
            _model("bad-count-model", 100, 0),
            _model("bad-error-rate-model", 3080, 200),
        ],
    }
    violations = check_results_schema(results)
    assert len(violations) == 2
    joined = " ".join(violations)
    assert "bad-count-model" in joined
    assert "bad-error-rate-model" in joined
    assert "good-model" not in joined
