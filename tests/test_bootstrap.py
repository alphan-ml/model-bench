"""Small-fixture tests for bootstrap.py (decision-pack Task 2: paired
bootstrap over per-message correctness, joined by id across models)."""

from __future__ import annotations

import pytest

from modelbench import bootstrap


def test_point_estimates_match_plain_accuracy():
    correct_by_model = {
        "a": [True, True, False, False, True, True, False, True, True, False],  # 6/10
        "b": [True, False, False, False, True, True, True, True, True, True],  # 7/10
    }
    result = bootstrap.paired_bootstrap(correct_by_model, n_resamples=200, seed=26)
    assert result["accuracy_fine_ci"]["a"]["point"] == pytest.approx(0.6)
    assert result["accuracy_fine_ci"]["b"]["point"] == pytest.approx(0.7)
    assert result["pairwise_diff_ci"]["a_minus_b"]["point"] == pytest.approx(-0.1)


def test_identical_models_have_zero_point_difference_and_tight_interval():
    same = [True, True, False, True, False, True, True, False, True, True]
    correct_by_model = {"a": same, "b": list(same)}
    result = bootstrap.paired_bootstrap(correct_by_model, n_resamples=500, seed=26)
    diff = result["pairwise_diff_ci"]["a_minus_b"]
    assert diff["point"] == 0.0
    # Paired: every resample compares a model against an identical copy of
    # itself on the SAME resampled ids, so the difference is exactly 0 in
    # every single resample -- the interval collapses to a point.
    assert diff["ci_lo"] == 0.0
    assert diff["ci_hi"] == 0.0


def test_all_correct_and_all_wrong_edge_cases_have_zero_width_intervals():
    correct_by_model = {
        "perfect": [True] * 20,
        "useless": [False] * 20,
    }
    result = bootstrap.paired_bootstrap(correct_by_model, n_resamples=100, seed=26)
    assert result["accuracy_fine_ci"]["perfect"] == {"point": 1.0, "ci_lo": 1.0, "ci_hi": 1.0}
    assert result["accuracy_fine_ci"]["useless"] == {"point": 0.0, "ci_lo": 0.0, "ci_hi": 0.0}


def test_result_is_deterministic_given_the_same_seed():
    correct_by_model = {
        "a": [True, False, True, True, False, False, True, True, False, True],
        "b": [False, False, True, True, True, False, True, False, False, True],
    }
    r1 = bootstrap.paired_bootstrap(correct_by_model, n_resamples=300, seed=26)
    r2 = bootstrap.paired_bootstrap(correct_by_model, n_resamples=300, seed=26)
    assert r1 == r2


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        bootstrap.paired_bootstrap({"a": [True, False], "b": [True, False, True]})


def test_empty_input_raises():
    with pytest.raises(ValueError):
        bootstrap.paired_bootstrap({})


def test_pairwise_keys_cover_every_unordered_pair():
    correct_by_model = {
        "a": [True, False, True, True],
        "b": [False, False, True, True],
        "c": [True, True, True, False],
    }
    result = bootstrap.paired_bootstrap(correct_by_model, n_resamples=50, seed=26)
    assert set(result["pairwise_diff_ci"].keys()) == {"a_minus_b", "a_minus_c", "b_minus_c"}
