"""Small-fixture tests for escalation.py (decision-pack Task 4: an
escalation policy fit on model-reported confidence)."""

from __future__ import annotations

from modelbench import escalation


def _row(id_, confidence, correct):
    return {"id": id_, "confidence": confidence, "correct_fine": correct}


def test_split_halves_is_deterministic_and_covers_every_id_exactly_once():
    ids = list(range(20))
    a1, b1 = escalation.split_halves(ids, seed=26)
    a2, b2 = escalation.split_halves(ids, seed=26)
    assert a1 == a2 and b1 == b2
    assert len(a1) == 10 and len(b1) == 10
    assert sorted(a1 + b1) == ids
    assert set(a1).isdisjoint(b1)


def test_split_halves_different_seed_gives_a_different_split():
    ids = list(range(20))
    a_26, _ = escalation.split_halves(ids, seed=26)
    a_1, _ = escalation.split_halves(ids, seed=1)
    assert a_26 != a_1


def test_find_threshold_picks_smallest_threshold_reaching_target():
    # confidence 100 rows: all correct; confidence 50 rows: half correct.
    rows = (
        [_row(i, 100, True) for i in range(4)]
        + [_row(i + 4, 50, True) for i in range(2)]
        + [_row(i + 6, 50, False) for i in range(2)]
    )
    # At t=0..50: all 8 rows qualify -> 6/8 = 0.75 accuracy.
    # At t=51..100: only the confidence-100 rows qualify -> 4/4 = 1.0.
    # 0.75 already clears a 70% target, so the smallest satisfying threshold is 0;
    # reaching 95% needs the confidence-100-only subset, whose smallest
    # qualifying threshold is 51 (the first integer above the 50-confidence group).
    assert escalation.find_threshold(rows, 70) == 0
    assert escalation.find_threshold(rows, 95) == 51


def test_find_threshold_returns_none_when_unreachable():
    rows = [_row(0, 100, False), _row(1, 100, True)]  # best possible subset accuracy is 0.5
    assert escalation.find_threshold(rows, 95) is None


def test_find_threshold_null_confidence_rows_never_qualify():
    # Two null-confidence rows are mixed in with a wrong 80-confidence row
    # and a correct 90-confidence row. If nulls were (wrongly) treated as
    # satisfying `>= 0`, they would drag t=0's accuracy in some direction;
    # since they must be excluded outright, t=0's subset is just the two
    # non-null rows (1 wrong, 1 correct -> 0.5), and reaching 100% accuracy
    # requires narrowing to the single confidence-90 row, i.e. t=81 (the
    # first integer above the wrong row's confidence of 80).
    rows = [
        _row(0, None, True),
        _row(1, None, True),
        _row(2, 80, False),
        _row(3, 90, True),
    ]
    assert escalation.find_threshold(rows, 50) == 0
    assert escalation.find_threshold(rows, 100) == 81


def test_evaluate_policy_null_confidence_always_escalated():
    rows = [_row(0, None, True), _row(1, 95, True), _row(2, 40, False)]
    result = escalation.evaluate_policy(rows, threshold=90)
    assert result["n_auto"] == 1  # only id=1
    assert result["n_escalated"] == 2  # id=0 (null) and id=2 (below threshold)
    assert result["accuracy_auto"] == 1.0
    assert result["accuracy_escalated"] == 0.5  # id=0 correct + id=2 wrong -> 1/2


def test_evaluate_policy_none_threshold_escalates_everything():
    rows = [_row(0, 100, True), _row(1, 90, False)]
    result = escalation.evaluate_policy(rows, threshold=None)
    assert result["n_auto"] == 0
    assert result["automation_rate"] == 0.0
    assert result["accuracy_auto"] is None
    assert result["n_escalated"] == 2


def test_run_escalation_reports_both_directions_for_both_targets():
    # ids 0-9: confidence 100, always correct. ids 10-19: confidence 50,
    # always wrong. With seed=26, split_halves gives each half a 5/5 mix
    # of the two groups (verified directly below), so the only way to
    # reach 95%+ accuracy on either half is to keep just the confidence-100
    # rows -- the smallest threshold that does that is 51 (the first
    # integer above the low group's confidence value of 50).
    rows = [_row(i, 100, True) for i in range(10)] + [_row(i + 10, 50, False) for i in range(10)]
    ids_a, ids_b = escalation.split_halves([r["id"] for r in rows], seed=26)
    assert sorted(i for i in ids_a if i < 10) and sorted(i for i in ids_a if i >= 10)
    assert sorted(i for i in ids_b if i < 10) and sorted(i for i in ids_b if i >= 10)

    result = escalation.run_escalation(rows, seed=26, targets=(95, 98))
    assert result["seed"] == 26
    assert result["n_a"] == 10 and result["n_b"] == 10
    assert set(result["targets"].keys()) == {"95", "98"}
    for target_block in result["targets"].values():
        assert set(target_block.keys()) == {"fit_on_a_eval_on_b", "fit_on_b_eval_on_a"}
        for direction in target_block.values():
            assert direction["chosen_threshold"] == 51
            assert direction["accuracy_auto"] == 1.0
