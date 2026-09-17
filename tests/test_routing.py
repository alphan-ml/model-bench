"""Small-fixture tests for routing.py (decision-pack Task 5: cost per
correctly routed message, and the quality/automation trade-off curve)."""

from __future__ import annotations

from modelbench import routing


def _row(id_, confidence, correct):
    return {"id": id_, "confidence": confidence, "correct_fine": correct}


def test_cost_per_correct_route_basic():
    # $0.10 per 1,000 messages at 50% accuracy -> $0.20 per 1,000 CORRECT ones.
    assert routing.cost_per_correct_route(0.10, 0.5) == 0.20


def test_cost_per_correct_route_full_accuracy_equals_cost_per_1k():
    assert routing.cost_per_correct_route(0.30, 1.0) == 0.30


def test_cost_per_correct_route_zero_accuracy_is_none():
    assert routing.cost_per_correct_route(0.10, 0.0) is None


def test_quality_automation_curve_shape_and_thresholds():
    rows = [_row(i, 100, True) for i in range(5)] + [_row(i + 5, 60, False) for i in range(5)]
    curve = routing.quality_automation_curve(rows, thresholds=range(50, 101, 10))
    thresholds = [c["threshold"] for c in curve]
    assert thresholds == [50, 60, 70, 80, 90, 100]

    by_t = {c["threshold"]: c for c in curve}
    # t=50: everyone qualifies (10 rows), 5 correct -> 0.5 accuracy, full automation.
    assert by_t[50]["automation_rate"] == 1.0
    assert by_t[50]["auto_accuracy"] == 0.5
    # t=70: only the confidence-100 rows qualify -> perfect accuracy, half automation.
    assert by_t[70]["automation_rate"] == 0.5
    assert by_t[70]["auto_accuracy"] == 1.0
    # t=100: still just the confidence-100 rows.
    assert by_t[100]["automation_rate"] == 0.5
    assert by_t[100]["auto_accuracy"] == 1.0


def test_quality_automation_curve_empty_subset_reports_none_accuracy():
    rows = [_row(0, 50, True)]
    curve = routing.quality_automation_curve(rows, thresholds=range(90, 101, 10))
    assert curve[0]["automation_rate"] == 0.0
    assert curve[0]["auto_accuracy"] is None


def test_quality_automation_curve_null_confidence_excluded():
    rows = [_row(0, None, True), _row(1, 90, True)]
    curve = routing.quality_automation_curve(rows, thresholds=range(50, 61, 10))
    assert curve[0]["automation_rate"] == 0.5  # only id=1 qualifies, id=0 is null
